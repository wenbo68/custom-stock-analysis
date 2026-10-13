# -*- coding: utf-8 -*-
"""The chat model call: one request to the configured model (``MAIN_LLM``
through litellm, the same client and key the analysis uses) with the
conversation and the tool menu, answered as either text, tool calls,
or both.

``ModelClient`` is the seam the harness depends on; tests hand it a
scripted fake, production uses ``LiteLlmClient``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from src.tiered_analysis.llm_support import LlmConfigError
from src.tiered_analysis.run_context import llm_api_key, llm_model

#: Temperature 0 like every model call in this app (owner decision
#: 2026-08-23): the same conversation should get the same answer.
CHAT_TEMPERATURE = 0.0


@dataclass(frozen=True)
class ModelReply:
    """What came back: the text (None when the model only called tools),
    the tool calls in OpenAI shape ({id, type, function: {name,
    arguments}}), token usage, and the model that answered."""

    content: Optional[str]
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    #: The model that answered, as the page's "llm" fact names it.
    llm: Optional[str] = None


class ModelClient(Protocol):
    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                 tool_choice: str = "auto") -> ModelReply:
        """``tool_choice`` is the provider's own word: ``auto`` lets the
        model pick a tool, ``none`` offers the menu but refuses every
        call (the summary request, src/chat/compact.py)."""
        ...


class ModelCallError(RuntimeError):
    """The provider refused or failed; the message is safe to show."""


def _tool_calls_of(message: Any) -> List[Dict[str, Any]]:
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        function = getattr(call, "function", None)
        calls.append({
            "id": getattr(call, "id", None) or f"call_{len(calls) + 1}",
            "type": "function",
            "function": {
                "name": getattr(function, "name", None) or "",
                "arguments": getattr(function, "arguments", None) or "{}",
            },
        })
    return calls


class LiteLlmClient:
    """The configured model through litellm. Raises ``LlmConfigError``
    when no model is set and ``ModelCallError`` when the call fails."""

    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                 tool_choice: str = "auto") -> ModelReply:
        model = llm_model()
        if not model:
            raise LlmConfigError("no LLM model configured: MAIN_LLM is not set")
        import litellm

        kwargs: Dict[str, Any] = {}
        api_key = llm_api_key()
        if api_key:
            kwargs["api_key"] = api_key
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        try:
            response = litellm.completion(
                model=model, messages=messages, temperature=CHAT_TEMPERATURE, **kwargs,
            )
        except Exception as exc:  # any provider error: the user must see why
            raise ModelCallError(f"{type(exc).__name__}: {exc}") from exc
        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        return ModelReply(
            content=getattr(message, "content", None),
            tool_calls=_tool_calls_of(message),
            # litellm's usage speaks the provider's words; we say input/output.
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            llm=getattr(response, "model", None) or model,
        )
