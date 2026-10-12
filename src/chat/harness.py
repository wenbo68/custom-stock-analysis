# -*- coding: utf-8 -*-
"""The agent loop ("harness"): send the conversation to the model, run
the tools it asks for, feed the results back, repeat — until the model
answers in plain text, the tool-call limit stops it, or an action needs
the user's yes.

Guardrails (owner discussion 2026-09-19):

- **Tool-call limit.** At most ``TOOL_CALL_LIMIT`` model calls that ask
  for tools per user message, so a confused model cannot poll forever.
  The limit leaves a visible note in the conversation, and the calls of
  the reply that hit it are answered with an error result rather than
  run — an unanswered call would make the provider reject every later
  request in the conversation (2026-10-10).
- **Every tool answers.** Unknown tools, bad arguments, refusals and
  misses all come back to the model as readable results, never as
  exceptions, so it can explain them.
- **Confirmation before actions and large reads.** A tool with a
  ``confirm`` is held as *pending* on the conversation; the loop stops,
  the page asks the user, and ``confirm`` resumes it with the answer.
- **Result size limit.** A tool result over ``RESULT_CHAR_CAP`` is cut,
  with a note, before the model sees it.
- **A visible trace.** Every tool call and result is a stored message
  the page shows. The tool row carries ``input`` — the inputs with
  every default filled in (``Tool.inputs``), so the page can show all
  of them, not only what the model sent (owner request 2026-09-24) —
  and ``output``, what came back. Every stored key the page reads is
  named as the page labels it (owner request 2026-09-24).
- **Context budgeting.** The model sees the most recent turn whole
  (the user's question with everything it set off, however long), then
  older turns, whole, while the total stays within
  ``HISTORY_MESSAGE_LIMIT`` messages. Cutting only at a user-message
  boundary means a tool result never arrives without its call.
- **The chosen language.** Each turn carries the language the user chose
  for the app; the prompt names it, and a final reply written in another
  script is stored with the notice ``wrong_language`` and sent back with
  a correction line (not stored — it is in the call's transcript) up to
  ``LANGUAGE_RETRY_LIMIT`` times (src/chat/language.py).

One turn runs at a time per conversation; a second request while one
is in flight is refused (``ConversationBusyError``), and so is deleting
the conversation (``delete_conversation``) — otherwise the turn would
fail halfway with its paid model call wasted (2026-10-10).
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
from .language import (
    DEFAULT_LANGUAGE, LANGUAGE_RETRY_LIMIT, correction_message, matches_language, using_turn_language,
)
from .model import CHAT_TEMPERATURE, ModelClient, ModelReply
from .transcript import render_prompt, render_reply
from .prompt import system_prompt
from .tools import ToolCatalog

logger = logging.getLogger(__name__)

TOOL_CALL_LIMIT = 8
RESULT_CHAR_CAP = 40_000
HISTORY_MESSAGE_LIMIT = 40

#: The keys a stored message may carry to the model (the provider's own
#: exchange shape, which is why these keep their wire names); everything
#: else (usage, sizes, errors, approval, the call's transcript) is for
#: the page and is named as the page labels it.
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
    #: The inputs with every default filled in (``Tool.inputs``).
    input: Dict[str, Any]
    #: What the page words the question with (see tools.py confirmers).
    facts: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"call_id": self.call_id, "name": self.name, "input": self.input, "facts": self.facts}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PendingCall":
        return cls(
            call_id=str(raw.get("call_id") or ""), name=str(raw.get("name") or ""),
            input=dict(raw.get("input") or {}), facts=dict(raw.get("facts") or {}),
        )


def model_view(message: Dict[str, Any]) -> Dict[str, Any]:
    """A stored message cut down to what the provider may see."""
    return {key: message[key] for key in MODEL_KEYS if message.get(key) is not None}


def trim_history(messages: List[Dict[str, Any]], limit: int = HISTORY_MESSAGE_LIMIT) -> List[Dict[str, Any]]:
    """The most recent turn whole — from the last user message to the
    end, even when the turn alone runs past ``limit`` — then older
    turns, whole, newest first, while the total fits in ``limit``. A
    turn starts at its user message, so no tool result arrives without
    its call. Nothing when there is no user message at all.

    Why not simply the last ``limit`` rows advanced to a user row: one
    turn of eight tool-calling replies with several calls each is more
    than 40 rows, and that window then held no user row — the model got
    the system prompt and nothing else (2026-10-10)."""
    turn_starts = [index for index, message in enumerate(messages) if message.get("role") == "user"]
    if not turn_starts:
        return []
    start = turn_starts[-1]
    for earlier in reversed(turn_starts[:-1]):
        if len(messages) - earlier > limit:
            break
        start = earlier
    return list(messages[start:])


def cap_result(result: Dict[str, Any], cap: int = RESULT_CHAR_CAP) -> Dict[str, Any]:
    """The result as the tool message's text, cut with a note when it
    is over the cap: {content, output_chars, truncated}."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    chars = len(text)
    if chars <= cap:
        return {"content": text, "output_chars": chars, "truncated": False}
    note = f'... [cut: {chars} characters, the first {cap} shown]'
    return {"content": text[:cap] + note, "output_chars": chars, "truncated": True}


