# -*- coding: utf-8 -*-
"""Fetcher-layer fixes from the backend review of 2026-10-10 (section D).

Each class is one bug: Yahoo's exclusive end date (D1), A-share volume
units (D2), A-share spellings the clock gate did not recognize (D3), a
bare 5-digit Hong Kong code mistaken for Shenzhen (D6), and retries
that never fired plus an empty-result failure with no reason (D8).
"""
from __future__ import annotations

import unittest
from typing import List
from unittest.mock import patch

import pandas as pd

from data_provider.base import DataFetchError, DataFetcherManager
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.core.trading_calendar import get_market_for_stock


def _yahoo_frame() -> pd.DataFrame:
    index = pd.to_datetime(["2026-09-21", "2026-09-22"])
    return pd.DataFrame(
        {"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
         "Close": [1.0, 2.0], "Volume": [10, 20]},
        index=index,
    )


def _no_retry_sleep():
    """tenacity's backoff would otherwise make these tests wait seconds."""
    return patch.object(YfinanceFetcher._fetch_raw_data.retry, "sleep", lambda _s: None)


class TestYahooEndDateIsExclusive(unittest.TestCase):
    """D1: yfinance documents ``end`` as exclusive, so asking for
    ``end=today`` returns bars through yesterday on any server whose
    local date is still today after the close."""

    def test_the_download_asks_for_the_day_after_the_requested_end(self):
        seen = {}

        def fake_download(**kwargs):
            seen.update(kwargs)
            return _yahoo_frame()

        with patch("yfinance.download", fake_download):
            YfinanceFetcher()._fetch_raw_data("MSFT", "2026-09-01", "2026-09-22")

        self.assertEqual(seen["start"], "2026-09-01")
        self.assertEqual(seen["end"], "2026-09-23")

    def test_month_and_year_ends_roll_over(self):
        seen = {}

        def fake_download(**kwargs):
            seen.update(kwargs)
            return _yahoo_frame()

        with patch("yfinance.download", fake_download):
            YfinanceFetcher()._fetch_raw_data("MSFT", "2026-12-01", "2026-12-31")

        self.assertEqual(seen["end"], "2027-01-01")


class TestHongKongCodeInYahooFallback(unittest.TestCase):
    """D6: a bare 5-digit code is Hong Kong (``_is_hk_market``), and
    Yahoo spells it as four digits plus ``.HK``."""

    def test_bare_five_digit_code_is_hong_kong_not_shenzhen(self):
        self.assertEqual(YfinanceFetcher()._convert_stock_code("00700"), "0700.HK")

    def test_hk_prefixed_code_keeps_working(self):
        self.assertEqual(YfinanceFetcher()._convert_stock_code("hk00700"), "0700.HK")

    def test_five_digit_hk_codes_with_more_digits_are_not_truncated(self):
        self.assertEqual(YfinanceFetcher()._convert_stock_code("09988"), "9988.HK")

    def test_five_digit_hk_suffix_spelling_becomes_yahoo_four_digits(self):
        self.assertEqual(YfinanceFetcher()._convert_stock_code("00700.HK"), "0700.HK")
        self.assertEqual(YfinanceFetcher()._convert_stock_code("0700.HK"), "0700.HK")

    def test_six_digit_a_share_codes_are_unchanged(self):
        self.assertEqual(YfinanceFetcher()._convert_stock_code("600519"), "600519.SS")
        self.assertEqual(YfinanceFetcher()._convert_stock_code("000001"), "000001.SZ")


