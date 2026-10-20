# -*- coding: utf-8 -*-
"""Chat conversations in the database (chat_conversations and
chat_messages, src/storage.py).

A message row holds the exchange in the model's own shape — role, text,
the tool calls the model asked for, or one tool's result — plus the
facts the chat page shows beside it (token usage, result sizes, errors)
and, on a bot reply, the model call's transcript (``transcript.py``).
``harness.model_view`` strips a stored message down to what the model
may see, so extra keys here never reach the provider.

Pending confirmations (tool calls held until the user answers) sit on
the conversation row as JSON; ``harness.py`` owns their shape.

Each message row also carries its model call's token counts as columns
(``input_tokens``/``output_tokens``, 0 where there was no call), so the
facts the sidebar shows for every conversation come from one grouped
query instead of parsing every stored prompt on every refresh
(2026-10-10). Rows written before the columns existed are filled once
by ``backfill_tokens`` at startup.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

#: The first user message becomes the title, cut to this many characters.
TITLE_MAX_CHARS = 60

#: ``append_message``'s "leave the pending list as it is" marker, so
#: None can mean "clear it".
KEEP_PENDING: Any = object()

#: The roles whose row sets off a turn of the bot's: the user's own
#: line, and a run notice (src/chat/run_notice.py). The sidebar counts
#: these as the conversation's turns.
TURN_ROLES = ("user", "notice")

#: The facts of a conversation with no messages yet.
_EMPTY_STATS: Dict[str, Any] = {
    "message_count": 0, "user_input_count": 0, "total_tokens": 0, "ended_at": None,
}


def _session():
    from src.storage import DatabaseManager

    return DatabaseManager.get_instance().get_session()


def _iso(value: Optional[datetime]) -> Optional[str]:
    from src.storage import utc_iso

    return utc_iso(value)


def _conversation_view(row: Any, stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        **(stats or _EMPTY_STATS),
    }


def _stats_by_conversation(session: Any, conversation_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """What the history rows show for each conversation (2026-09-23), in
    the page's words: how many messages it holds, how many turns were
    set off (``user_input_count``, the page's "convo turns": the user's
    own lines and the run notices the app wrote, since a notice sets
    off a turn the same way — owner decision 2026-10-20), the tokens
    every model call cost together, and when the last turn was set off
    (``ended_at``; ``None`` before the first message). One grouped
    query over the message table, for every conversation or for the
    one given; a conversation with no rows is absent."""
    from sqlalchemy import case, func

    from src.storage import ChatMessageRecord as M

    tokens = func.coalesce(M.input_tokens, 0) + func.coalesce(M.output_tokens, 0)
    is_turn = M.role.in_(TURN_ROLES)
    query = session.query(
        M.conversation_id,
        func.count(M.id),
        func.sum(case((is_turn, 1), else_=0)),
        func.sum(tokens),
        func.max(case((is_turn, M.created_at))),
    ).group_by(M.conversation_id)
    if conversation_id is not None:
        query = query.filter(M.conversation_id == conversation_id)
    return {
        conversation: {
            "message_count": int(count or 0),
            "user_input_count": int(user_inputs or 0),
            "total_tokens": int(total_tokens or 0),
            "ended_at": _iso(_as_datetime(ended_at)),
        }
        for conversation, count, user_inputs, total_tokens, ended_at in query.all()
    }


def _as_datetime(value: Any) -> Optional[datetime]:
    """A ``max()`` over a DateTime column comes back parsed on most
    drivers; sqlite can hand back the stored text."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _token_counts(message: Dict[str, Any]) -> Tuple[int, int]:
    """The message's ``usage`` as the two columns: 0 where there is no
    usage or a count is missing."""
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)


def create_conversation() -> Dict[str, Any]:
    """A new, empty conversation; its id is what every other call takes."""
    from src.storage import ChatConversationRecord

    with _session() as session:
        row = ChatConversationRecord(id=uuid.uuid4().hex)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _conversation_view(row)


def list_conversations() -> List[Dict[str, Any]]:
    """Every conversation, the one the user most recently wrote in
    first (owner request 2026-10-15: not the one whose reply most
    recently landed — ``ended_at`` orders, and a conversation with no
    message yet sits by when it was created), each with the facts the
    history rows show (``_stats_by_conversation``)."""
    from src.storage import ChatConversationRecord

    with _session() as session:
        stats = _stats_by_conversation(session)
        rows = session.query(ChatConversationRecord).all()
        views = [_conversation_view(row, stats.get(row.id)) for row in rows]
    return sorted(views, key=_last_written, reverse=True)


