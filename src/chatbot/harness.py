# -*- coding: utf-8 -*-
"""The agent loop ("harness"): send the conversation to the model, run
the tools it asks for, feed the results back, repeat — until the model
answers in plain text, a step cap stops it, or an action needs the
user's yes.

Guardrails (owner discussion 2026-09-19):

- **Step cap.** At most ``MAX_TOOL_ROUNDS`` model calls that ask for
  tools per user message, so a confused model cannot poll forever. The
  cap leaves a visible note in the conversation.
- **Every tool answers.** Unknown tools, bad arguments, refusals and
  misses all come back to the model as readable results, never as
  exceptions, so it can explain them.
- **Confirmation before actions and large reads.** A tool with a
  ``confirm`` is held as *pending* on the conversation; the loop stops,
  the page asks the user, and ``confirm`` resumes it with the answer.
- **Result size limit.** A tool result over ``RESULT_CHAR_CAP`` is cut,
  with a note, before the model sees it.
- **A visible trace.** Every tool call and result is a stored message
  the page shows.
- **Context budgeting.** Only the last ``HISTORY_MESSAGE_LIMIT``
  messages go to the model, cut at a user-message boundary so a tool
  result never arrives without the call it answers.

One turn runs at a time per conversation; a second request while one
is in flight is refused (``ConversationBusyError``).
"""
from __future__ import annotations

import json
import logging
import time
import threading
from dataclasses import dataclass
from typing import Tuple, Any, Dict, List, Optional

from src.tiered_analysis.server_status import server_status

from . import store
from .model import CHAT_TEMPERATURE, ModelClient, ModelReply
from .transcript import render_prompt, render_reply
from .prompt import system_prompt
from .tools import ToolCatalog

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
RESULT_CHAR_CAP = 40_000
HISTORY_MESSAGE_LIMIT = 40

#: The keys a stored message may carry to the model; everything else
#: (usage, sizes, errors, approval, the call's transcript) is for the page.
MODEL_KEYS = ("role", "content", "tool_calls", "tool_call_id", "name")


class ConversationBusyError(RuntimeError):
    """A turn is already running for this conversation."""


class UnknownConversationError(KeyError):
    pass


class ConfirmationPendingError(RuntimeError):
    """A held action must be answered before a new message is taken."""


class NothingPendingError(RuntimeError):
    """``confirm`` was called with no action held."""


@dataclass(frozen=True)
class PendingCall:
    call_id: str
    name: str
    args: Dict[str, Any]
    #: What the page words the question with (see tools.py confirmers).
    facts: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"call_id": self.call_id, "name": self.name, "args": self.args, "facts": self.facts}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PendingCall":
        return cls(
            call_id=str(raw.get("call_id") or ""), name=str(raw.get("name") or ""),
            args=dict(raw.get("args") or {}), facts=dict(raw.get("facts") or {}),
        )


def model_view(message: Dict[str, Any]) -> Dict[str, Any]:
    """A stored message cut down to what the provider may see."""
    return {key: message[key] for key in MODEL_KEYS if message.get(key) is not None}


def trim_history(messages: List[Dict[str, Any]], limit: int = HISTORY_MESSAGE_LIMIT) -> List[Dict[str, Any]]:
    """The last ``limit`` messages, then advanced to the first user
    message so no tool result arrives without its call."""
    kept = messages[-limit:] if len(messages) > limit else list(messages)
    while kept and kept[0].get("role") != "user":
        kept.pop(0)
    return kept


