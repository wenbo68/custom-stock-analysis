# -*- coding: utf-8 -*-
"""How much of the model's context a chat request takes, against how
much it may take (owner request 2026-10-13, after Claude Code's
``/context``).

**The max.** A model reads a bounded amount of text per call, its
*context window*, measured in tokens (the chunks the provider bills
by, about four characters each). litellm ships a table of every model
it knows with that window and the model's output limit; for a model in
the table the max this chat may fill is the window minus the output
limit, so the reply always has room. For a model litellm does not know
(a local Ollama name, an OpenRouter alias) the window comes from the
``CHAT_CONTEXT_WINDOW`` variable (default ``DEFAULT_CONTEXT_WINDOW``)
and the max is half of it, since the output limit is unknown too. A
table row whose output limit is as large as the window (local models
often report that) is halved the same way, because the subtraction
would leave nothing.

**The used.** The request is text we build ourselves, so its size is
its character count divided by this model's characters-per-token. Every
stored bot reply keeps the exact text it was sent and the provider's
own count of the tokens that text was, so the ratio is measured from
the newest such reply (``chars_per_token``); before the first reply the
usual four is assumed. Gemini, OpenAI and DeepSeek tokenize
differently, which is why the ratio is learned rather than fixed.

**The trigger.** Past ``COMPACT_AT_PERCENT`` of the max the harness
summarizes the conversation by itself (src/chat/compact.py).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .transcript import render_prompt

logger = logging.getLogger(__name__)

#: The window, in tokens, of a model litellm does not know.
CONTEXT_WINDOW_ENV = "CHAT_CONTEXT_WINDOW"
DEFAULT_CONTEXT_WINDOW = 128_000
#: Assumed until the first reply's receipt says otherwise.
DEFAULT_CHARS_PER_TOKEN = 4.0
#: A measured ratio outside this range is a broken receipt, not a tokenizer.
_CHARS_PER_TOKEN_RANGE = (1.0, 20.0)
#: The harness summarizes the conversation past this share of the max.
COMPACT_AT_PERCENT = 85


@dataclass(frozen=True)
class ContextLimit:
    """How much a request to ``llm`` may hold: ``max_tokens``, and where
    the number came from (``source``: ``litellm`` for a model in its
    table, ``env`` for the fallback window)."""

    llm: Optional[str]
    window: int
    output_limit: Optional[int]
    max_tokens: int
    source: str

    @property
    def compact_at(self) -> int:
        return self.max_tokens * COMPACT_AT_PERCENT // 100


@dataclass(frozen=True)
class ContextUsage:
    """One request measured against its limit, by part: the standing
    instructions, the tool menu, and the conversation (every message
    the model is shown, headings included)."""

    limit: ContextLimit
    system_prompt_tokens: int
    tools_tokens: int
    conversation_tokens: int
    chars_per_token: float
    #: The ratio was measured from a stored reply, not assumed.
    calibrated: bool

    @property
    def used_tokens(self) -> int:
        return self.system_prompt_tokens + self.tools_tokens + self.conversation_tokens

    @property
    def percent(self) -> float:
        """``used_tokens`` as a share of the max, to one decimal (owner
        request 2026-10-13: a fresh conversation sits well under 1%,
        and a whole-number "0%" said nothing)."""
        return round(self.used_tokens * 100 / self.limit.max_tokens, 1) if self.limit.max_tokens else 0.0

    @property
    def needs_compaction(self) -> bool:
        return self.used_tokens >= self.limit.compact_at

    def view(self) -> Dict[str, Any]:
        """The facts the page's ``/context`` shows, in its words."""
        limit = self.limit
        return {
            "llm": limit.llm,
            "source": limit.source,
            "window": limit.window,
            "output_limit": limit.output_limit,
            "max_tokens": limit.max_tokens,
            "used_tokens": self.used_tokens,
            "percent": self.percent,
            "compact_at_tokens": limit.compact_at,
            "compact_at_percent": COMPACT_AT_PERCENT,
            "chars_per_token": round(self.chars_per_token, 2),
            "calibrated": self.calibrated,
            "system_prompt_tokens": self.system_prompt_tokens,
            "tools_tokens": self.tools_tokens,
            "conversation_tokens": self.conversation_tokens,
        }


