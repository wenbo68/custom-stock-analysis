# -*- coding: utf-8 -*-
"""Request and response shapes of the chat API (2026-09-21). Every field
is named as the chat page labels it (owner request 2026-09-24): a
conversation's facts are user_input_count, total_tokens, created_at
(start date) and ended_at (end date); a tool step has a name, an input
and an output; an LLM step has its llm, time_ms and usage."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from src.languages import DEFAULT_LANGUAGE, LANGUAGES, require_supported

ChatRole = Literal["user", "assistant", "tool"]


class ConversationSummary(BaseModel):
    id: str
    title: Optional[str] = Field(default=None, description="The first user message, cut short; null until one is sent.")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int
    user_input_count: int = Field(description="How many messages the user sent (the page's \"user inputs\").")
    total_tokens: int = Field(description="Tokens every LLM call in the conversation used, together.")
    ended_at: Optional[str] = Field(default=None, description="When the user last sent a message (the page's \"end date\"); null before the first.")


class ConversationList(BaseModel):
    items: List[ConversationSummary] = Field(description="Most recently touched first.")


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any] = Field(description="The arguments the model gave, parsed.")


class TokenUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class ChatMessage(BaseModel):
    """One message as the page shows it. A user message has `text`. An
    assistant message (one LLM call) has `text` and/or `tool_calls`. A
    tool message answers one call (`tool_call_id`) with `output`."""

    seq: int
    role: ChatRole
    created_at: Optional[str] = None
    text: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    usage: Optional[TokenUsage] = None
    llm: Optional[str] = Field(default=None, description="Assistant rows only: the model that answered.")
    error: Optional[str] = Field(default=None, description="Assistant rows only: the LLM call failed with this.")
    time_ms: Optional[int] = Field(default=None, description=(
        "Assistant rows: how long the LLM call took. Tool rows: how long the tool ran "
        "(null when nothing ran — an unknown tool, bad arguments, a refusal)."
    ))
    transcript_chars: Optional[int] = Field(default=None, description=(
        "Assistant rows only: how much text the call's transcript holds; read it with "
        "`GET /conversations/{id}/messages/{seq}/transcript`. Null when there is none."
    ))
    notice: Optional[str] = Field(default=None, description="Assistant rows only: `tool_call_limit` when the turn hit the tool-call limit.")
    tool_call_id: Optional[str] = None
    name: Optional[str] = Field(default=None, description="Tool rows: the tool's name.")
    output: Optional[Any] = Field(default=None, description="Tool rows: what the tool answered (an `error` key on a refusal or miss).")
    output_chars: Optional[int] = None
    truncated: Optional[bool] = Field(default=None, description="Tool rows: the model saw a cut-down copy.")
    approved: Optional[bool] = Field(default=None, description="Tool rows that waited for the user: their answer.")
    input: Optional[Dict[str, Any]] = Field(default=None, description=(
        "Tool rows: the inputs the tool ran with, every default filled in. Null when the "
        "model's arguments never parsed (the assistant row's `tool_calls` keep what it sent)."
    ))


class PendingCall(BaseModel):
    call_id: str
    name: str
    input: Dict[str, Any] = Field(description="The inputs the tool would run with, every default filled in.")
    facts: Dict[str, Any] = Field(description=(
        "What to ask with: for start_run the effective inputs; for delete_run "
        "the run's row; for the large reads chars and tokens_estimate."
    ))


class PendingAction(BaseModel):
    """The tool call waiting for the user's yes or no (the first of
    `calls`); the others wait their turn."""

    calls: List[PendingCall]


class ConversationView(ConversationSummary):
    messages: List[ChatMessage]
    pending: Optional[PendingAction] = None


LANGUAGE_FIELD_DESCRIPTION = (
    "The language the user chose for the app (the page's language switch); "
    "the bot answers in it whatever language the message is written in. "
    "One of: " + ", ".join(sorted(LANGUAGES)) + "."
)


def validate_language(value: str) -> str:
    return require_supported(value)


class SendMessageRequest(BaseModel):
    text: str = Field(description="The user's message.")
    language: str = Field(default=DEFAULT_LANGUAGE, description=LANGUAGE_FIELD_DESCRIPTION)

    _language = field_validator("language")(validate_language)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        return cleaned


class ConfirmRequest(BaseModel):
    approved: bool = Field(description="true runs the held action; false records the refusal.")
    language: str = Field(default=DEFAULT_LANGUAGE, description=LANGUAGE_FIELD_DESCRIPTION)

    _language = field_validator("language")(validate_language)


class ConversationDeleted(BaseModel):
    id: str
