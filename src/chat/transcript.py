# -*- coding: utf-8 -*-
"""What one chat model call looked like, as text (owner request
2026-09-23): the page shows it when the token line of a reply is
clicked, in the same shape as a run's LLM transcript. The input is the
whole request — every message the model was shown and the tool menu it
was offered — rendered as one readable text; the output is the text the
model wrote plus any tool calls it asked for, as JSON.

Stored on the assistant message under ``transcript`` (never one of
``harness.MODEL_KEYS``, so the model never sees its own transcript).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def render_prompt(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> str:
    """The request as one text: each message under a ``=== role ===``
    heading in order, then the tool menu under ``=== tools offered ===``."""
    parts: List[str] = []
    for message in messages:
        role = str(message.get("role") or "?")
        heading = role
        if role == "tool":
            heading = f"tool ({message.get('name') or '?'}, {message.get('tool_call_id') or '?'})"
        body: List[str] = []
        content = message.get("content")
        if content:
            body.append(str(content))
        calls = message.get("tool_calls") or []
        if calls:
            body.append("[tool calls]\n" + _dumps(calls))
        parts.append(f"=== {heading} ===\n" + ("\n".join(body) if body else "(empty)"))
    parts.append("=== tools offered ===\n" + (_dumps(tools) if tools else "(none)"))
    return "\n\n".join(parts)


def render_reply(content: Optional[str], tool_calls: List[Dict[str, Any]]) -> Optional[str]:
    """The raw answer as text: what the model wrote, then its tool calls
    as JSON. None when it produced neither."""
    parts: List[str] = []
    if content:
        parts.append(str(content))
    if tool_calls:
        parts.append("[tool calls]\n" + _dumps(tool_calls))
    return "\n\n".join(parts) if parts else None


def transcript_view(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The message's model call in the run-transcript shape (input,
    output, llm, time, tokens, error), or None for a message that holds
    no model call."""
    transcript = message.get("transcript")
    if not isinstance(transcript, dict):
        return None
    usage = message.get("usage") or {}
    return {
        "call_number": message.get("seq"),
        "created_at": message.get("created_at"),
        "stage": (
            "summary" if message.get("role") == "summary"
            else "side_question" if message.get("side_question")
            else "chat"
        ),
        "llm": message.get("llm"),
        "temperature": transcript.get("temperature"),
        "time_ms": message.get("time_ms"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "structured": None,
        "error": message.get("error"),
        "input": transcript.get("input"),
        "output": transcript.get("output"),
    }


def transcript_chars(message: Dict[str, Any]) -> Optional[int]:
    """How much text the message's transcript holds, None without one."""
    transcript = message.get("transcript")
    if not isinstance(transcript, dict):
        return None
    return len(transcript.get("input") or "") + len(transcript.get("output") or "")
