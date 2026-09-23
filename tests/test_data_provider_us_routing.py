# -*- coding: utf-8 -*-
"""US daily-bar routing (owner decision 2026-09-23).

Yahoo is the one full-history source for US symbols. When its newest
bar lags the last completed session (Yahoo reconciles end-of-day bars
hours late now and then), Alpha Vantage's free 100-bar window tops up
the missing newest bars — never replaces the series. Finnhub's candle
endpoint moved behind a paid plan and is gone from the price layer
(its news endpoint is unaffected and still used by company news).
"""
from __future__ import annotations

import unittest
from datetime import date
from typing import List, Optional
from unittest.mock import patch

import pandas as pd

import data_provider
from data_provider.base import DataFetchError, DataFetcherManager
from data_provider.us_topup import is_lagging, merge_topup, newest_bar_date


def _frame(rows, code="MSFT") -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["volume"] * df["close"]
    df["pct_chg"] = (df["close"].pct_change() * 100).fillna(0).round(2)
    df["code"] = code
    return df


YAHOO_ROWS = [
    ("2026-09-17", 496.0, 499.0, 494.0, 497.75, 30_000_000),
    ("2026-09-18", 497.9, 499.0, 492.0, 493.78, 39_600_000),
    ("2026-09-21", 494.95, 502.0, 494.0, 501.61, 27_900_000),
]
AV_ROWS = [
    ("2026-09-18", 497.9, 499.0, 492.0, 493.78, 39_600_000),
    ("2026-09-21", 494.95, 502.0, 494.0, 501.61, 27_900_000),
    ("2026-09-22", 507.5, 509.0, 496.0, 498.00, 20_800_000),
]
SEP_21 = date(2026, 9, 21)
SEP_22 = date(2026, 9, 22)


class StubFetcher:
    """Stands in for a real fetcher: a name, a priority, and a canned
    answer (a frame, or an exception to raise)."""

    def __init__(self, name: str, priority: int, answer) -> None:
        self.name = name
        self.priority = priority
        self._answer = answer
        self.calls: List[dict] = []

    def get_daily_data(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def _manager(yahoo: Optional[StubFetcher], alphavantage: Optional[StubFetcher] = None) -> DataFetcherManager:
    DataFetcherManager.reset_daily_source_health()
    fetchers = [f for f in (yahoo, alphavantage) if f is not None]
    return DataFetcherManager(fetchers=fetchers)


class TestUsRouting(unittest.TestCase):
    def test_yahoo_alone_when_its_bars_are_fresh(self):
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS))
        av = StubFetcher("AlphaVantageFetcher", 3, _frame(AV_ROWS))

        df, source = _manager(yahoo, av).get_daily_data("MSFT", days=400, fresh_through=SEP_21)

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(newest_bar_date(df), SEP_21)
        self.assertEqual(av.calls, [], "Alpha Vantage must not be spent when Yahoo is current")

    def test_alphavantage_tops_up_the_missing_newest_bar(self):
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS))
        av = StubFetcher("AlphaVantageFetcher", 3, _frame(AV_ROWS))

        df, source = _manager(yahoo, av).get_daily_data("MSFT", days=400, fresh_through=SEP_22)

        self.assertEqual(source, "YfinanceFetcher+AlphaVantageFetcher")
        self.assertEqual(len(av.calls), 1)
        self.assertEqual(newest_bar_date(df), SEP_22)
        self.assertEqual(len(df), 4, "only the bar Yahoo lacked is appended")
        self.assertEqual(list(df["date"].dt.strftime("%Y-%m-%d")),
                         ["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"])
        self.assertAlmostEqual(float(df.iloc[-1]["close"]), 498.0)
        # The appended bar's change is measured against Yahoo's last close.
        self.assertAlmostEqual(float(df.iloc[-1]["pct_chg"]), round((498.0 / 501.61 - 1) * 100, 2))

    def test_no_freshness_target_means_no_top_up(self):
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS))
        av = StubFetcher("AlphaVantageFetcher", 3, _frame(AV_ROWS))

        _df, source = _manager(yahoo, av).get_daily_data("MSFT", days=400)

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(av.calls, [])

    def test_top_up_refused_when_vendors_disagree_on_the_shared_day(self):
        # A dividend or split between the two vendors' views: Yahoo's series
        # is adjusted, Alpha Vantage's is raw, so the shared day no longer
        # matches and the bars must not be mixed.
        disagreeing = [(d, o * 0.9, h * 0.9, l * 0.9, c * 0.9, v) for d, o, h, l, c, v in AV_ROWS]
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS))
        av = StubFetcher("AlphaVantageFetcher", 3, _frame(disagreeing))

        df, source = _manager(yahoo, av).get_daily_data("MSFT", days=400, fresh_through=SEP_22)

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(newest_bar_date(df), SEP_21)

    def test_top_up_failure_keeps_yahoo_bars(self):
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS))
        av = StubFetcher("AlphaVantageFetcher", 3, DataFetchError("[AlphaVantage] Rate limited"))

        df, source = _manager(yahoo, av).get_daily_data("MSFT", days=400, fresh_through=SEP_22)

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(len(df), 3)

    def test_yahoo_failure_is_fatal_even_with_alphavantage_present(self):
        # 100 bars from Alpha Vantage alone would silently starve the
        # long-window indicators; a run must fail loudly instead.
        yahoo = StubFetcher("YfinanceFetcher", 4, DataFetchError("Yahoo Finance 获取数据失败"))
        av = StubFetcher("AlphaVantageFetcher", 3, _frame(AV_ROWS))

        with self.assertRaises(DataFetchError) as ctx:
            _manager(yahoo, av).get_daily_data("MSFT", days=400, fresh_through=SEP_22)

        self.assertIn("YfinanceFetcher", str(ctx.exception))
        self.assertEqual(av.calls, [])

    def test_us_index_is_yahoo_only(self):
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS, code="SPX"))
        av = StubFetcher("AlphaVantageFetcher", 3, _frame(AV_ROWS, code="SPX"))

        _df, source = _manager(yahoo, av).get_daily_data("SPX", days=400, fresh_through=SEP_22)

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(av.calls, [])

    def test_lagging_yahoo_without_alphavantage_returns_what_it_has(self):
        yahoo = StubFetcher("YfinanceFetcher", 4, _frame(YAHOO_ROWS))

        df, source = _manager(yahoo).get_daily_data("MSFT", days=400, fresh_through=SEP_22)

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(newest_bar_date(df), SEP_21)


