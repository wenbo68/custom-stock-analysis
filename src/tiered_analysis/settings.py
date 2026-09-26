# -*- coding: utf-8 -*-
"""The run form's defaults and the sizing settings of a tiered run
(v2 slice 6; simplified 2026-09-21; the page's words since 2026-09-24).

The share formula needs how much capital the user trades with, what
percent of it they accept losing on one trade, and the reward ratio the
plan should aim for. Every run sizes (owner decision 2026-07-24): the
run form always sends all three, and a scripted or API caller that
sends nothing gets the form's own defaults below. There is no saved
server-side layer any more — the ``.env``-backed settings and the
``sizing-defaults`` endpoint that exposed them were never used and
were removed.

Every name here is the analysis page's own word for the thing (owner
request 2026-09-24): ``capital``, ``risk_pct`` (a percent, 1 = 1%, as
the form's "Risk: %" field takes it), ``reward_ratio``,
``max_hold_weeks``, ``tier``. The engine, the database and every client
use these same words and units, so nothing translates at any edge.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

#: The web form's own defaults: 100k capital, 1% risk, target = entry +
#: 2 × risk, a two-week max hold, the preliminary analysis. What a run
#: uses when the caller sends nothing.
DEFAULT_CAPITAL = 100_000.0
DEFAULT_RISK_PCT = 1.0
#: A resistance-capped target below this ratio draws a warning; the 1.5
#: hard floor in levels.py still voids the plan outright.
DEFAULT_REWARD_RATIO = 2.0
DEFAULT_MAX_HOLD_WEEKS = 2
DEFAULT_TIER = 1

#: The max hold choices the form offers, in weeks (owner decision
#: 2026-08-08): the SAME number feeds the AI prompts, the report and the
#: forward-test grading window so they stay on one page.
MAX_HOLD_WEEKS_CHOICES = (1, 2, 3, 4)
#: The tiers a run can be asked for: 1 = the preliminary analysis, 2 =
#: the deep analysis. Tier 3 is retired (outlook redesign, 2026-07-20).
SUPPORTED_TIERS = (1, 2)


def max_hold_weeks_text(max_hold_weeks: int) -> str:
    """Human wording for the max hold time ("1 week", "3 weeks")."""
    return f"{max_hold_weeks} week" + ("" if max_hold_weeks == 1 else "s")


@dataclass(frozen=True)
class SizingSettings:
    """What the sizing engine needs from the user. The fields stay
    optional so a test can switch sizing off by passing None; production
    always has all three."""

    capital: Optional[float] = DEFAULT_CAPITAL
    #: Percent of capital risked on one trade (1 = 1%).
    risk_pct: Optional[float] = DEFAULT_RISK_PCT
    reward_ratio: float = DEFAULT_REWARD_RATIO

    @property
    def is_enabled(self) -> bool:
        return self.capital is not None and self.risk_pct is not None


def merge_overrides(
    settings: SizingSettings,
    capital: Optional[float] = None,
    risk_pct: Optional[float] = None,
    reward_ratio: Optional[float] = None,
) -> SizingSettings:
    """Per-run values (from the API request) on top of ``settings``.

    Returns a new object — settings are never mutated in place. A reward
    ratio of 1 or below is ignored (the request model already rejects
    it; this keeps direct callers honest too).
    """
    merged = settings
    if capital is not None:
        merged = replace(merged, capital=float(capital))
    if risk_pct is not None:
        merged = replace(merged, risk_pct=float(risk_pct))
    if reward_ratio is not None and float(reward_ratio) > 1.0:
        merged = replace(merged, reward_ratio=float(reward_ratio))
    return merged
