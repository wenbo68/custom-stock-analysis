# -*- coding: utf-8 -*-
"""Request and response shapes of the chat API (2026-09-21)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

ChatRole = Literal["user", "assistant", "tool"]


class ConversationSummary(BaseModel):
    id: str
    title: Optional[str] = Field(default=None, description="The first user message, cut short; null until one is sent.")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int
    question_count: int = Field(description="How many messages the user sent (the conversation's questions).")
    total_tokens: int = Field(description="Tokens every model call in the conversation used, together.")
    last_question_at: Optional[str] = Field(default=None, description="When the user last sent a message; null before the first.")


class ConversationList(BaseModel):
    items: List[ConversationSummary] = Field(description="Most recently touched first.")


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any] = Field(description="The arguments the model gave, parsed.")


class TokenUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class ChatMessage(BaseModel):
    """One message as the page shows it. A user message has `text`. An
    assistant message has `text` and/or `tool_calls`. A tool message
    answers one call (`tool_call_id`) with `result`."""

    seq: int
    role: ChatRole
    created_at: Optional[str] = None
    text: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    usage: Optional[TokenUsage] = None
    model: Optional[str] = None
    error: Optional[str] = Field(default=None, description="Assistant rows only: the model call failed with this.")
    duration_ms: Optional[int] = Field(default=None, description=(
        "Assistant rows: how long the model call took. Tool rows: how long the tool ran "
        "(null when nothing ran — an unknown tool, bad arguments, a refusal)."
    ))
    transcript_chars: Optional[int] = Field(default=None, description=(
        "Assistant rows only: how much text the call's transcript holds; read it with "
        "`GET /conversations/{id}/messages/{seq}/transcript`. Null when there is none."
    ))
    notice: Optional[str] = Field(default=None, description="Assistant rows only: `step_cap` when the turn hit the tool-round limit.")
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    result: Optional[Any] = Field(default=None, description="Tool rows: what the tool answered (an `error` key on a refusal or miss).")
    result_chars: Optional[int] = None
    truncated: Optional[bool] = Field(default=None, description="Tool rows: the model saw a cut-down copy.")
    approved: Optional[bool] = Field(default=None, description="Tool rows that waited for the user: their answer.")


class PendingCall(BaseModel):
    call_id: str
    name: str
    arguments: Dict[str, Any]
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


class SendMessageRequest(BaseModel):
    text: str = Field(description="The user's message.")

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        return cleaned


class ConfirmRequest(BaseModel):
    approved: bool = Field(description="true runs the held action; false records the refusal.")


class ConversationDeleted(BaseModel):
    id: str
