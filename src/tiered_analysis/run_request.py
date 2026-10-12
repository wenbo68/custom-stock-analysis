# -*- coding: utf-8 -*-
"""The run request: the analysis page's form, field for field.

It lives here, below the HTTP layer, because two clients build it — the
web page over HTTP (api/v1/endpoints/tiered.py) and the chat's
start_run tool in-process (src/chat/tools.py) — and the service that
takes it (run_service.py) is in ``src`` too (2026-10-10). The tiered
API's schema module re-exports it so /docs still shows it.

Every field carries the analysis page's own words, in the form's order
— ticker, capital, risk % (a percent, as typed), reward ratio, max hold
weeks, tier, run anyway — so the page, the chat's tool and the user
share one vocabulary (owner request 2026-09-24). The engine and the
database use the same words too.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.languages import DEFAULT_LANGUAGE, LANGUAGES, require_supported
from src.tiered_analysis.settings import DEFAULT_MAX_HOLD_WEEKS, DEFAULT_TIER


class TieredAnalyzeRequest(BaseModel):
    """The run form, field for field. The form defaults fill whatever a
    caller leaves out (see GET /status `defaults`)."""

    ticker: str = Field(description="Ticker, e.g. AAPL or 600519.")
    capital: Optional[float] = Field(
        default=None, gt=0,
        description="Trading capital in the ticker's own currency.",
    )
    risk_pct: Optional[float] = Field(
        default=None, gt=0, lt=100,
        description="Percent of capital to risk on this trade (1 = 1%).",
    )
    reward_ratio: Optional[float] = Field(
        default=None, gt=1, le=10,
        description="Target reward-to-risk ratio (target = entry + ratio × risk).",
    )
    #: Max hold time in weeks (2026-08-08): the horizon the AI judges
    #: against, shown on the report and used as the grading window.
    max_hold_weeks: int = Field(
        default=DEFAULT_MAX_HOLD_WEEKS, ge=1, le=4,
        description="Max hold time in weeks the AI judges against.",
    )
    #: 1 = the preliminary analysis (one LLM call), 2 = the deep analysis
    #: (the vote). Tier 3 is retired (outlook redesign) — tier 3 is a
    #: validation error, not a clamp.
    tier: int = Field(
        default=DEFAULT_TIER, ge=1, le=2,
        description="1 = preliminary analysis, 2 = deep analysis (the vote).",
    )
    #: "Run anyway" after a market-open refusal: start during the trading
    #: day, analyzing the PREVIOUS completed session's close.
    run_anyway: bool = Field(
        default=False,
        description="Start during the trading day anyway, analyzing the previous completed session.",
    )
    #: The language the user chose for the app (2026-09-26): every
    #: sentence the report's models write is in it. Stored with the
    #: run's inputs; two runs that differ only by language are not
    #: duplicates of each other.
    language: str = Field(
        default=DEFAULT_LANGUAGE,
        description="The language the report's model-written text is in. One of: " + ", ".join(sorted(LANGUAGES)) + ".",
    )

    @field_validator("ticker")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("ticker must not be blank")
        return cleaned

    _language = field_validator("language")(require_supported)
