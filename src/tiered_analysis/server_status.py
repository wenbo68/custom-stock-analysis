# -*- coding: utf-8 -*-
"""What a client needs to know about this server before it acts
(``GET /status``, 2026-09-21).

The web page learns most of this the hard way — a run refused with a 400
says the model is missing, a 409 says the market is open. A second
client, the chatbot, cannot read ``.env`` or a wall clock, so one small
route answers up front: which model will do the analysis (and whether a
key is set — never the key itself), which data sources are configured
(so a missing news report has an explanation), how many run slots exist
and how many runs hold or wait for one, what a run uses when the caller
sends nothing, how long transcripts are kept, and where each market's
clock stands — a run is refused during the trading day, so a client can
say *when* instead of just *no*. The server's own time rides along
because a model does not know the date.

Pure assembly over the modules that own each fact; ``now`` is a
parameter so tests pin the clock.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .llm_support import TRANSCRIPT_MAX_AGE_DAYS
from .run_context import DATA_KEY_ENV, llm_api_key, llm_model, llm_sub_model
from .run_gate import MarketClock, known_markets, market_clock
from .run_queue import max_concurrent_runs
from .settings import DEFAULT_HOLD_WEEKS, DEFAULT_TIER, SizingSettings

#: Data source -> the environment variable that enables it. The three
#: keyed vendors come from run_context; SEC EDGAR only wants a contact
#: string but refuses anonymous callers, so it counts as configured or
#: not the same way.
DATA_SOURCE_ENV: Dict[str, str] = {
    **DATA_KEY_ENV,
    "sec_edgar": "SEC_EDGAR_USER_AGENT",
}


def _is_set(env_name: str) -> bool:
    return bool((os.getenv(env_name) or "").strip())


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def market_status(clock: MarketClock) -> Dict[str, Any]:
    """One market's clock as the route reports it (ISO datetimes carrying
    the market's own UTC offset)."""
    return {
        "market": clock.market,
        "timezone": clock.timezone,
        "local_time": clock.local_time.isoformat(),
        "session_open": _iso(clock.session_open),
        "session_close": _iso(clock.session_close),
        "runs_blocked": clock.blocked,
        "runs_allowed_from": _iso(clock.blocked_until),
    }


def server_status(now: Optional[datetime] = None) -> Dict[str, Any]:
    """The whole status document. ``now`` defaults to the current UTC
    time; a naive value is taken as UTC."""
    from . import history

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    sizing = SizingSettings()
    counts = history.status_counts()
    return {
        "server_time": current.astimezone(timezone.utc).isoformat(),
        "llm": {
            "main_model": llm_model(),
            "sub_model": llm_sub_model(),
            "api_key_set": llm_api_key() is not None,
        },
        "data_sources": {name: _is_set(env) for name, env in DATA_SOURCE_ENV.items()},
        "runs": {
            "max_concurrent": max_concurrent_runs(),
            "running": counts[history.STATUS_RUNNING],
            "queued": counts[history.STATUS_QUEUED],
        },
        "defaults": {
            "tier": DEFAULT_TIER,
            "hold_weeks": DEFAULT_HOLD_WEEKS,
            "capital": sizing.capital,
            "risk_fraction": sizing.risk_fraction,
            "reward_risk": sizing.reward_risk,
        },
        "transcript_retention_days": TRANSCRIPT_MAX_AGE_DAYS,
        "markets": [
            market_status(market_clock(market, now=current))
            for market in known_markets()
        ],
    }