class TestFinnhubRemoved(unittest.TestCase):
    def test_finnhub_is_not_a_price_source(self):
        self.assertFalse(hasattr(data_provider, "FinnhubFetcher"))
        self.assertNotIn("FinnhubFetcher", DataFetcherManager._DAILY_MARKET_FETCHER_SUPPORT)


class TestTopupHelpers(unittest.TestCase):
    def test_is_lagging(self):
        df = _frame(YAHOO_ROWS)
        self.assertFalse(is_lagging(df, None))
        self.assertFalse(is_lagging(df, SEP_21))
        self.assertTrue(is_lagging(df, SEP_22))
        self.assertTrue(is_lagging(df.iloc[0:0], SEP_22))

    def test_merge_needs_a_shared_day(self):
        only_new = [("2026-09-22", 507.5, 509.0, 496.0, 498.00, 20_800_000)]
        merged, reason = merge_topup(_frame(YAHOO_ROWS), _frame(only_new))
        self.assertIsNotNone(reason)
        self.assertEqual(len(merged), 3)

    def test_merge_with_nothing_newer_is_a_no_op(self):
        merged, reason = merge_topup(_frame(YAHOO_ROWS), _frame(AV_ROWS[:2]))
        self.assertIsNotNone(reason)
        self.assertEqual(len(merged), 3)


class TestAlphaVantageAlwaysCompact(unittest.TestCase):
    def test_deep_range_still_asks_for_the_free_compact_window(self):
        from data_provider.alphavantage_fetcher import AlphaVantageFetcher

        fetcher = AlphaVantageFetcher.__new__(AlphaVantageFetcher)
        fetcher._api_key = "k"
        seen = {}

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"Time Series (Daily)": {
                    "2026-09-22": {"1. open": "1", "2. high": "1", "3. low": "1", "4. close": "1", "5. volume": "1"},
                }}

        def fake_get(url, params=None, timeout=None):
            seen.update(params or {})
            return Resp()

        with patch("data_provider.alphavantage_fetcher.requests.get", fake_get), \
             patch.object(AlphaVantageFetcher, "random_sleep", lambda *a, **k: None):
            fetcher._fetch_raw_data("MSFT", "2025-08-01", "2026-09-23")

        self.assertEqual(seen.get("outputsize"), "compact")


if __name__ == "__main__":
    unittest.main()
