# -*- coding: utf-8 -*-
"""Offline tests for the server-status document (server_status.py,
2026-09-21): what a client learns before it acts."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.tiered_analysis import history
from src.tiered_analysis.server_status import DATA_SOURCE_ENV, server_status


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "server_status.db")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


@pytest.fixture()
def bare_env(monkeypatch):
    """No model, no key, no data source, default slots."""
    for name in ("MAIN_LLM", "SUB_LLM", "LLM_API_KEY", "MAX_CONCURRENT_RUNS",
                 *DATA_SOURCE_ENV.values()):
        monkeypatch.delenv(name, raising=False)


# Wednesday 2026-08-05 18:00 UTC: 14:00 in New York (mid-session),
# 02:00 Thursday in Shanghai (before the open).
NOW = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)


class TestServerStatus:
    def test_nothing_configured(self, isolated_db, bare_env):
        status = server_status(now=NOW)
        assert status["server_time"] == "2026-08-05T18:00:00+00:00"
        assert status["llm"] == {"main_model": None, "sub_model": None,
                                 "api_key_set": False}
        assert status["data_sources"] == {
            "finnhub": False, "alphavantage": False, "fred": False, "sec_edgar": False,
        }
        assert status["runs"] == {"max_concurrent": 4, "running": 0, "queued": 0}
        assert status["defaults"] == {
            "capital": 100_000.0, "risk_pct": 1.0, "reward_ratio": 2.0,
            "max_hold_weeks": 2, "tier": 1,
        }
        assert status["transcript_retention_days"] == 14

    def test_configuration_and_queue_show_but_never_the_key(
        self, isolated_db, bare_env, monkeypatch,
    ):
        monkeypatch.setenv("MAIN_LLM", "gemini/pro")
        monkeypatch.setenv("LLM_API_KEY", "sk-secret")
        monkeypatch.setenv("FINNHUB_API_KEY", "fh")
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "me (me@example.com)")
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "2")
        history.create_run("a", "AAPL", status="queued")
        history.create_run("b", "AAPL", status="queued")
        history.create_run("c", "AAPL")

        status = server_status(now=NOW)

        assert status["llm"] == {"main_model": "gemini/pro", "sub_model": "gemini/pro",
                                 "api_key_set": True}
        assert "sk-secret" not in repr(status)
        assert status["data_sources"]["finnhub"] is True
        assert status["data_sources"]["sec_edgar"] is True
        assert status["data_sources"]["fred"] is False
        assert status["runs"] == {"max_concurrent": 2, "running": 1, "queued": 2}

    def test_each_market_clock(self, isolated_db, bare_env):
        markets = {m["market"]: m for m in server_status(now=NOW)["markets"]}
        assert list(markets) == ["cn", "hk", "us", "jp", "kr", "tw"]
        us = markets["us"]
        assert us["timezone"] == "America/New_York"
        assert us["local_time"] == NOW.astimezone(ZoneInfo("America/New_York")).isoformat()
        assert us["runs_blocked"] is True
        assert us["session_open"].startswith("2026-08-05T09:30")
        assert us["runs_allowed_from"].startswith("2026-08-05T16:30")
        cn = markets["cn"]
        assert cn["runs_blocked"] is False and cn["runs_allowed_from"] is None
        assert cn["local_time"].startswith("2026-08-06T02:00")

    def test_naive_now_is_utc_and_default_now_is_now(self, isolated_db, bare_env):
        naive = server_status(now=NOW.replace(tzinfo=None))
        assert naive["server_time"] == "2026-08-05T18:00:00+00:00"
        live = server_status()
        assert live["server_time"].endswith("+00:00")
