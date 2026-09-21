# -*- coding: utf-8 -*-
"""Sizing settings for a tiered run (v2 slice 6; simplified 2026-09-21).

The share formula needs how much capital the user trades with, what
fraction of it they accept losing on one trade, and the reward-to-risk
ratio the plan should aim for. Every run sizes (owner decision
2026-07-24): the run form always sends all three, and a scripted or API
caller that sends nothing gets the form's own defaults below. There is
no saved server-side layer any more — the ``.env``-backed settings and
the ``sizing-defaults`` endpoint that exposed them were never used and
were removed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

#: The web form's own defaults: 100k capital, 1% risk, target = entry +
#: 2 × risk. What a run uses when the caller sends nothing.
DEFAULT_CAPITAL = 100_000.0
DEFAULT_RISK_FRACTION = 0.01
#: A resistance-capped target below this ratio draws a warning; the 1.5
#: hard floor in levels.py still voids the plan outright.
DEFAULT_REWARD_RISK = 2.0
#: The form's other defaults, kept beside the sizing ones so the request
#: model and the server-status route read the same numbers: the quick
#: analysis, judged over a two-week hold.
DEFAULT_TIER = 1
DEFAULT_HOLD_WEEKS = 2


@dataclass(frozen=True)
class SizingSettings:
    """What the sizing engine needs from the user. The fields stay
    optional so a test can switch sizing off by passing None; production
    always has all three."""

    capital: Optional[float] = DEFAULT_CAPITAL
    risk_fraction: Optional[float] = DEFAULT_RISK_FRACTION
    reward_risk: float = DEFAULT_REWARD_RISK

    @property
    def is_enabled(self) -> bool:
        return self.capital is not None and self.risk_fraction is not None


def merge_overrides(
    settings: SizingSettings,
    capital: Optional[float] = None,
    risk_fraction: Optional[float] = None,
    reward_risk: Optional[float] = None,
) -> SizingSettings:
    """Per-run values (from the API request) on top of ``settings``.

    Returns a new object — settings are never mutated in place. A reward
    ratio of 1 or below is ignored (the request model already rejects
    it; this keeps direct callers honest too).
    """
    merged = settings
    if capital is not None:
        merged = replace(merged, capital=float(capital))
    if risk_fraction is not None:
        merged = replace(merged, risk_fraction=float(risk_fraction))
    if reward_risk is not None and float(reward_risk) > 1.0:
        merged = replace(merged, reward_risk=float(reward_risk))
    return merged