class TestClockGateRecognizesAShareSpellings(unittest.TestCase):
    """D3: the data layer routes ``600519.SH`` and friends to the
    mainland fetchers, so the clock gate must see the same market
    instead of failing open on an intraday bar."""

    def test_prefixed_and_suffixed_mainland_spellings_are_cn(self):
        for spelling in ("600519.SH", "SH600519", "600519.SS", "sz000001",
                         "SZ.000001", "000001.SZ", "920748.BJ", "bj920748"):
            with self.subTest(spelling=spelling):
                self.assertEqual(get_market_for_stock(spelling), "cn")

    def test_other_markets_are_unchanged(self):
        self.assertEqual(get_market_for_stock("AAPL"), "us")
        self.assertEqual(get_market_for_stock("00700"), "hk")
        self.assertEqual(get_market_for_stock("hk00700"), "hk")
        self.assertEqual(get_market_for_stock("0700.HK"), "hk")
        self.assertEqual(get_market_for_stock("7203.T"), "jp")
        self.assertEqual(get_market_for_stock("005930.KS"), "kr")
        self.assertEqual(get_market_for_stock("2330.TW"), "tw")
        self.assertIsNone(get_market_for_stock("not-a-code"))


class TestRetryFiresOnNetworkFailures(unittest.TestCase):
    """D8 (part 1): the fetchers wrap every exception into
    ``DataFetchError``, so a retry rule keyed on ``ConnectionError``
    never matched. The rule now looks at the wrapped cause."""

    def test_yahoo_retries_a_connection_error_then_succeeds(self):
        answers: List[object] = [ConnectionError("reset by peer"), _yahoo_frame()]
        calls = []

        def fake_download(**kwargs):
            calls.append(1)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch("yfinance.download", fake_download), _no_retry_sleep():
            df = YfinanceFetcher()._fetch_raw_data("MSFT", "2026-09-01", "2026-09-22")

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(df), 2)

    def test_yahoo_does_not_retry_a_legitimate_no_data_answer(self):
        calls = []

        def fake_download(**kwargs):
            calls.append(1)
            return pd.DataFrame()

        with patch("yfinance.download", fake_download), _no_retry_sleep():
            with self.assertRaises(DataFetchError):
                YfinanceFetcher()._fetch_raw_data("MSFT", "2026-09-01", "2026-09-22")

        self.assertEqual(len(calls), 1)

    def test_akshare_retries_a_timeout_then_succeeds(self):
        from data_provider.akshare_fetcher import AkshareFetcher

        answers: List[object] = [TimeoutError("read timed out"), pd.DataFrame({"日期": ["2026-09-22"]})]
        calls = []

        def fake_hk(**kwargs):
            calls.append(1)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        fetcher = AkshareFetcher()
        with patch("akshare.stock_hk_hist", fake_hk), \
             patch.object(AkshareFetcher, "_enforce_rate_limit", lambda self: None), \
             patch.object(AkshareFetcher, "_set_random_user_agent", lambda self: None), \
             patch.object(AkshareFetcher._fetch_raw_data.retry, "sleep", lambda _s: None):
            df = fetcher._fetch_raw_data("00700", "2026-09-01", "2026-09-22")

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(df), 1)


class TestEfinanceRetryRule(unittest.TestCase):
    """The efinance fetcher keeps one attempt by owner design, but its
    retry rule now reads the wrapped cause like the other fetchers."""

    def test_rule_matches_a_wrapped_network_error_only(self):
        from data_provider.efinance_fetcher import EfinanceFetcher

        rule = EfinanceFetcher._fetch_raw_data.retry.retry
        wrapped = DataFetchError("efinance 获取数据失败")
        wrapped.__cause__ = ConnectionError("reset")
        self.assertTrue(rule.predicate(wrapped))
        self.assertFalse(rule.predicate(DataFetchError("no rows")))


class _StubFetcher:
    def __init__(self, name: str, priority: int, answer) -> None:
        self.name = name
        self.priority = priority
        self._answer = answer

    def get_daily_data(self, **kwargs):
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


class TestEmptyResultsAreNamedInTheFailure(unittest.TestCase):
    """D8 (part 2): when every source answers with an empty frame the
    final error used to read "all sources failed:" followed by nothing."""

    def test_each_empty_answer_is_listed(self):
        DataFetcherManager.reset_daily_source_health()
        manager = DataFetcherManager(fetchers=[
            _StubFetcher("EfinanceFetcher", 0, pd.DataFrame()),
            _StubFetcher("AkshareFetcher", 1, pd.DataFrame()),
        ])

        with self.assertRaises(DataFetchError) as caught:
            manager.get_daily_data("600519", days=30)

        message = str(caught.exception)
        self.assertIn("[EfinanceFetcher]", message)
        self.assertIn("[AkshareFetcher]", message)
        self.assertIn("空", message)


