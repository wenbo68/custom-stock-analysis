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

from pydantic import BaseModel, Field

from src.tiered_analysis.run_request import TieredAnalyzeRequest as _TieredAnalyzeRequest

# Every field a client sends or reads carries the analysis page's own
# words, in the form's order — ticker, capital, risk % (a percent, as
# typed), reward ratio, max hold weeks, tier, run anyway — so the page,
# the chat's tool and the user share one vocabulary (owner request
# 2026-09-24). The engine and the database use the same words too.

RunStatus = Literal["queued", "running", "succeeded", "failed"]
#: `no_outlook` = the run finished but the analysis produced no outlook
#: (the page's "No outlook").
Outlook = Literal["bullish", "neutral", "bearish", "no_outlook"]
#: As a filter, `no_outlook` also matches rows that have no outlook yet
#: (unfinished or failed) — the dash in the history list.
OutlookFilter = Literal["bullish", "neutral", "bearish", "no_outlook"]
Section = Literal["core", "data_reports", "deep_analysis", "plan"]


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------

# The request shape lives in src (run_request.py) because the chat
# builds it in-process too; re-exported here so /docs and the route
# read it from the schema module like every other shape.
TieredAnalyzeRequest = _TieredAnalyzeRequest


class AnalyzeAccepted(BaseModel):
    """202: the run is stored and will start when a slot is free."""

    run_id: str
    ticker: str
    tier: int
    status: Literal["queued", "running"] = Field(
        description="running when a slot was free at once, else queued.",
    )


# ---------------------------------------------------------------------------
# GET /runs, GET /runs/tickers, GET /runs/{run_id}
# ---------------------------------------------------------------------------


class RunSummary(BaseModel):
    """One history row: identity, status, and the facts the list shows
    and filters on. No report payload — that is GET /runs/{run_id}."""

    run_id: str
    ticker: str
    status: RunStatus
    error: Optional[str] = None
    created_at: Optional[str] = Field(default=None, description="ISO 8601, UTC.")
    updated_at: Optional[str] = Field(default=None, description="ISO 8601, UTC.")
    queue_position: Optional[int] = Field(
        default=None,
        description="Queued rows only: the run's place in the line, from 1.",
    )
    # The run's inputs, in the form's order; null on rows stored before
    # a field existed.
    capital: Optional[float] = None
    risk_pct: Optional[float] = Field(default=None, description="Percent of capital risked (1 = 1%).")
    reward_ratio: Optional[float] = None
    max_hold_weeks: Optional[int] = None
    tier: Optional[int] = Field(default=None, description="1 or 2.")
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
            "limited to `sections`, plus `data_report_index`: one light row per "
            "data report (name, kind, counted, warnings) whatever the "
            "sections. Null while queued/running and after a failure."
        ),
    )


class RunDeleted(BaseModel):
    """The run and its transcript are gone."""

    run_id: str
    ticker: str
    status: Literal["queued", "succeeded", "failed"] = Field(
        description="What the run was. `queued` means it was cancelled before it started.",
    )


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/vote_items
# ---------------------------------------------------------------------------

#: A vote item's fate: counted toward the score, or excluded (a failed
#: citation check, outvoted by the checkers, or left unresolved).
VoteItemStatus = Literal["counted", "excluded"]


class VoteItemPage(BaseModel):
    """One page of a deep-analysis run's vote items, in stored order."""

    items: List[Dict[str, Any]] = Field(
        description=(
            "Vote items (shape: web/src/api/tiered.ts TieredVoteItem): the "
            "claim, its data_report and data field, the item_outlook it argues "
            "for, the listers' and checkers' votes, and final_status."
        ),
    )
    page: int
    page_size: int
    total: int = Field(description="Every match, not just this page.")
    page_count: int


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/transcript, GET /runs/{run_id}/transcript/{call_number}
# ---------------------------------------------------------------------------


