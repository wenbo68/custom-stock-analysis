# -*- coding: utf-8 -*-
"""Tier report envelope: the shapes every tier of a run fills.

The sizing slots (capital / risk_pct / shares) stay empty until the
deterministic sizing engine has sized the run — printing a share count
creates an obligation to justify it, which an unsized report does not
have. Every name is the analysis page's own word for the thing (owner
request 2026-09-24).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .providers.base import DataReport, Market
from .settings import (  # noqa: F401  (re-exported for the engine's callers)
    DEFAULT_MAX_HOLD_WEEKS,
    MAX_HOLD_WEEKS_CHOICES,
    max_hold_weeks_text,
)

TRADING_DAYS_PER_WEEK = 5


class Outlook(str, Enum):
    """The impersonal judgment about the stock (outlook redesign,
    2026-07-20): what the evidence says, with no knowledge of the user's
    position. The old buy/hold/sell "direction" vocabulary is gone
    (2026-09-19) — an assessment can't literally mean "you should sell"
    when it doesn't know whether you own anything, and one fact deserves
    one name."""

    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    #: The analysis produced no outlook (the page's "No outlook"; the
    #: run itself is done, not failed). Was "unknown" until 2026-09-24.
    NO_OUTLOOK = "no_outlook"
    # (A "stopped" outlook for stale-data runs existed 2026-08-08 to
    # 2026-09-17; such runs now fail with StaleDataError instead.)


class Action(str, Enum):
    """The personal instruction, derived by code from the outlook plus,
    for entries, the plan's reward-to-risk vs the user's goal. The
    outlook decides WHETHER the stock deserves money; the action is what
    that means for a new position. (The held-shares column — keep
    holding / sell all — was removed with the ownership input,
    2026-09-16; a future portfolio feature would reintroduce it.)"""

    BUY_NOW = "buy_now"  # buy now: the plan's reward-to-risk meets the goal
    BUY_LATER = "buy_later"  # buy later: reward-to-risk below the goal
    NO_TRADE = "no_trade"  # nothing to do
    UNKNOWN = "unknown"


def derive_action(outlook: Outlook, plan_meets_goal: bool = True) -> Action:
    """The outlook → action table:

    | outlook  | action              |
    |----------|---------------------|
    | bullish  | buy_now / buy_later |
    | neutral  | no_trade            |
    | bearish  | no_trade            |

    ``plan_meets_goal`` splits the bullish cell (owner decision
    2026-08-23): BUY_NOW when the trade plan's actual reward ratio
    reaches the user's chosen goal, BUY_LATER when it falls short — the same comparison as the plan
    card's reward-below-goal warning, so the two can never disagree. A
    ratio that cannot be computed counts as meeting the goal, mirroring
    that warning's silence.
    """
    if outlook is Outlook.BULLISH:
        return Action.BUY_NOW if plan_meets_goal else Action.BUY_LATER
    if outlook in (Outlook.NEUTRAL, Outlook.BEARISH):
        return Action.NO_TRADE
    return Action.UNKNOWN


def coerce_price(value: object) -> Optional[float]:
    """Best-effort float from a str|int|float price field.

    Legacy level values may be numbers, numeric strings, or markers
    like "N/A". Anything non-numeric becomes None — callers must surface a
    warning rather than let a bad level pass silently.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


#: A price-like number in prose: digits (optionally decimal) not glued to a
#: letter/digit (rejects indicator names like MA20/RSI14) and not a percent.
_PRICE_IN_TEXT_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?")


def extract_price(value: object) -> Optional[float]:
    """coerce_price plus a prose fallback (first price-like number).

    The live production run showed the legacy pipeline sometimes returned
    levels as full sentences ("理想买入点：303.80元（...）"). The number is still
    deterministic text — extract the first one that is not an indicator
    name (MA20) and not a percentage (7%).
    """
    strict = coerce_price(value)
    if strict is not None:
        return strict
    if not isinstance(value, str):
        return None
    for match in _PRICE_IN_TEXT_RE.finditer(value):
        end = match.end()
        if end < len(value) and value[end] == "%":
            continue
        return float(match.group())
    return None


@dataclass(frozen=True)
class SizingSlots:
    """The sizing facts a sized report carries; empty until sizing ran."""

    capital: Optional[float] = None
    risk_pct: Optional[float] = None
    shares: Optional[float] = None

    @property
    def is_empty(self) -> bool:
        return self.capital is None and self.risk_pct is None and self.shares is None


@dataclass(frozen=True)
class TradePlanLevels:
    """The plan's price levels (formula-computed, see levels.py)."""

    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None


#: Tolerance on the "did the plan reach the reward goal" comparison,
#: shared by the plan card's reward-below-goal warning and the buy-now /
#: buy-later action split so the two can never disagree.
REWARD_GOAL_EPS = 1e-3


def calculate_reward_ratio(levels: TradePlanLevels) -> Optional[float]:
    """The plan's actual reward-to-risk: (target − entry) / (entry − stop).

    None when any leg is missing or the risk side is not positive; the
    callers treat an unknowable ratio as "no complaint" (no warning, no
    buy-later downgrade)."""
    entry, stop, target = levels.entry, levels.stop_loss, levels.target
    if entry is None or stop is None or target is None or entry <= stop:
        return None
    return (target - entry) / (entry - stop)


@dataclass(frozen=True)
class TierReport:
    """Output of one tier for one ticker: report + decision."""

    tier: int
    ticker: str
    market: Market
    outlook: Outlook
    confidence: Optional[str] = None
    score: Optional[int] = None
    levels: TradePlanLevels = field(default_factory=TradePlanLevels)
    summary: Optional[str] = None
    data_reports: List[DataReport] = field(default_factory=list)
    sizing: SizingSlots = field(default_factory=SizingSlots)
    warnings: List[str] = field(default_factory=list)
    #: v2 slice 3 audit trail: per-level base/formula/inputs + AI adjustment
    #: (reason, evidence, rejection). JSON-ready dict; None on pre-v2 reports.
    levels_detail: Optional[Dict[str, Any]] = None
    #: The tier's own record: the preliminary analysis's outlook and
    #: score on a tier-1 report, the deep analysis's vote items, pools
    #: and summary on a tier-2 report. JSON-ready dict; None elsewhere.
    detail: Optional[Dict[str, Any]] = None
    #: Max hold time in weeks the run was judged against (2026-08-08);
    #: None on reports stored before the hold-time picker existed.
    max_hold_weeks: Optional[int] = None
