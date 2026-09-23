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
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

#: The first user message becomes the title, cut to this many characters.
TITLE_MAX_CHARS = 60


def _session():
    from src.storage import DatabaseManager

    return DatabaseManager.get_instance().get_session()


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _conversation_view(row: Any, stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        **(stats or _stats([])),
    }


def _stats(rows: List[Any]) -> Dict[str, Any]:
    """What the history rows show for a conversation (2026-09-23): how
    many messages it holds, how many of them the user sent (its
    questions), the tokens every model call cost together, and when the
    user last asked something (``None`` before the first question)."""
    question_count = 0
    total_tokens = 0
    last_question_at: Optional[datetime] = None
    for row in rows:
        if row.role == "user":
            question_count += 1
            if row.created_at is not None and (last_question_at is None or row.created_at > last_question_at):
                last_question_at = row.created_at
        elif row.role == "assistant":
            usage = (_parse(row.content_json) or {}).get("usage") or {}
            total_tokens += int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
    return {
        "message_count": len(rows),
        "question_count": question_count,
        "total_tokens": total_tokens,
        "last_question_at": _iso(last_question_at),
    }


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
    """Every conversation, most recently touched first, each with the
    facts the history rows show (``_stats``)."""
    from src.storage import ChatConversationRecord, ChatMessageRecord

    with _session() as session:
        by_conversation: Dict[str, List[Any]] = {}
        for message in session.query(ChatMessageRecord).order_by(ChatMessageRecord.seq).all():
            by_conversation.setdefault(message.conversation_id, []).append(message)
        rows = (
            session.query(ChatConversationRecord)
            .order_by(ChatConversationRecord.updated_at.desc(),
                      ChatConversationRecord.created_at.desc())
            .all()
        )
        return [_conversation_view(row, _stats(by_conversation.get(row.id, []))) for row in rows]


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
        view = _conversation_view(row, _stats(rows))
        view["messages"] = messages
        view["pending"] = _parse(row.pending_json)
        return view


def conversation_exists(conversation_id: str) -> bool:
    from src.storage import ChatConversationRecord

    with _session() as session:
        return session.get(ChatConversationRecord, conversation_id) is not None


def delete_conversation(conversation_id: str) -> bool:
    """Remove the conversation and its messages. False for an unknown id."""
    from src.storage import ChatConversationRecord, ChatMessageRecord

    with _session() as session:
        row = session.get(ChatConversationRecord, conversation_id)
        if row is None:
            return False
        (
            session.query(ChatMessageRecord)
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


def append_message(conversation_id: str, message: Dict[str, Any]) -> int:
    """Store one message (a dict in the model's shape plus any page
    facts) as the next row and touch the conversation. The first user
    message names an untitled conversation. Returns the row's seq."""
    from sqlalchemy import func

    from src.storage import ChatConversationRecord, ChatMessageRecord, utc_naive_now

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
        session.add(ChatMessageRecord(
            conversation_id=conversation_id,
            seq=seq,
            role=str(message.get("role") or ""),
            content_json=json.dumps(message, ensure_ascii=False),
        ))
        if conversation.title is None and message.get("role") == "user":
            conversation.title = _title_from(str(message.get("content") or ""))
        conversation.updated_at = utc_naive_now()
        session.commit()
        return seq


def set_pending(conversation_id: str, pending: Optional[Dict[str, Any]]) -> None:
    """Record (or, with None, clear) the tool calls waiting for the user."""
    from src.storage import ChatConversationRecord

    with _session() as session:
        row = session.get(ChatConversationRecord, conversation_id)
        if row is None:
            raise KeyError(conversation_id)
        row.pending_json = (
            json.dumps(pending, ensure_ascii=False) if pending is not None else None
        )
        session.commit()


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