class TranscriptCallFacts(BaseModel):
    """Everything about one LLM call except its text."""

    call_number: int = Field(description="Call number within the run, from 1.")
    created_at: Optional[str] = None
    stage: Optional[str] = Field(
        default=None, description="Which stage of the run made the call, e.g. preliminary_analysis.",
    )
    llm: Optional[str] = Field(default=None, description="The model that answered.")
    temperature: Optional[float] = None
    time_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    structured: Optional[str] = Field(
        default=None, description="Reply enforcement asked for: schema, json, or null.",
    )
    error: Optional[str] = Field(
        default=None, description="Set when the call itself failed.",
    )


class TranscriptCallSummary(TranscriptCallFacts):
    """An index row: the facts plus how big the text is, so a caller can
    decide whether to fetch it."""

    input_chars: int
    output_chars: int


class TranscriptIndex(BaseModel):
    items: List[TranscriptCallSummary] = Field(
        description="In call order. Empty when the run made no call or its rows expired.",
    )


class TranscriptCall(TranscriptCallFacts):
    """One call with its full input (the prompt) and raw output (the reply)."""

    input: Optional[str] = None
    output: Optional[str] = None


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


class LlmStatus(BaseModel):
    main_model: Optional[str] = Field(
        default=None, description="The model that does the analysis (MAIN_LLM); null = not configured, runs are refused.",
    )
    sub_model: Optional[str] = Field(
        default=None, description="The cheaper model for news screening (SUB_LLM), else the main one.",
    )
    api_key_set: bool = Field(description="Whether LLM_API_KEY is set. The key itself is never reported.")


class DataSourceStatus(BaseModel):
    """Which data sources are configured; an unconfigured one leaves its report blank with a warning."""

    finnhub: bool = Field(description="Company news.")
    alphavantage: bool = Field(description="Top-up of the newest US price bars (world news needs no key).")
    fred: bool = Field(description="Macro economy.")
    sec_edgar: bool = Field(description="US fundamentals (a contact string, not a key).")


class RunSlots(BaseModel):
    max_concurrent: int = Field(description="Runs that may execute at once; the rest queue.")
    running: int
    queued: int


class RunDefaults(BaseModel):
    """What a run uses when the request leaves a field out, in the
    form's order."""

    capital: Optional[float] = None
    risk_pct: Optional[float] = Field(default=None, description="Percent of capital risked (1 = 1%).")
    reward_ratio: float
    max_hold_weeks: int
    tier: int


class MarketClockStatus(BaseModel):
    """Where one market's clock stands. Runs analyze completed sessions
    only, so they are refused from the open until 30 minutes past the
    close (`POST /analyze` answers 409 `market_open`; `run_anyway` starts it anyway)."""

    market: str = Field(
        description=(
            "us: US tickers (AAPL); cn: 6-digit A-share codes (600519); "
            "hk: Hong Kong codes; jp/kr/tw: Yahoo-style suffixed codes (7203.T, 005930.KS, 2330.TW)."
        ),
    )
    timezone: str = Field(description="IANA zone, e.g. America/New_York.")
    local_time: str = Field(description="Now in the market's zone (ISO 8601 with offset).")
    session_open: Optional[str] = Field(default=None, description="Today's regular session; null on a non-trading day.")
    session_close: Optional[str] = None
    runs_blocked: bool = Field(description="Whether a run for this market would be refused right now.")
    runs_allowed_from: Optional[str] = Field(
        default=None, description="When blocked: the moment runs are accepted again.",
    )


class ServerStatus(BaseModel):
    """What this server can do right now."""

    server_time: str = Field(description="Now, UTC, ISO 8601.")
    llm: LlmStatus
    data_sources: DataSourceStatus
    runs: RunSlots
    defaults: RunDefaults
    transcript_retention_days: int = Field(description="LLM transcripts older than this are pruned.")
    markets: List[MarketClockStatus]
