# -*- coding: utf-8 -*-
"""Top up a lagging daily series with another vendor's newest bars.

Owner decision 2026-09-23: for US symbols Yahoo is the one full-history
source, and Alpha Vantage's free tier (the newest 100 bars only) is used
solely to fill in bars Yahoo has not published yet. Yahoo reconciles its
end-of-day rows hours after the close now and then — the day's row sits
there with an open and a volume but no close — and the staleness gate
then fails every run for the day.

Mixing two vendors is safe only near the end of the series: Yahoo's
prices are dividend/split-adjusted, Alpha Vantage's are as traded, and
the two agree only for days after the latest corporate action. So the
merge insists that both vendors agree on the newest day they share, and
appends only bars dated after it.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

import pandas as pd

#: How far the two vendors may disagree on the shared day's close before
#: the merge is refused (an adjustment boundary, a bad print, anything).
OVERLAP_TOLERANCE = 0.005


def newest_bar_date(df: Optional[pd.DataFrame]) -> Optional[date]:
    """The newest dated bar in a standard daily frame, None when there is
    none."""
    if df is None or df.empty or "date" not in df.columns:
        return None
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.max().date()


def is_lagging(df: Optional[pd.DataFrame], fresh_through: Optional[date]) -> bool:
    """True when the frame's newest bar is older than ``fresh_through``
    (the last completed session). No target means nothing to lag."""
    if fresh_through is None:
        return False
    newest = newest_bar_date(df)
    return newest is None or newest < fresh_through


def merge_topup(primary: pd.DataFrame, topup: pd.DataFrame) -> Tuple[pd.DataFrame, Optional[str]]:
    """Append ``topup``'s bars dated after ``primary``'s newest bar.

    Returns ``(frame, reason)``: ``reason`` is None when bars were
    appended, else why nothing was (the primary comes back untouched).
    """
    newest = newest_bar_date(primary)
    if newest is None:
        return primary, "the primary series has no dated bars"
    if topup is None or topup.empty or "date" not in topup.columns:
        return primary, "the top-up series is empty"

    extra = topup.copy()
    extra["date"] = pd.to_datetime(extra["date"], errors="coerce")
    extra = extra.dropna(subset=["date"])
    shared = extra[extra["date"].dt.date == newest]
    if shared.empty:
        return primary, f"the top-up has no bar on {newest.isoformat()} to compare against"

    primary_dates = pd.to_datetime(primary["date"], errors="coerce").dt.date
    primary_close = float(primary.loc[primary_dates == newest, "close"].iloc[-1])
    topup_close = float(shared["close"].iloc[-1])
    if primary_close <= 0 or abs(topup_close - primary_close) / primary_close > OVERLAP_TOLERANCE:
        return primary, (
            f"the vendors disagree on {newest.isoformat()}: {primary_close:.4f} vs "
            f"{topup_close:.4f} (an adjustment boundary?)"
        )

    newer = extra[extra["date"].dt.date > newest]
    if newer.empty:
        return primary, "the top-up has no bars newer than the primary"

    newer = newer.reindex(columns=primary.columns)
    merged = pd.concat([primary, newer], ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"])
    merged = merged.sort_values("date", ascending=True).reset_index(drop=True)
    if "pct_chg" in merged.columns:
        # The appended bars' change is measured against the bar before
        # them in the merged series (Yahoo's last close for the first one).
        changes = (merged["close"].pct_change() * 100).round(2)
        appended = merged.index >= len(primary)
        merged.loc[appended, "pct_chg"] = changes[appended]
    return merged, None
