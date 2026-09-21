# -*- coding: utf-8 -*-
"""Request and response shapes of the tiered API (2026-09-21).

Every route declares its response model here so the generated OpenAPI
page (``/docs``) shows what comes back, field by field, not just what
goes in. The one deliberately loose field is ``RunDetail.result``: the
stored report is a large, versioned JSON document whose shape the
frontend types in web/src/api/tiered.ts; mirroring it here would be a
second copy to keep in step for no runtime gain.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

RunStatus = Literal["queued", "running", "done", "failed"]
Outlook = Literal["bullish", "neutral", "bearish", "unknown"]
#: The outlook filter also takes "none": rows with no opinion (unfinished,
#: failed, or the judge produced nothing) — the dash in the history list.
OutlookFilter = Literal["bullish", "neutral", "bearish", "none"]
Section = Literal["core", "dimensions", "debate", "plan"]


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------


class SizingOverride(BaseModel):
    """Per-run sizing inputs; the form defaults fill whatever is omitted."""

    capital: Optional[float] = Field(
        default=None, gt=0,
        description="Trading capital in the ticker's own currency.",
    )
    risk_fraction: Optional[float] = Field(
        default=None, gt=0, lt=1,
        description="Fraction of capital to risk on this trade (0.01 = 1%).",
    )
    reward_risk: Optional[float] = Field(
        default=None, gt=1, le=10,
        description="Target reward-to-risk ratio (target = entry + R × risk).",
    )


class TieredAnalyzeRequest(BaseModel):
    stock_code: str = Field(description="Ticker, e.g. AAPL or 600519.")
    #: 1 = the one-blob judge, 2 = the evidence vote. Tier 3 is retired
    #: (outlook redesign) — depth 3 is a validation error, not a clamp.
    depth: int = Field(
        default=1, ge=1, le=2,
        description="1 = quick analysis, 2 = deep analysis (the evidence vote).",
    )
    sizing: Optional[SizingOverride] = None
    #: Max hold time in weeks (2026-08-08): the horizon the AI judges
    #: against, shown on the report and used as the grading window.
    hold_weeks: int = Field(
        default=2, ge=1, le=4,
        description="Max hold time in weeks the AI judges against.",
    )
    #: Clock-gate override ("run anyway"): start during the trading day,
    #: analyzing the PREVIOUS completed session's close.
    run_anyway: bool = Field(
        default=False,
        description="Start during the trading day anyway, analyzing the previous completed session.",
    )

    @field_validator("stock_code")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("stock_code must not be blank")
        return cleaned


class AnalyzeAccepted(BaseModel):
    """202: the run is stored and will start when a slot is free."""

    task_id: str
    stock_code: str
    depth: int
    status: Literal["queued", "running"] = Field(
        description="running when a slot was free at once, else queued.",
    )


# ---------------------------------------------------------------------------
# GET /runs, GET /runs/tickers, GET /runs/{task_id}
# ---------------------------------------------------------------------------


class RunSummary(BaseModel):
    """One history row: identity, status, and the facts the list shows
    and filters on. No report payload — that is GET /runs/{task_id}."""

    task_id: str
    stock_code: str
    status: RunStatus
    error: Optional[str] = None
    created_at: Optional[str] = Field(default=None, description="ISO 8601, UTC.")
    updated_at: Optional[str] = Field(default=None, description="ISO 8601, UTC.")
    queue_ahead: Optional[int] = Field(
        default=None,
        description="Queued rows only: how many runs are ahead in the line.",
    )
    tier: Optional[int] = Field(default=None, description="1 or 2.")
    capital: Optional[float] = None
    risk_fraction: Optional[float] = Field(default=None, description="0.01 = 1%.")
    reward_risk: Optional[float] = None
    hold_weeks: Optional[int] = None
    outlook: Optional[Outlook] = Field(
        default=None, description="Set once the run is done; null before.",
    )
    shares: Optional[float] = Field(
        default=None,
        description=(
            "0 = sizing ran but bought nothing; null = no sizing block. "
            "Fractional on markets that size in fractional units."
        ),
    )


class RunPage(BaseModel):
    """One page of the run history, newest first."""

    items: List[RunSummary]
    page: int
    page_size: int
    total: int = Field(description="Every match, not just this page.")
    page_count: int


class TickerList(BaseModel):
    items: List[str] = Field(description="Every ticker ever run, A-Z.")


class RunDetail(RunSummary):
    """One run with the stored report cut down to the requested sections."""

    sections: List[Section] = Field(description="What `result` holds.")
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "The stored report (shape: web/src/api/tiered.ts TieredResult), "
            "limited to `sections`. Null while queued/running and after a failure."
        ),
    )


# ---------------------------------------------------------------------------
# GET /runs/{task_id}/transcript, GET /runs/{task_id}/transcript/{seq}
# ---------------------------------------------------------------------------


class TranscriptCallFacts(BaseModel):
    """Everything about one LLM call except its text."""

    seq: int = Field(description="Call number within the run, from 1.")
    created_at: Optional[str] = None
    stage: Optional[str] = Field(
        default=None, description="Which step made the call, e.g. tier1_analysis.",
    )
    model: Optional[str] = None
    temperature: Optional[float] = None
    duration_ms: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    structured: Optional[str] = Field(
        default=None, description="Reply enforcement asked for: schema, json, or null.",
    )
    error: Optional[str] = Field(
        default=None, description="Set when the call itself failed.",
    )


class TranscriptCallSummary(TranscriptCallFacts):
    """An index row: the facts plus how big the text is, so a caller can
    decide whether to fetch it."""

    prompt_chars: int
    reply_chars: int


class TranscriptIndex(BaseModel):
    items: List[TranscriptCallSummary] = Field(
        description="In call order. Empty when the run made no call or its rows expired.",
    )


class TranscriptCall(TranscriptCallFacts):
    """One call with its full prompt and raw reply."""

    prompt: Optional[str] = None
    reply: Optional[str] = None
