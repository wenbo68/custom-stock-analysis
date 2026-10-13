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
- **Context limit and compaction** (owner request 2026-10-13, after
  Claude Code's ``/context`` and autocompact). Before every model
  call the request is sized against the model's max
  (src/chat/context.py). Past ``COMPACT_AT_PERCENT`` of it, the loop
  first has the model summarize the conversation (src/chat/compact.py)
  and stores the summary as a ``summary`` row; from then on the model's
  view starts at that row. Once per turn at most, never while a held
  call waits. ``compact`` does the same on request (the page's
  ``/compact``); ``context_usage`` is the page's ``/context``.
- **The chosen language.** Each turn carries the language the user chose
  for the app; the prompt names it, and a final reply written in another
  script is stored with the notice ``wrong_language`` and sent back with
  a correction line (not stored — it is in the call's transcript) up to
  ``LANGUAGE_RETRY_LIMIT`` times (src/chat/language.py).

- **Stop.** The page's send button turns into a stop button while a
  turn runs (owner request 2026-10-12, after Claude Code's Esc). ``stop``
  raises the turn's flag; the loop checks it after every model call
  and before every tool. A model call in flight is never cut short:
  the loop waits for its reply and stores it with its token counts,
  so what the page shows as spent is what the provider billed, with
  every provider alike (owner decision 2026-10-12 — a provider may bill
  a cancelled stream in full anyway, Gemini does). Then the reply's
  tool calls, and any not yet run under a tool, are answered with a
  ``stopped`` error result instead of run, so the provider sees no
  unanswered call; a call that would have been held for a yes is
  answered the same way, not held. Last comes a ``stopped`` row,
  which the model sees as the user saying the reply was stopped — so
  the stopped turn stays in the context as what it was, and the model
  does not pick the old work back up on the next message unless
  asked. A stop that lands while the final reply (one asking for no
  tool) is being written cuts nothing: that reply is whole and stands,
  and the ``stopped`` row that follows says so (``STOPPED_LATE_MESSAGE``)
  — the page tells the user that was the last step. The page's stopped
  line names the step the stop landed on and what the next steps would
  have been (the answered calls), so the answered calls are stored as
  tool rows but not shown as steps.

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
from dataclasses import dataclass, field
from typing import Callable, Tuple, Any, Dict, List, Optional

from src.tiered_analysis.run_context import llm_model
from src.tiered_analysis.server_status import server_status

from . import store
from .compact import (
    SUMMARY_ROLE, TRIGGER_AUTO, TRIGGER_MANUAL, after_last_summary, is_boundary, summary_for_model,
    summary_instruction,
)
from .context import ContextLimit, ContextUsage, chars_per_token, context_limit, measure
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

#: The row that ends a stopped turn. Stored under its own role, as the
#: page labels it, so it is neither one of the user's inputs (the
#: sidebar counts those) nor a bot step; ``model_view`` hands it to the
#: model as a user line, which is what it is.
STOPPED_ROLE = "stopped"
STOPPED_MESSAGE = (
    "[The user stopped this reply before it finished. Wait for the user's "
    "next message; do not continue the stopped work unless asked.]"
)
#: The same row when the stop landed on the final reply: nothing was cut
#: short, and the model should not think it was.
STOPPED_LATE_MESSAGE = (
    "[The user asked to stop this reply, but it had already finished; "
    "nothing was cut short. Wait for the user's next message.]"
)


class ConversationBusyError(RuntimeError):
    """A turn is already running for this conversation."""


class UnknownConversationError(KeyError):
    pass


class ConfirmationPendingError(RuntimeError):
    """A held action must be answered before a new message is taken."""


class NothingPendingError(RuntimeError):
    """``confirm`` was called with no action held."""


class NothingToCompactError(RuntimeError):
    """``compact`` was called on a conversation the model sees nothing of."""


def starts_turn(message: Dict[str, Any]) -> bool:
    """A row a turn starts at, for ``trim_history``: the user's line,
    or a summary row that stood and stands in for everything before
    it. A failed summary row is nothing to the model, so it starts no
    turn — else the window could open on it and hold no user line."""
    return message.get("role") == "user" or is_boundary(message)


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


def model_view(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A stored message cut down to what the provider may see. The
    ``stopped`` row goes as a user line; so does a summary row, with
    its preface. A summary row that failed is nothing to the model
    (None)."""
    view = {key: message[key] for key in MODEL_KEYS if message.get(key) is not None}
    if view.get("role") == STOPPED_ROLE:
        view["role"] = "user"
    elif view.get("role") == SUMMARY_ROLE:
        if message.get("error") or not view.get("content"):
            return None
        view["role"] = "user"
        view["content"] = summary_for_model(str(view["content"]))
    return view


def trim_history(messages: List[Dict[str, Any]], limit: int = HISTORY_MESSAGE_LIMIT) -> List[Dict[str, Any]]:
    """The most recent turn whole — from the last user message to the
    end, even when the turn alone runs past ``limit`` — then older
    turns, whole, newest first, while the total fits in ``limit``. A
    turn starts at its user message (or at a summary row, which stands
    for all the turns before it), so no tool result arrives without
    its call. Nothing when there is no user message at all.

    Why not simply the last ``limit`` rows advanced to a user row: one
    turn of eight tool-calling replies with several calls each is more
    than 40 rows, and that window then held no user row — the model got
    the system prompt and nothing else (2026-10-10)."""
    turn_starts = [index for index, message in enumerate(messages) if starts_turn(message)]
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


@dataclass(frozen=True)
class Request:
    """One model call's input: the system prompt first, then the
    stored rows the model may see (``history``, after the newest
    summary and within ``HISTORY_MESSAGE_LIMIT``) as the provider sees
    them, then the correction line when there is one. ``base`` is the
    same without the correction — what a summary request builds on."""

    messages: List[Dict[str, Any]]
    base: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]
    history: List[Dict[str, Any]] = field(default_factory=list)


def current_limit() -> ContextLimit:
    """The configured model's limit (src/chat/context.py)."""
    return context_limit(llm_model())


class ChatHarness:
    def __init__(self, model: ModelClient, catalog: Optional[ToolCatalog] = None,
                 limit: Callable[[], ContextLimit] = current_limit) -> None:
        self._model = model
        self._catalog = catalog or ToolCatalog()
        #: How much a request may hold; tests hand in a fixed one.
        self._limit = limit
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        #: The stop flag of each turn in flight, by conversation; a turn
        #: makes its own on entry and takes it away on exit, so a stop
        #: that lands between turns raises a flag nobody reads.
        self._stops: Dict[str, threading.Event] = {}

    # -- public ---------------------------------------------------------

    def send(self, conversation_id: str, text: str, language: str = DEFAULT_LANGUAGE) -> None:
        """Store the user's message and run the loop until it rests.
        ``language`` is the one the user chose for the app; the bot
        answers in it."""
        with self._turn(conversation_id) as turn, using_turn_language(language):
            if store.get_pending(conversation_id):
                raise ConfirmationPendingError(conversation_id)
            store.append_message(conversation_id, {"role": "user", "content": text})
            self._loop(conversation_id, tool_calls=0, language=language, stop=turn.stop)

    def stop(self, conversation_id: str) -> bool:
        """Ask the turn running on the conversation to stop (see the
        module notes): True when one was running, False when nothing
        was — the turn may just have ended, which is no error.
        ``UnknownConversationError`` for an id that does not exist."""
        with self._locks_guard:
            flag = self._stops.get(conversation_id)
        if flag is None:
            if not store.conversation_exists(conversation_id):
                raise UnknownConversationError(conversation_id)
            return False
        flag.set()
        return True

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
        with self._turn(conversation_id) as turn, using_turn_language(language):
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
            self._loop(conversation_id, tool_calls=int(pending.get("tool_calls", 0)),
                       language=language, stop=turn.stop)

    def compact(self, conversation_id: str, language: str = DEFAULT_LANGUAGE) -> bool:
        """Summarize the conversation now (the page's ``/compact``): one
        model call, stored as a summary row (src/chat/compact.py). True
        when the summary stands, False when the call failed and the
        row says so. Refused while a held call waits
        (``ConfirmationPendingError``) and when the model sees nothing
        to summarize (``NothingToCompactError``)."""
        with self._turn(conversation_id) as turn, using_turn_language(language):
            if store.get_pending(conversation_id):
                raise ConfirmationPendingError(conversation_id)
            request = self._request(conversation_id, language)
            if not request.history:
                raise NothingToCompactError(conversation_id)
            stood = self._compact(conversation_id, language, TRIGGER_MANUAL, request)
            if turn.stop.is_set():
                # The summary call was the whole turn and ran to its
                # end: nothing was cut short, and the row says so.
                self._store_stopped(conversation_id, late=True)
            return stood

    def context_usage(self, conversation_id: Optional[str], language: str = DEFAULT_LANGUAGE) -> ContextUsage:
        """How much of the model's context the next request would take
        (the page's ``/context``): the conversation's, or with None
        the standing instructions and tool menu alone. Read without
        the turn lock — a turn in flight only makes it a moment stale.
        ``UnknownConversationError`` for an id that does not exist."""
        if conversation_id is not None and not store.conversation_exists(conversation_id):
            raise UnknownConversationError(conversation_id)
        return self._measure(self._request(conversation_id, language))

    # -- the loop -------------------------------------------------------

    def _loop(self, conversation_id: str, tool_calls: int, language: str,
              stop: threading.Event) -> None:
        """``tool_calls`` counts the model replies that asked for tools in
        this turn, against ``TOOL_CALL_LIMIT``. A final reply in the wrong
        language goes back with a correction, ``LANGUAGE_RETRY_LIMIT``
        times at most; after that the last reply stands, with its notice.
        ``stop`` is the turn's stop flag (see the module notes): checked
        after every model call and before every tool, never during a
        call — the step in flight finishes and is stored."""
        language_retries = 0
        correction: Optional[str] = None
        #: One summary per turn at most, whether it stood or failed.
        compacted = False
        while True:
            request = self._request(conversation_id, language, correction)
            if not compacted and self._measure(request).needs_compaction:
                compacted = True
                stood = self._compact(conversation_id, language, TRIGGER_AUTO, request)
                if stop.is_set():
                    # The summary was the step the stop landed on.
                    self._store_stopped(conversation_id)
                    return
                if stood:
                    # The summary stands for the reply a correction was
                    # about, so the correction goes with it; a failed
                    # summary changes nothing and the request stands.
                    request = self._request(conversation_id, language)
            correction = None
            reply = self._ask_model(conversation_id, language, request)
            if reply is None:
                return
            if not reply.tool_calls:
                if stop.is_set():
                    # A stop during the final reply cuts nothing: the
                    # reply is whole, so it stands (even in the wrong
                    # language — no retry is sent), and the row says so.
                    self._store_stopped(conversation_id, late=True)
                    return
                if matches_language(reply.content, language) or language_retries >= LANGUAGE_RETRY_LIMIT:
                    return
                language_retries += 1
                correction = correction_message(language)
                continue
            if stop.is_set():
                # Stopped while the model was thinking: its reply stands,
                # tokens and all; its calls are answered, not run.
                self._answer_stopped(conversation_id, [
                    (str(call.get("id") or ""), str((call.get("function") or {}).get("name") or ""), None)
                    for call in reply.tool_calls
                ])
                self._store_stopped(conversation_id)
                return
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
                if stop.is_set():
                    self._answer_stopped(conversation_id, [(call_id, name, None)])
                    continue
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
            if stop.is_set():
                # Stopped under a tool: the calls that would have waited
                # for a yes are answered too, not held.
                self._answer_stopped(conversation_id, [(c.call_id, c.name, c.input) for c in held])
                self._store_stopped(conversation_id)
                return
            if held:
                store.set_pending(conversation_id, {"calls": [c.to_dict() for c in held], "tool_calls": tool_calls})
                return

    def _answer_stopped(self, conversation_id: str,
                        calls: List[Tuple[str, str, Optional[Dict[str, Any]]]]) -> None:
        """Answer each (call_id, name, input) with the ``stopped`` error
        result: the user stopped the turn before the call ran."""
        for call_id, name, inputs in calls:
            self._store_tool_result(
                conversation_id, call_id, name,
                {"error": "stopped", "message": "the user stopped the reply before this call ran; it was not run"},
                input=inputs,
            )

    @staticmethod
    def _store_stopped(conversation_id: str, late: bool = False) -> None:
        """The row that ends a stopped turn (``STOPPED_ROLE``); ``late``
        when the stop landed on the final reply and cut nothing."""
        store.append_message(conversation_id, {
            "role": STOPPED_ROLE, "content": STOPPED_LATE_MESSAGE if late else STOPPED_MESSAGE,
        })

    def _request(self, conversation_id: Optional[str], language: str,
                 correction: Optional[str] = None) -> Request:
        """What the next model call would be sent (see ``Request``).
        ``correction`` is the retry's line after a wrong-language reply,
        sent as the last user message and kept only in the transcript.
        With no conversation, the system prompt and tool menu alone."""
        stored = store.messages(conversation_id) if conversation_id is not None else []
        history = trim_history(after_last_summary(stored))
        base = [{"role": "system", "content": system_prompt(server_status(), language)}]
        base.extend(view for view in (model_view(m) for m in history) if view is not None)
        messages = base + ([{"role": "user", "content": correction}] if correction else [])
        return Request(messages=messages, base=base, tools=self._catalog.specs(), history=history)

    def _measure(self, request: Request) -> ContextUsage:
        """The request against the model's limit, at the ratio the
        newest stored reply measured (src/chat/context.py)."""
        ratio, calibrated = chars_per_token(request.history)
        return measure(self._limit(), request.messages, request.tools, ratio, calibrated)

    def _compact(self, conversation_id: str, language: str, trigger: str, request: Request) -> bool:
        """The summary call (src/chat/compact.py): the request's rows
        plus the summary instruction, tools offered but refused. Stored
        as a summary row either way — with the text, or with the error
        when the call failed or wrote nothing — carrying what it stands
        for under ``compacted``. True when the summary stands. Nothing
        happens, and False, when the model sees no rows at all."""
        if not request.history:
            return False
        messages = request.base + [{"role": "user", "content": summary_instruction(language)}]
        usage = self._measure(request)
        compacted = {
            "trigger": trigger,
            "first_seq": request.history[0].get("seq"),
            "last_seq": request.history[-1].get("seq"),
            "tokens_before": usage.used_tokens,
        }
        transcript: Dict[str, Any] = {
            "input": render_prompt(messages, request.tools), "output": None, "temperature": CHAT_TEMPERATURE,
        }
        started = time.monotonic()
        try:
            reply = self._model.complete(messages, request.tools, tool_choice="none")
        except Exception as exc:
            logger.warning("chat summary call failed for %s: %s", conversation_id, exc)
            store.append_message(conversation_id, {
                "role": SUMMARY_ROLE, "content": None, "error": str(exc), "compacted": compacted,
                "time_ms": int((time.monotonic() - started) * 1000), "transcript": transcript,
            })
            return False
        summary = (reply.content or "").strip()
        message: Dict[str, Any] = {
            "role": SUMMARY_ROLE, "content": summary or None, "compacted": compacted,
            "time_ms": int((time.monotonic() - started) * 1000),
            "transcript": {**transcript, "output": render_reply(reply.content, reply.tool_calls)},
        }
        if not summary:
            message["error"] = "the model wrote no summary"
        if reply.input_tokens is not None or reply.output_tokens is not None:
            message["usage"] = {"input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens}
        if reply.llm:
            message["llm"] = reply.llm
        store.append_message(conversation_id, message)
        return bool(summary)

    def _ask_model(self, conversation_id: str, language: str, request: Request) -> Optional[ModelReply]:
        """One model call, stored as an assistant message. A failed call
        is stored as an assistant message carrying the error, and None
        is returned so the loop rests; the user can simply write again.
        Either way the message keeps the call's transcript (the exact
        input, the raw output, the time it took) for the page. A final
        reply in the wrong language is stored with the notice
        ``wrong_language``."""
        messages, tools = request.messages, request.tools
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
        return _Turn(self._lock_for(conversation_id), conversation_id, self._stops, self._locks_guard)


class _Turn:
    """Context manager: the conversation's lock, refused when held. The
    conversation is looked up under the lock, so a delete cannot slip
    in between the check and the turn (2026-10-10). The turn's stop
    flag (``stop``) is registered for ``ChatHarness.stop`` to raise and
    taken away again on exit."""

    def __init__(self, lock: threading.Lock, conversation_id: str,
                 stops: Dict[str, threading.Event], stops_guard: threading.Lock) -> None:
        self._lock = lock
        self._conversation_id = conversation_id
        self._stops = stops
        self._stops_guard = stops_guard
        self.stop = threading.Event()

    def __enter__(self) -> "_Turn":
        if not self._lock.acquire(blocking=False):
            raise ConversationBusyError(self._conversation_id)
        if not store.conversation_exists(self._conversation_id):
            self._lock.release()
            raise UnknownConversationError(self._conversation_id)
        with self._stops_guard:
            self._stops[self._conversation_id] = self.stop
        return self

    def __exit__(self, *_: Any) -> None:
        with self._stops_guard:
            if self._stops.get(self._conversation_id) is self.stop:
                del self._stops[self._conversation_id]
        self._lock.release()