class TestAShareVolumeIsShares(unittest.TestCase):
    """D2: Eastmoney (via efinance and akshare) reports 成交量 in lots of
    100 shares; every other vendor reports shares. The liquidity check
    divides planned shares by this number, so it must be shares."""

    EM_ROWS = pd.DataFrame({
        "日期": ["2001-08-27"], "开盘": [34.51], "收盘": [37.01], "最高": [37.78],
        "最低": [32.85], "成交量": [406318], "成交额": [1410347000.0], "涨跌幅": [16.25],
    })

    def test_efinance_normalizer_converts_lots_to_shares(self):
        from data_provider.efinance_fetcher import EfinanceFetcher

        df = EfinanceFetcher()._normalize_data(self.EM_ROWS.copy(), "600519")
        self.assertEqual(int(df["volume"].iloc[0]), 40_631_800)

    def test_akshare_eastmoney_channel_converts_lots_to_shares(self):
        from data_provider.akshare_fetcher import AkshareFetcher

        fetcher = AkshareFetcher()
        with patch("akshare.stock_zh_a_hist", lambda **kw: self.EM_ROWS.copy()), \
             patch.object(AkshareFetcher, "_enforce_rate_limit", lambda self: None), \
             patch.object(AkshareFetcher, "_set_random_user_agent", lambda self: None):
            df = fetcher._fetch_stock_data_em("600519", "2001-08-01", "2001-08-31")
        self.assertEqual(int(df["成交量"].iloc[0]), 40_631_800)

    def test_akshare_eastmoney_etf_channel_converts_lots_to_shares(self):
        from data_provider.akshare_fetcher import AkshareFetcher

        fetcher = AkshareFetcher()
        with patch("akshare.fund_etf_hist_em", lambda **kw: self.EM_ROWS.copy()), \
             patch.object(AkshareFetcher, "_enforce_rate_limit", lambda self: None), \
             patch.object(AkshareFetcher, "_set_random_user_agent", lambda self: None):
            df = fetcher._fetch_etf_data("510300", "2001-08-01", "2001-08-31")
        self.assertEqual(int(df["成交量"].iloc[0]), 40_631_800)

    def test_akshare_sina_and_tencent_channels_stay_in_shares(self):
        from data_provider.akshare_fetcher import AkshareFetcher

        sina = pd.DataFrame({"date": ["2001-08-27"], "open": [1.0], "high": [1.0], "low": [1.0],
                             "close": [1.0], "volume": [40_631_800], "amount": [1.0]})
        fetcher = AkshareFetcher()
        with patch("data_provider.akshare_fetcher._akshare_call_with_timeout", lambda fn, **kw: sina.copy()), \
             patch.object(AkshareFetcher, "_enforce_rate_limit", lambda self: None):
            df = fetcher._fetch_stock_data_sina("600519", "2001-08-01", "2001-08-31")
        self.assertEqual(int(df["成交量"].iloc[0]), 40_631_800)

    def test_akshare_hong_kong_stays_in_shares(self):
        from data_provider.akshare_fetcher import AkshareFetcher

        fetcher = AkshareFetcher()
        with patch("akshare.stock_hk_hist", lambda **kw: self.EM_ROWS.copy()), \
             patch.object(AkshareFetcher, "_enforce_rate_limit", lambda self: None), \
             patch.object(AkshareFetcher, "_set_random_user_agent", lambda self: None):
            df = fetcher._fetch_hk_data("00700", "2001-08-01", "2001-08-31")
        self.assertEqual(int(df["成交量"].iloc[0]), 406318)


if __name__ == "__main__":
    unittest.main()
