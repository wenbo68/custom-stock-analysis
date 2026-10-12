# -*- coding: utf-8 -*-
"""Offline tests for the warning-only next-earnings-date layer."""
from __future__ import annotations

import datetime as dt
import unittest

from unittest import mock

from src.tiered_analysis.earnings import (
    EARNINGS_WARNING_DAYS,
    EarningsInfo,
    earnings_from_data_reports,
    earnings_warning,
    market_today,
    next_earnings_info,
)
from src.tiered_analysis.providers.base import Market

TODAY = dt.date(2026, 7, 20)

#: 01:00 UTC on the 21st — still the evening of the 20th in New York,
#: already the morning of the 21st in Shanghai.
LATE_UTC = dt.datetime(2026, 7, 21, 1, 0, tzinfo=dt.timezone.utc)


def _wall_clock(fixed):
    """Patch the exchange-calendar module's clock to ``fixed`` (aware)."""
    patcher = mock.patch("src.core.trading_calendar.datetime")
    fake = patcher.start()
    fake.now.side_effect = (
        lambda tz=None: fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    )
    return patcher


class TestMarketToday(unittest.TestCase):
    """"Today" for the earnings and macro gates is the MARKET's date, not
    the server's (review 2026-10-10): on a UTC host after 20:00 New York
    time the server's date is one day ahead, so a 7-day gate fired a day
    early or late."""

    def test_us_today_is_the_new_york_date(self):
        self.assertEqual(market_today(Market.US, now=LATE_UTC), dt.date(2026, 7, 20))

    def test_cn_today_is_the_shanghai_date(self):
        self.assertEqual(market_today(Market.CN, now=LATE_UTC), dt.date(2026, 7, 21))

    def test_unknown_market_keeps_the_given_clock(self):
        self.assertEqual(market_today(Market.UNKNOWN, now=LATE_UTC), dt.date(2026, 7, 21))
        self.assertEqual(market_today(None, now=LATE_UTC), dt.date(2026, 7, 21))

    def test_earnings_gate_counts_from_the_market_date(self):
        dim = mock.Mock(name="fundamentals")
        dim.name = "fundamentals"
        dim.payload = {"quarterly_report": {"next_earnings_date": "2026-07-27"}}
        patcher = _wall_clock(LATE_UTC)
        try:
            info = earnings_from_data_reports([dim], market=Market.US)
        finally:
            patcher.stop()
        self.assertEqual(info.days_until, 7)  # from the 20th, not the 21st
        self.assertTrue(info.is_near)

    def test_next_earnings_lookup_counts_from_the_market_date(self):
        patcher = _wall_clock(LATE_UTC)
        try:
            info = next_earnings_info(
                "AAPL", Market.US, fetcher=lambda s: [dt.date(2026, 7, 20)],
            )
        finally:
            patcher.stop()
        # The 20th is still "today" in New York, so it is upcoming, not past.
        self.assertEqual(info.days_until, 0)


class TestNextEarningsInfo(unittest.TestCase):
    def test_picks_first_future_date(self):
        info = next_earnings_info(
            "AAPL", Market.US, today=TODAY,
            fetcher=lambda s: [dt.date(2026, 4, 30), dt.date(2026, 7, 29),
                               dt.date(2026, 10, 29)],
        )
        self.assertEqual(info.next_date, "2026-07-29")
        self.assertEqual(info.days_until, 9)
        self.assertFalse(info.is_near)

    def test_today_counts_as_upcoming(self):
        info = next_earnings_info(
            "AAPL", Market.US, today=TODAY, fetcher=lambda s: [TODAY]
        )
        self.assertEqual(info.days_until, 0)
        self.assertTrue(info.is_near)

    def test_within_window_is_near_with_warning(self):
        info = next_earnings_info(
            "AAPL", Market.US, today=TODAY,
            fetcher=lambda s: [TODAY + dt.timedelta(days=EARNINGS_WARNING_DAYS)],
        )
        self.assertTrue(info.is_near)
        warning = earnings_warning(info)
        self.assertIsNotNone(warning)
        self.assertIn("expect turbulence", warning)
        self.assertIn(info.next_date, warning)

    def test_outside_window_no_warning(self):
        info = next_earnings_info(
            "AAPL", Market.US, today=TODAY,
            fetcher=lambda s: [TODAY + dt.timedelta(days=30)],
        )
        self.assertFalse(info.is_near)
        self.assertIsNone(earnings_warning(info))

    def test_only_past_dates_yields_note(self):
        info = next_earnings_info(
            "AAPL", Market.US, today=TODAY,
            fetcher=lambda s: [dt.date(2026, 4, 30)],
        )
        self.assertIsNone(info.next_date)
        self.assertIn("no upcoming", info.note)

    def test_non_us_market_is_a_quiet_gap(self):
        info = next_earnings_info("600519", Market.CN, today=TODAY)
        self.assertIsNone(info.next_date)
        self.assertIn("not yet available", info.note)

    def test_fetch_failure_never_raises(self):
        def _boom(ticker):
            raise RuntimeError("api down")

        info = next_earnings_info("AAPL", Market.US, today=TODAY, fetcher=_boom)
        self.assertIsNone(info.next_date)
        self.assertIn("api down", info.note)

    def test_detail_is_json_ready(self):
        import json

        info = next_earnings_info(
            "AAPL", Market.US, today=TODAY,
            fetcher=lambda s: [TODAY + dt.timedelta(days=3)],
        )
        detail = info.to_detail()
        json.dumps(detail)
        self.assertEqual(detail["days_until"], 3)
        self.assertTrue(detail["is_near"])
        self.assertEqual(detail["warning_days"], EARNINGS_WARNING_DAYS)


class TestEarningsInfoDefaults(unittest.TestCase):
    def test_empty_info_is_not_near(self):
        self.assertFalse(EarningsInfo().is_near)
        self.assertIsNone(earnings_warning(EarningsInfo()))


if __name__ == "__main__":
    unittest.main()