class ChatHarness:
    def __init__(self, model: ModelClient, catalog: Optional[ToolCatalog] = None) -> None:
        self._model = model
        self._catalog = catalog or ToolCatalog()
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # -- public ---------------------------------------------------------

    def send(self, conversation_id: str, text: str, language: str = DEFAULT_LANGUAGE) -> None:
        """Store the user's message and run the loop until it rests.
        ``language`` is the one the user chose for the app; the bot
        answers in it."""
        with self._turn(conversation_id), using_turn_language(language):
            if store.get_pending(conversation_id):
                raise ConfirmationPendingError(conversation_id)
            store.append_message(conversation_id, {"role": "user", "content": text})
            self._loop(conversation_id, tool_calls=0, language=language)

    def delete_conversation(self, conversation_id: str) -> bool:
        """Remove the conversation and its messages. Refused
        (``ConversationBusyError``) while a turn runs on it; False for an
        unknown id. The conversation's lock entry goes with it, so the
        lock table does not grow with every conversation ever seen."""
        lock = self._lock_for(conversation_id)
        if not lock.acquire(blocking=False):
            raise ConversationBusyError(conversation_id)
        try:
            deleted = store.delete_conversation(conversation_id)
            with self._locks_guard:
                if self._locks.get(conversation_id) is lock:
                    del self._locks[conversation_id]
        finally:
            lock.release()
        return deleted

    def confirm(self, conversation_id: str, approved: bool, language: str = DEFAULT_LANGUAGE) -> None:
        """Answer the first held action: run it (or record the refusal),
        then resume the loop once nothing else is held. The answer and
        the shortened list of held calls are one write, so a crash
        between them cannot leave an already-run action held, to be
        run again on the next yes (2026-10-10)."""
        with self._turn(conversation_id), using_turn_language(language):
            pending = store.get_pending(conversation_id)
            if not pending or not pending.get("calls"):
                raise NothingPendingError(conversation_id)
            calls = [PendingCall.from_dict(c) for c in pending["calls"]]
            call, remaining = calls[0], calls[1:]
            tool = self._catalog.get(call.name)
            time_ms: Optional[int] = None
            if not approved:
                result: Dict[str, Any] = {"declined": True, "message": "The user declined this action. Do not retry it unless asked."}
            elif tool is None:
                result = {"error": "unknown_tool", "message": f"no tool named {call.name}"}
            else:
                params, problem = tool.parse(call.input)
                if problem is not None:
                    result = problem
                else:
                    result, time_ms = self._execute(tool, params)
            still_held: Optional[Dict[str, Any]] = None
            if remaining:
                still_held = {
                    "calls": [c.to_dict() for c in remaining],
                    "tool_calls": pending.get("tool_calls", 0),
                }
            self._store_tool_result(conversation_id, call.call_id, call.name, result,
                                    approved=approved, time_ms=time_ms, input=call.input,
                                    pending=still_held)
            if remaining:
                return
            self._loop(conversation_id, tool_calls=int(pending.get("tool_calls", 0)), language=language)

    # -- the loop -------------------------------------------------------

    def _loop(self, conversation_id: str, tool_calls: int, language: str) -> None:
        """``tool_calls`` counts the model replies that asked for tools in
        this turn, against ``TOOL_CALL_LIMIT``. A final reply in the wrong
        language goes back with a correction, ``LANGUAGE_RETRY_LIMIT``
        times at most; after that the last reply stands, with its notice."""
        language_retries = 0
        correction: Optional[str] = None
        while True:
            reply = self._ask_model(conversation_id, language, correction)
            correction = None
            if reply is None:
                return
            if not reply.tool_calls:
                if matches_language(reply.content, language) or language_retries >= LANGUAGE_RETRY_LIMIT:
                    return
                language_retries += 1
                correction = correction_message(language)
                continue
            if tool_calls >= TOOL_CALL_LIMIT:
                # The calls of this reply are answered, not run: a
                # provider rejects every later request that carries an
                # assistant message whose tool calls got no answer.
                for call in reply.tool_calls:
                    self._store_tool_result(
                        conversation_id, str(call.get("id") or ""),
                        str((call.get("function") or {}).get("name") or ""),
                        {"error": "tool_call_limit",
                         "message": "the tool-call limit for this turn was reached; this call was not run"},
                    )
                store.append_message(conversation_id, {
                    "role": "assistant",
                    "content": f"I stopped at my tool-call limit ({TOOL_CALL_LIMIT} tool-calling steps) in this turn. Ask again to continue.",
                    "notice": "tool_call_limit",
                })
                return
            tool_calls += 1
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
                inputs = self._guard(tool.inputs, params, name)
                if tool.confirm is not None:
                    facts = self._guard(tool.confirm, params, name)
                    if "error" in facts:
                        self._store_tool_result(conversation_id, call_id, name, facts, input=inputs)
                        continue
                    held.append(PendingCall(call_id, name, inputs, facts))
                    continue
                result, time_ms = self._execute(tool, params)
                self._store_tool_result(conversation_id, call_id, name, result,
                                        time_ms=time_ms, input=inputs)
            if held:
                store.set_pending(conversation_id, {"calls": [c.to_dict() for c in held], "tool_calls": tool_calls})
                return

    def _ask_model(self, conversation_id: str, language: str,
                   correction: Optional[str] = None) -> Optional[ModelReply]:
        """One model call, stored as an assistant message. A failed call
        is stored as an assistant message carrying the error, and None
        is returned so the loop rests; the user can simply write again.
        Either way the message keeps the call's transcript (the exact
        input, the raw output, the time it took) for the page.

        ``correction`` is the retry's line after a wrong-language reply:
        sent as the last user message, kept only in the transcript. A
        final reply that is again in the wrong language is stored with
        the notice ``wrong_language``."""
        history = trim_history(store.messages(conversation_id))
        messages = [{"role": "system", "content": system_prompt(server_status(), language)}]
        messages.extend(model_view(m) for m in history)
        if correction:
            messages.append({"role": "user", "content": correction})
        tools = self._catalog.specs()
        transcript: Dict[str, Any] = {
            "input": render_prompt(messages, tools), "output": None, "temperature": CHAT_TEMPERATURE,
        }
        started = time.monotonic()
        try:
            reply = self._model.complete(messages, tools)
        except Exception as exc:
            logger.warning("chat model call failed for %s: %s", conversation_id, exc)
            store.append_message(conversation_id, {
                "role": "assistant", "content": f"The model call failed: {exc}", "error": str(exc),
                "time_ms": int((time.monotonic() - started) * 1000), "transcript": transcript,
            })
            return None
        message: Dict[str, Any] = {
            "role": "assistant", "content": reply.content,
            "time_ms": int((time.monotonic() - started) * 1000),
            "transcript": {**transcript, "output": render_reply(reply.content, reply.tool_calls)},
        }
        if reply.tool_calls:
            message["tool_calls"] = reply.tool_calls
        elif not matches_language(reply.content, language):
            message["notice"] = "wrong_language"
        if reply.input_tokens is not None or reply.output_tokens is not None:
            message["usage"] = {"input_tokens": reply.input_tokens,
                                "output_tokens": reply.output_tokens}
        if reply.llm:
            message["llm"] = reply.llm
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
                           time_ms: Optional[int] = None,
                           input: Optional[Dict[str, Any]] = None,
                           pending: Any = store.KEEP_PENDING) -> None:
        """Store a tool's answer. ``time_ms`` is how long the tool ran,
        None when nothing ran (an unknown tool, bad arguments, a refusal).
        ``input`` is the inputs with defaults filled in, None when the
        model's arguments never parsed. ``pending`` is the held-calls
        list to write in the same commit (None clears it); left alone
        by default."""
        capped = cap_result(result)
        message: Dict[str, Any] = {
            "role": "tool", "tool_call_id": call_id, "name": name,
            "content": capped["content"], "output_chars": capped["output_chars"],
            "truncated": capped["truncated"],
        }
        if approved is not None:
            message["approved"] = approved
        if time_ms is not None:
            message["time_ms"] = time_ms
        if input is not None:
            message["input"] = input
        store.append_message(conversation_id, message, pending=pending)

    # -- locking --------------------------------------------------------

    def _lock_for(self, conversation_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(conversation_id, threading.Lock())

    def _turn(self, conversation_id: str) -> "_Turn":
        return _Turn(self._lock_for(conversation_id), conversation_id)


class _Turn:
    """Context manager: the conversation's lock, refused when held. The
    conversation is looked up under the lock, so a delete cannot slip
    in between the check and the turn (2026-10-10)."""

    def __init__(self, lock: threading.Lock, conversation_id: str) -> None:
        self._lock = lock
        self._conversation_id = conversation_id

    def __enter__(self) -> "_Turn":
        if not self._lock.acquire(blocking=False):
            raise ConversationBusyError(self._conversation_id)
        if not store.conversation_exists(self._conversation_id):
            self._lock.release()
            raise UnknownConversationError(self._conversation_id)
        return self

    def __exit__(self, *_: Any) -> None:
        self._lock.release()