def _last_written(view: Dict[str, Any]) -> datetime:
    """When the user last wrote in the conversation, else when it was
    created (both ISO strings from ``_iso``)."""
    return datetime.fromisoformat(view["ended_at"] or view["created_at"])


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """The conversation with its messages in order and the pending
    confirmation (None when nothing waits); None for an unknown id."""
    from src.storage import ChatConversationRecord, ChatMessageRecord

    with _session() as session:
        row = session.get(ChatConversationRecord, conversation_id)
        if row is None:
            return None
        rows = (
            session.query(ChatMessageRecord)
            .filter_by(conversation_id=conversation_id)
            .order_by(ChatMessageRecord.seq)
            .all()
        )
        messages = [_message_view(m) for m in rows]
        view = _conversation_view(row, _stats_by_conversation(session, conversation_id).get(conversation_id))
        view["messages"] = messages
        view["pending"] = _parse(row.pending_json)
        return view


def conversation_exists(conversation_id: str) -> bool:
    from src.storage import ChatConversationRecord

    with _session() as session:
        return session.get(ChatConversationRecord, conversation_id) is not None


def delete_conversation(conversation_id: str) -> bool:
    """Remove the conversation, its messages and its run watches. False
    for an unknown id."""
    from src.storage import ChatConversationRecord, ChatMessageRecord, ChatRunWatchRecord

    with _session() as session:
        row = session.get(ChatConversationRecord, conversation_id)
        if row is None:
            return False
        (
            session.query(ChatMessageRecord)
            .filter_by(conversation_id=conversation_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(ChatRunWatchRecord)
            .filter_by(conversation_id=conversation_id)
            .delete(synchronize_session=False)
        )
        session.delete(row)
        session.commit()
        return True


def _message_view(row: Any) -> Dict[str, Any]:
    message = _parse(row.content_json) or {}
    return {**message, "seq": row.seq, "created_at": _iso(row.created_at)}


def messages(conversation_id: str) -> List[Dict[str, Any]]:
    """The stored messages in order, each with its ``seq`` and time."""
    from src.storage import ChatMessageRecord

    with _session() as session:
        rows = (
            session.query(ChatMessageRecord)
            .filter_by(conversation_id=conversation_id)
            .order_by(ChatMessageRecord.seq)
            .all()
        )
        return [_message_view(row) for row in rows]


def message(conversation_id: str, seq: int) -> Optional[Dict[str, Any]]:
    """One stored message by its seq, None when there is none."""
    from src.storage import ChatMessageRecord

    with _session() as session:
        row = (
            session.query(ChatMessageRecord)
            .filter_by(conversation_id=conversation_id, seq=seq)
            .one_or_none()
        )
        return _message_view(row) if row is not None else None


def append_message(conversation_id: str, message: Dict[str, Any],
                   pending: Any = KEEP_PENDING, drop_watch: Optional[str] = None) -> int:
    """Store one message (a dict in the model's shape plus any page
    facts) as the next row and touch the conversation. The first user
    message names an untitled conversation. ``pending`` — a held-calls
    dict, or None to clear — is written in the same commit when given
    (``KEEP_PENDING`` leaves it alone), so answering a held call and
    dropping it from the list can never come apart (2026-10-10).
    ``drop_watch`` — a run id — removes the conversation's watch on
    that run in the same commit, for the same reason: a run notice is
    stored exactly once (2026-10-20). Returns the row's seq."""
    from sqlalchemy import func

    from src.storage import ChatConversationRecord, ChatMessageRecord, ChatRunWatchRecord, utc_naive_now

    with _session() as session:
        conversation = session.get(ChatConversationRecord, conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)
        last = (
            session.query(func.max(ChatMessageRecord.seq))
            .filter_by(conversation_id=conversation_id)
            .scalar()
        )
        seq = int(last or 0) + 1
        input_tokens, output_tokens = _token_counts(message)
        session.add(ChatMessageRecord(
            conversation_id=conversation_id,
            seq=seq,
            role=str(message.get("role") or ""),
            content_json=json.dumps(message, ensure_ascii=False),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ))
        if conversation.title is None and message.get("role") == "user":
            conversation.title = _title_from(str(message.get("content") or ""))
        if pending is not KEEP_PENDING:
            conversation.pending_json = _pending_json(pending)
        if drop_watch is not None:
            (
                session.query(ChatRunWatchRecord)
                .filter_by(conversation_id=conversation_id, run_id=drop_watch)
                .delete(synchronize_session=False)
            )
        conversation.updated_at = utc_naive_now()
        session.commit()
        return seq


def backfill_tokens() -> int:
    """Fill the token columns of rows written before they existed
    (NULL): a bot reply's counts come out of its stored ``usage``, every
    other row gets 0. Run once at startup; a second run finds nothing.
    Returns how many rows were filled."""
    from src.storage import ChatMessageRecord

    with _session() as session:
        rows = (
            session.query(ChatMessageRecord)
            .filter((ChatMessageRecord.input_tokens.is_(None)) | (ChatMessageRecord.output_tokens.is_(None)))
            .all()
        )
        for row in rows:
            row.input_tokens, row.output_tokens = _token_counts(_parse(row.content_json) or {})
        session.commit()
        return len(rows)


def set_pending(conversation_id: str, pending: Optional[Dict[str, Any]]) -> None:
    """Record (or, with None, clear) the tool calls waiting for the user."""
    from src.storage import ChatConversationRecord

    with _session() as session:
        row = session.get(ChatConversationRecord, conversation_id)
        if row is None:
            raise KeyError(conversation_id)
        row.pending_json = _pending_json(pending)
        session.commit()


def _pending_json(pending: Optional[Dict[str, Any]]) -> Optional[str]:
    return json.dumps(pending, ensure_ascii=False) if pending is not None else None


def get_pending(conversation_id: str) -> Optional[Dict[str, Any]]:
    from src.storage import ChatConversationRecord

    with _session() as session:
        row = session.get(ChatConversationRecord, conversation_id)
        return _parse(row.pending_json) if row is not None else None


def _title_from(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= TITLE_MAX_CHARS:
        return flat
    return flat[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def _parse(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# Run watches: the runs a conversation waits to hear about (2026-10-20)
# ---------------------------------------------------------------------------


def _watch_view(row: Any) -> Dict[str, Any]:
    return {
        "conversation_id": row.conversation_id, "run_id": row.run_id,
        "language": row.language, "created_at": _iso(row.created_at),
    }


def add_watch(conversation_id: str, run_id: str, language: str) -> None:
    """Record that the conversation waits for the run to end (the bot's
    start_run tool). A second watch on the same run by the same
    conversation is not added twice."""
    from src.storage import ChatRunWatchRecord

    with _session() as session:
        existing = (
            session.query(ChatRunWatchRecord)
            .filter_by(conversation_id=conversation_id, run_id=run_id)
            .one_or_none()
        )
        if existing is not None:
            return
        session.add(ChatRunWatchRecord(conversation_id=conversation_id, run_id=run_id, language=language))
        session.commit()


def remove_watch(conversation_id: str, run_id: str) -> bool:
    """Forget the run (its notice was delivered, or the conversation
    stopped or deleted the run itself). False when nothing was watched."""
    from src.storage import ChatRunWatchRecord

    with _session() as session:
        deleted = (
            session.query(ChatRunWatchRecord)
            .filter_by(conversation_id=conversation_id, run_id=run_id)
            .delete(synchronize_session=False)
        )
        session.commit()
        return bool(deleted)


def watches(conversation_id: str) -> List[Dict[str, Any]]:
    """The runs the conversation waits for, oldest first."""
    from src.storage import ChatRunWatchRecord

    with _session() as session:
        rows = (
            session.query(ChatRunWatchRecord)
            .filter_by(conversation_id=conversation_id)
            .order_by(ChatRunWatchRecord.id)
            .all()
        )
        return [_watch_view(row) for row in rows]


def conversations_watching(run_id: str) -> List[str]:
    """The ids of the conversations waiting for the run."""
    from src.storage import ChatRunWatchRecord

    with _session() as session:
        rows = (
            session.query(ChatRunWatchRecord.conversation_id)
            .filter_by(run_id=run_id)
            .order_by(ChatRunWatchRecord.id)
            .all()
        )
        return list(dict.fromkeys(row[0] for row in rows))


def conversations_with_watches() -> List[str]:
    """Every conversation that waits for at least one run (startup
    catch-up)."""
    from src.storage import ChatRunWatchRecord

    with _session() as session:
        rows = session.query(ChatRunWatchRecord.conversation_id).distinct().all()
        return [row[0] for row in rows]