def env_window() -> int:
    """``CHAT_CONTEXT_WINDOW`` as a positive integer; the default when
    unset, blank, or not a positive integer (logged once per read)."""
    raw = (os.getenv(CONTEXT_WINDOW_ENV) or "").strip()
    if not raw:
        return DEFAULT_CONTEXT_WINDOW
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning("%s=%r is not a positive whole number; using %d", CONTEXT_WINDOW_ENV, raw, DEFAULT_CONTEXT_WINDOW)
        return DEFAULT_CONTEXT_WINDOW
    return value


@lru_cache(maxsize=64)
def litellm_limits(llm: str) -> Optional[Tuple[int, Optional[int]]]:
    """(window, output limit) from litellm's model table, None for a
    model it does not know. Cached per model name: the table lookup
    imports litellm, and the answer never changes while running."""
    try:
        import litellm

        info = litellm.get_model_info(llm)
    except Exception:  # ModelNotMappedError, or litellm itself unavailable
        return None
    # Only the input limit names the window: the table's older
    # ``max_tokens`` field is as often the output limit.
    window = info.get("max_input_tokens")
    if not window:
        return None
    output_limit = info.get("max_output_tokens")
    return int(window), (int(output_limit) if output_limit else None)


def context_limit(llm: Optional[str]) -> ContextLimit:
    """The limit for ``llm`` (see the module notes); the fallback window
    for no model at all."""
    known = litellm_limits(llm) if llm else None
    if known is None:
        window = env_window()
        return ContextLimit(llm=llm, window=window, output_limit=None, max_tokens=window // 2, source="env")
    window, output_limit = known
    if output_limit is not None and output_limit < window:
        max_tokens = window - output_limit
    else:
        max_tokens = window // 2
    return ContextLimit(llm=llm, window=window, output_limit=output_limit, max_tokens=max_tokens, source="litellm")


def chars_per_token(messages: List[Dict[str, Any]]) -> Tuple[float, bool]:
    """This model's characters per token, measured from the newest
    stored reply that kept both the text it was sent and the provider's
    count of its input tokens: (ratio, True). (The default, False) when
    no reply gives one."""
    low, high = _CHARS_PER_TOKEN_RANGE
    for message in reversed(messages):
        usage = message.get("usage") or {}
        transcript = message.get("transcript") or {}
        tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        chars = len(transcript.get("input") or "") if isinstance(transcript, dict) else 0
        if tokens and chars:
            ratio = chars / float(tokens)
            if low <= ratio <= high:
                return ratio, True
    return DEFAULT_CHARS_PER_TOKEN, False


def measure(limit: ContextLimit, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
            ratio: float = DEFAULT_CHARS_PER_TOKEN, calibrated: bool = False) -> ContextUsage:
    """Size the request ``messages`` (the system prompt first) plus the
    tool menu, as ``render_prompt`` lays it out — the same text whose
    token count the receipts report, so the ratio applies to it."""
    full = len(render_prompt(messages, tools))
    # The tool section is the whole "=== tools offered ===" tail; the
    # system part is the first message's block with the join after it.
    tool_menu = len(render_prompt([], tools))
    system = len(render_prompt(messages[:1], [])) - len(render_prompt([], [])) if messages else 0
    conversation = max(0, full - system - tool_menu)

    def to_tokens(chars: int) -> int:
        return int(round(chars / ratio))

    return ContextUsage(
        limit=limit,
        system_prompt_tokens=to_tokens(system),
        tools_tokens=to_tokens(tool_menu),
        conversation_tokens=to_tokens(conversation),
        chars_per_token=ratio,
        calibrated=calibrated,
    )