def cap_result(result: Dict[str, Any], cap: int = RESULT_CHAR_CAP) -> Dict[str, Any]:
    """The result as the tool message's text, cut with a note when it
    is over the cap: {content, chars, truncated}."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    chars = len(text)
    if chars <= cap:
        return {"content": text, "chars": chars, "truncated": False}
    note = f'... [cut: {chars} characters, the first {cap} shown]'
    return {"content": text[:cap] + note, "chars": chars, "truncated": True}


class ChatHarness:
    def __init__(self, model: ModelClient, catalog: Optional[ToolCatalog] = None) -> None:
        self._model = model
        self._catalog = catalog or ToolCatalog()
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # -- public ---------------------------------------------------------

    def send(self, conversation_id: str, text: str) -> None:
        """Store the user's message and run the loop until it rests."""
        with self._turn(conversation_id):
            if store.get_pending(conversation_id):
                raise ConfirmationPendingError(conversation_id)
            store.append_message(conversation_id, {"role": "user", "content": text})
            self._loop(conversation_id, rounds=0)

    def confirm(self, conversation_id: str, approved: bool) -> None:
        """Answer the first held action: run it (or record the refusal),
        then resume the loop once nothing else is held."""
        with self._turn(conversation_id):
            pending = store.get_pending(conversation_id)
            if not pending or not pending.get("calls"):
                raise NothingPendingError(conversation_id)
            calls = [PendingCall.from_dict(c) for c in pending["calls"]]
            call, remaining = calls[0], calls[1:]
            tool = self._catalog.get(call.name)
            duration_ms: Optional[int] = None
            if not approved:
                result: Dict[str, Any] = {"declined": True, "message": "The user declined this action. Do not retry it unless asked."}
            elif tool is None:
                result = {"error": "unknown_tool", "message": f"no tool named {call.name}"}
            else:
                params, problem = tool.parse(call.args)
                if problem is not None:
                    result = problem
                else:
                    result, duration_ms = self._execute(tool, params)
            self._store_tool_result(conversation_id, call.call_id, call.name, result,
                                    approved=approved, duration_ms=duration_ms)
            if remaining:
                store.set_pending(conversation_id, {
                    "calls": [c.to_dict() for c in remaining], "rounds": pending.get("rounds", 0),
                })
                return
            store.set_pending(conversation_id, None)
            self._loop(conversation_id, rounds=int(pending.get("rounds", 0)))

    # -- the loop -------------------------------------------------------

    def _loop(self, conversation_id: str, rounds: int) -> None:
        while True:
            reply = self._ask_model(conversation_id)
            if reply is None:
                return
            if not reply.tool_calls:
                return
            if rounds >= MAX_TOOL_ROUNDS:
                store.append_message(conversation_id, {
                    "role": "assistant",
                    "content": f"I stopped after {MAX_TOOL_ROUNDS} rounds of tool calls in this turn. Ask again to continue.",
                    "notice": "step_cap",
                })
                return
            rounds += 1
            held: List[PendingCall] = []
            for call in reply.tool_calls:
                call_id = str(call.get("id") or "")
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                tool = self._catalog.get(name)
                if tool is None:
                    self._store_tool_result(conversation_id, call_id, name,
                                            {"error": "unknown_tool", "message": f"no tool named {name}"})
                    continue
                params, problem = tool.parse(function.get("arguments"))
                if problem is not None:
                    self._store_tool_result(conversation_id, call_id, name, problem)
                    continue
                if tool.confirm is not None:
                    facts = self._guard(tool.confirm, params, name)
                    if "error" in facts:
                        self._store_tool_result(conversation_id, call_id, name, facts)
                        continue
                    held.append(PendingCall(call_id, name, params.model_dump(mode="json"), facts))
                    continue
                result, duration_ms = self._execute(tool, params)
                self._store_tool_result(conversation_id, call_id, name, result, duration_ms=duration_ms)
            if held:
                store.set_pending(conversation_id, {"calls": [c.to_dict() for c in held], "rounds": rounds})
                return

    def _ask_model(self, conversation_id: str) -> Optional[ModelReply]:
        """One model call, stored as an assistant message. A failed call
        is stored as an assistant message carrying the error, and None
        is returned so the loop rests; the user can simply write again.
        Either way the message keeps the call's transcript (the exact
        prompt, the raw reply, the time it took) for the page."""
        history = trim_history(store.messages(conversation_id))
        messages = [{"role": "system", "content": system_prompt(server_status())}]
        messages.extend(model_view(m) for m in history)
        tools = self._catalog.specs()
        transcript: Dict[str, Any] = {
            "prompt": render_prompt(messages, tools), "reply": None, "temperature": CHAT_TEMPERATURE,
        }
        started = time.monotonic()
        try:
            reply = self._model.complete(messages, tools)
        except Exception as exc:
            logger.warning("chat model call failed for %s: %s", conversation_id, exc)
            store.append_message(conversation_id, {
                "role": "assistant", "content": f"The model call failed: {exc}", "error": str(exc),
                "duration_ms": int((time.monotonic() - started) * 1000), "transcript": transcript,
            })
            return None
        message: Dict[str, Any] = {
            "role": "assistant", "content": reply.content,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "transcript": {**transcript, "reply": render_reply(reply.content, reply.tool_calls)},
        }
        if reply.tool_calls:
            message["tool_calls"] = reply.tool_calls
        if reply.prompt_tokens is not None or reply.completion_tokens is not None:
            message["usage"] = {"prompt_tokens": reply.prompt_tokens,
                                "completion_tokens": reply.completion_tokens}
        if reply.model:
            message["model"] = reply.model
        store.append_message(conversation_id, message)
        return reply

    def _execute(self, tool: Any, params: Any) -> Tuple[Dict[str, Any], int]:
        """Run the tool; its result and how long it took (for the page)."""
        started = time.monotonic()
        result = self._guard(tool.run, params, tool.name)
        return result, int((time.monotonic() - started) * 1000)

    @staticmethod
    def _guard(fn: Any, params: Any, name: str) -> Dict[str, Any]:
        """A tool that raises answers with an error result instead."""
        try:
            result = fn(params)
        except Exception as exc:
            logger.exception("chat tool %s failed", name)
            return {"error": "tool_failed", "message": f"{type(exc).__name__}: {exc}"}
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _store_tool_result(conversation_id: str, call_id: str, name: str,
                           result: Dict[str, Any], approved: Optional[bool] = None,
                           duration_ms: Optional[int] = None) -> None:
        """Store a tool's answer. ``duration_ms`` is how long the tool ran,
        None when nothing ran (an unknown tool, bad arguments, a refusal)."""
        capped = cap_result(result)
        message: Dict[str, Any] = {
            "role": "tool", "tool_call_id": call_id, "name": name,
            "content": capped["content"], "chars": capped["chars"],
            "truncated": capped["truncated"],
        }
        if approved is not None:
            message["approved"] = approved
        if duration_ms is not None:
            message["duration_ms"] = duration_ms
        store.append_message(conversation_id, message)

    # -- locking --------------------------------------------------------

    def _turn(self, conversation_id: str) -> "_Turn":
        if not store.conversation_exists(conversation_id):
            raise UnknownConversationError(conversation_id)
        with self._locks_guard:
            lock = self._locks.setdefault(conversation_id, threading.Lock())
        return _Turn(lock, conversation_id)


class _Turn:
    """Context manager: the conversation's lock, refused when held."""

    def __init__(self, lock: threading.Lock, conversation_id: str) -> None:
        self._lock = lock
        self._conversation_id = conversation_id

    def __enter__(self) -> "_Turn":
        if not self._lock.acquire(blocking=False):
            raise ConversationBusyError(self._conversation_id)
        return self

    def __exit__(self, *_: Any) -> None:
        self._lock.release()
