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

#: `stopped` is the row that ends a turn the user stopped (the page's
#: "You stopped this reply" line); it is neither a user input nor a bot step.
#: `summary` is a bot step that summarized the conversation to free up
#: context (2026-10-13): from it on, the model sees the summary in place
#: of the rows before it. `notice` is the app's line that a run started
#: from the conversation has ended (2026-10-20): the bot's report follows
#: it as a turn of its own.
ChatRole = Literal["user", "assistant", "tool", "stopped", "summary", "notice"]


class ConversationSummary(BaseModel):
    id: str
    title: Optional[str] = Field(default=None, description="The first user message, cut short; null until one is sent.")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int
    user_input_count: int = Field(description=(
        "How many turns were set off (the page's \"convo turns\"): the user's own messages "
        "and the run notices the app wrote (2026-10-20)."
    ))
    total_tokens: int = Field(description="Tokens every LLM call in the conversation used, together.")
    ended_at: Optional[str] = Field(default=None, description="When the user last sent a message (the page's \"end date\"); null before the first.")


class ConversationList(BaseModel):
    items: List[ConversationSummary] = Field(description="The conversation the user most recently wrote in first.")


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any] = Field(description="The arguments the model gave, parsed.")


class TokenUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class CompactedFacts(BaseModel):
    """What a summary row stands for (2026-10-13)."""

    trigger: Literal["auto", "manual"] = Field(description="`auto`: the bot crossed the context line by itself; `manual`: the user typed /compact.")
    first_seq: Optional[int] = Field(default=None, description="The first message the summary stands for.")
    last_seq: Optional[int] = Field(default=None, description="The last message the summary stands for.")
    tokens_before: Optional[int] = Field(default=None, description="The estimated tokens the request held before the summary.")


class RunNoticeLevels(BaseModel):
    """A report's headline levels; each None until the plan computed it."""

    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None


class RunNoticeFacts(BaseModel):
    """How a watched run ended (2026-10-20). The page words its line
    from the run, when it ended, the outlook and score; the rest is
    the headline the model's own line carries (src/chat/run_notice.py),
    kept here so the row reads whole."""

    run_id: str
    ticker: str
    tier: Optional[int] = None
    status: Literal["succeeded", "failed", "stopped"]
    ended_at: Optional[str] = Field(default=None, description="When the run ended (ISO 8601, UTC).")
    outlook: Optional[str] = Field(default=None, description="Succeeded runs: the report's outlook.")
    score: Optional[float] = Field(default=None, description="Succeeded runs: the report's score.")
    confidence: Optional[float] = None
    action: Optional[str] = None
    levels: Optional[RunNoticeLevels] = None
    shares: Optional[float] = None
    earnings_date: Optional[str] = None
    summary: Optional[str] = None
    warning_count: int = 0
    error: Optional[str] = Field(default=None, description="Failed runs: what went wrong.")
    stopped_stage: Optional[str] = Field(default=None, description="Stopped runs: the step the stop landed in.")


class WatchedRun(BaseModel):
    """A run the conversation waits to hear about (2026-10-20): started
    by the bot here and not ended yet. The page keeps polling while
    any is listed."""

    run_id: str
    language: str = Field(description="The language the user had chosen when the run was started; the bot's report is written in it.")


class ChatMessage(BaseModel):
    """One message as the page shows it. A user message has `text`. An
    assistant message (one LLM call) has `text` and/or `tool_calls`. A
    tool message answers one call (`tool_call_id`) with `output`. A
    summary message (one LLM call too) has `text` — the summary — and
    `compacted`; with `error` set, the summary failed and the model
    still sees the full history."""

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
    compacted: Optional[CompactedFacts] = Field(default=None, description="Summary rows only: what the summary stands for.")
    late: Optional[bool] = Field(default=None, description=(
        "Stopped rows only: true when the stop landed after the turn's last step had already finished "
        "(a final reply, or a requested summary), so nothing was cut short; false when a step would have followed."
    ))
    side_question: Optional[bool] = Field(default=None, description=(
        "User, assistant and stopped rows: true when the row belongs to a side question (the page's `/btw`). "
        "The page shows it where it happened; no later LLM call, measure or summary carries it."
    ))
    run: Optional[RunNoticeFacts] = Field(default=None, description="Notice rows only: the run and how it ended.")
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
    busy: bool = Field(default=False, description=(
        "A turn is running on the conversation right now — one the page sent, or the bot's own report "
        "of a run that ended (2026-10-20). The page shows the dots and keeps polling while it is."
    ))
    watched_runs: List[WatchedRun] = Field(default_factory=list, description=(
        "The runs started from this conversation that have not ended yet; the bot reports each when it does."
    ))


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


class CompactRequest(BaseModel):
    language: str = Field(default=DEFAULT_LANGUAGE, description=LANGUAGE_FIELD_DESCRIPTION + " The summary is written in it.")

    _language = field_validator("language")(validate_language)


class ContextUsageView(BaseModel):
    """How much of the model's context the next request would take
    (the page's /context, 2026-10-13). Every count is in tokens."""

    llm: Optional[str] = Field(default=None, description="The configured model; null when none is set.")
    source: Literal["litellm", "env"] = Field(description=(
        "`litellm`: the window and output limit come from litellm's model table, and the max is "
        "their difference. `env`: litellm does not know the model; the window is CHAT_CONTEXT_WINDOW "
        "and the max is half of it."
    ))
    window: int = Field(description="The model's context window.")
    output_limit: Optional[int] = Field(default=None, description="The model's output limit, when the table gives one.")
    max_tokens: int = Field(description="How much a request may hold.")
    used_tokens: int = Field(description="The estimated size of the next request.")
    percent: float = Field(description="used_tokens as a share of max_tokens, to one decimal.")
    compact_at_tokens: int = Field(description="Past this the bot summarizes the conversation by itself.")
    compact_at_percent: int
    chars_per_token: float = Field(description="The ratio the estimate used.")
    calibrated: bool = Field(description="The ratio was measured from the newest stored reply (false: assumed).")
    system_prompt_tokens: int = Field(description="The standing instructions' share.")
    tools_tokens: int = Field(description="The tool menu's share.")
    conversation_tokens: int = Field(description="The messages' share.")


class ConversationDeleted(BaseModel):
    id: str


class TurnStopped(BaseModel):
    id: str
    stopped: bool = Field(description=(
        "true: a turn was running and was told to stop; the turn's own request answers "
        "shortly with the stopped conversation. false: nothing was running (the turn may just have ended)."
    ))
