# -*- coding: utf-8 -*-
"""Chat API (2026-09-21): conversations with the app's chat bot.

A conversation is created empty, then each `POST .../messages` stores
the user's text, runs the bot's loop (src/chat/harness.py) — the
model may call tools, whose calls and results become messages too —
and answers with the whole conversation. When the model wants to do
something that needs the user's yes (start or delete a run, read a
large payload into the model), the answer carries `pending` and the
loop rests until `POST .../confirm` resolves it.

The bot uses the configured model (`MAIN_LLM`, `LLM_API_KEY`), the same
as the analysis: with no model set, sending a message is a 400.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from api.v1.endpoints.chat_schemas import (
    ConfirmRequest,
    ConversationDeleted,
    ConversationList,
    ConversationView,
    SendMessageRequest,
    TurnStopped,
)
from api.v1.endpoints.tiered_schemas import TranscriptCall
from src.chat import store
from src.chat.harness import (
    ChatHarness,
    ConfirmationPendingError,
    ConversationBusyError,
    NothingPendingError,
    UnknownConversationError,
)
from src.chat.model import LiteLlmClient
from src.chat.transcript import transcript_chars, transcript_view
from src.tiered_analysis.run_context import llm_model

logger = logging.getLogger(__name__)

router = APIRouter()

#: The one harness this process runs; tests replace it with one built
#: on a scripted model.
harness = ChatHarness(LiteLlmClient())


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _message_view(message: Dict[str, Any]) -> Dict[str, Any]:
    role = message.get("role")
    view: Dict[str, Any] = {
        "seq": message.get("seq"), "role": role, "created_at": message.get("created_at"),
    }
    if role == "tool":
        # Named as the chat page labels them: name, input, output.
        view.update({
            "tool_call_id": message.get("tool_call_id"),
            "name": message.get("name"),
            "output": _parse_json(message.get("content")),
            "output_chars": message.get("output_chars"),
            "truncated": message.get("truncated"),
            "approved": message.get("approved"),
            "time_ms": message.get("time_ms"),
            "input": message.get("input"),
        })
        return view
    view["text"] = message.get("content")
    if role == "assistant":
        view["tool_calls"] = [
            {
                "id": call.get("id"),
                "name": (call.get("function") or {}).get("name"),
                "arguments": _arguments_of(call),
            }
            for call in message.get("tool_calls") or []
        ]
        view["usage"] = message.get("usage")
        view["llm"] = message.get("llm")
        view["error"] = message.get("error")
        view["notice"] = message.get("notice")
        view["time_ms"] = message.get("time_ms")
        view["transcript_chars"] = transcript_chars(message)
    return view


def _arguments_of(call: Dict[str, Any]) -> Dict[str, Any]:
    parsed = _parse_json((call.get("function") or {}).get("arguments"))
    return parsed if isinstance(parsed, dict) else {}


def _pending_view(pending: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    calls = (pending or {}).get("calls") or []
    if not calls:
        return None
    return {"calls": [
        {"call_id": c.get("call_id"), "name": c.get("name"),
         "input": c.get("input") or {}, "facts": c.get("facts") or {}}
        for c in calls
    ]}


def _conversation_view(conversation_id: str) -> Dict[str, Any]:
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        **{k: v for k, v in conversation.items() if k not in ("messages", "pending")},
        "messages": [_message_view(m) for m in conversation["messages"]],
        "pending": _pending_view(conversation.get("pending")),
    }


def _require_llm_configured() -> None:
    if llm_model() is None:
        raise HTTPException(status_code=400, detail={
            "error": "llm_not_configured",
            "message": "set MAIN_LLM and LLM_API_KEY in .env first",
        })


@router.get("/conversations", response_model=ConversationList)
def list_conversations() -> Dict[str, List[Dict[str, Any]]]:
    """Every conversation, most recently touched first."""
    return {"items": store.list_conversations()}


@router.post("/conversations", status_code=201, response_model=ConversationView)
def create_conversation() -> Dict[str, Any]:
    """A new, empty conversation."""
    created = store.create_conversation()
    return _conversation_view(created["id"])


@router.get("/conversations/{conversation_id}", response_model=ConversationView)
def get_conversation(conversation_id: str) -> Dict[str, Any]:
    """The conversation with its messages and any pending action. 404 for an unknown id."""
    return _conversation_view(conversation_id)


@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleted)
def delete_conversation(conversation_id: str) -> Dict[str, str]:
    """Remove the conversation and its messages. 404 for an unknown id;
    409 `busy` while a turn is running on it (try again when it ends)."""
    try:
        deleted = harness.delete_conversation(conversation_id)
    except ConversationBusyError:
        raise HTTPException(status_code=409, detail={"code": "busy"})
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"id": conversation_id}


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationView)
def send_message(conversation_id: str, request: SendMessageRequest) -> Dict[str, Any]:
    """Send a message and run the bot until it answers or needs a yes.
    The bot answers in `language`, the one the user chose for the app.

    Answers with the whole conversation; read `pending` for a held
    action. Errors: 400 `llm_not_configured`; 404 unknown conversation;
    409 `busy` (a turn is already running) or 409
    `confirmation_pending` (answer the held action first).
    """
    _require_llm_configured()
    try:
        harness.send(conversation_id, request.text, request.language)
    except UnknownConversationError:
        raise HTTPException(status_code=404, detail="conversation not found")
    except ConversationBusyError:
        raise HTTPException(status_code=409, detail={"code": "busy"})
    except ConfirmationPendingError:
        raise HTTPException(status_code=409, detail={"code": "confirmation_pending"})
    return _conversation_view(conversation_id)


@router.post("/conversations/{conversation_id}/confirm", response_model=ConversationView)
def confirm_action(conversation_id: str, request: ConfirmRequest) -> Dict[str, Any]:
    """Answer the held action (yes runs it, no records the refusal) and
    resume the bot. 409 `nothing_pending` when no action is held."""
    _require_llm_configured()
    try:
        harness.confirm(conversation_id, request.approved, request.language)
    except UnknownConversationError:
        raise HTTPException(status_code=404, detail="conversation not found")
    except ConversationBusyError:
        raise HTTPException(status_code=409, detail={"code": "busy"})
    except NothingPendingError:
        raise HTTPException(status_code=409, detail={"code": "nothing_pending"})
    return _conversation_view(conversation_id)


@router.post("/conversations/{conversation_id}/stop", response_model=TurnStopped)
def stop_turn(conversation_id: str) -> Dict[str, Any]:
    """Stop the turn running on the conversation (the page's stop button).
    Answers at once; the turn's own `POST .../messages` or `.../confirm`
    request then returns the conversation as stopped: the model call
    in flight abandoned, tool calls not yet run answered with a
    `stopped` error, and a `stopped` row at the end. `stopped` is false
    when nothing was running. 404 for an unknown conversation."""
    try:
        stopped = harness.stop(conversation_id)
    except UnknownConversationError:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"id": conversation_id, "stopped": stopped}


@router.get("/conversations/{conversation_id}/messages/{seq}/transcript", response_model=TranscriptCall)
def get_message_transcript(conversation_id: str, seq: int) -> Dict[str, Any]:
    """One bot reply's model call — the exact input it was sent, the raw
    output, the llm, time and tokens — in the same shape as a run's
    `GET /tiered/runs/{run_id}/transcript/{call_number}`. 404 for an unknown
    conversation or a message that holds no model call (user lines and
    tool results)."""
    if not store.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    message = store.message(conversation_id, seq)
    view = transcript_view(message) if message is not None else None
    if view is None:
        raise HTTPException(status_code=404, detail="no model call on this message")
    return view
