# -*- coding: utf-8 -*-
"""Offline tests for the database-backed storage (2026-09-14):

- DATABASE_URL (Postgres) beats the sqlite path, with the driver
  spelled out the way SQLAlchemy needs it;
- startup housekeeping marks orphaned "running" runs failed and prunes
  old transcript and cache rows;
- the per-run transcript round-trips through the database and is served
  by its own endpoint;
- the database-backed cache store round-trips, tolerates corrupt rows,
  and never raises.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import tiered
from src.tiered_analysis import run_service
from src.config import Config, _normalize_database_url
from src.tiered_analysis import history
from src.tiered_analysis.cache_store import DbCacheStore, prune_cache
from src.tiered_analysis.llm_support import LlmTranscript


@pytest.fixture()
def isolated_db(tmp_path):
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    old_database_url = os.environ.pop("DATABASE_URL", None)
    os.environ["DATABASE_PATH"] = str(tmp_path / "housekeeping.db")
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
        if old_database_url is not None:
            os.environ["DATABASE_URL"] = old_database_url


class TestDatabaseUrl:
    def test_postgres_urls_get_the_driver_spelled_out(self):
        assert _normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
        assert (
            _normalize_database_url("postgresql://u:p@h/db?sslmode=require")
            == "postgresql+psycopg://u:p@h/db?sslmode=require"
        )
        assert _normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"

    def test_database_url_wins_over_the_sqlite_path(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.setenv("DATABASE_PATH", "/nowhere/x.db")
        Config.reset_instance()
        try:
            assert Config().get_db_url() == "postgresql+psycopg://u:p@h/db"
        finally:
            Config.reset_instance()

    def test_without_database_url_the_sqlite_path_is_used(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "x.db"))
        Config.reset_instance()
        try:
            assert Config().get_db_url().startswith("sqlite:///")
        finally:
            Config.reset_instance()


class TestStartupHousekeeping:
    def test_running_runs_are_marked_failed(self, isolated_db):
        history.create_run("orphan", "AAPL")
        history.create_run("finished", "MSFT")
        history.mark_done("finished", {"ticker": "MSFT"})

        assert history.fail_stale_running_runs() == 1

        orphan = history.get_run("orphan")
        assert orphan["status"] == "failed"
        assert orphan["error"] == history.STALE_RUN_ERROR
        assert history.get_run("finished")["status"] == "done"
        assert history.fail_stale_running_runs() == 0

    def test_old_transcript_rows_are_pruned_fresh_ones_kept(self, isolated_db):
        from src.storage import TieredRunTranscriptRecord, utc_naive_now

        old = utc_naive_now() - timedelta(days=history.TRANSCRIPT_MAX_AGE_DAYS + 1)
        with isolated_db.get_session() as session:
            session.add(TieredRunTranscriptRecord(
                run_id="old", call_number=1, created_at=old, stage="s", llm="m",
            ))
            session.add(TieredRunTranscriptRecord(
                run_id="fresh", call_number=1, stage="s", llm="m",
            ))
            session.commit()

        assert history.prune_transcripts() == 1
        assert history.list_transcript("old") == []
        assert len(history.list_transcript("fresh")) == 1

    def test_app_startup_runs_the_housekeeping(self, isolated_db):
        from api.app import create_app

        history.create_run("orphan", "AAPL")
        with TestClient(create_app()) as client:
            assert client.get("/api/health").status_code == 200
        assert history.get_run("orphan")["status"] == "failed"

    def test_app_startup_resumes_queued_runs(self, isolated_db, monkeypatch):
        """A run left ``queued`` by the previous process starts again
        under the new one (the line lives in the database)."""
        import time
        from unittest.mock import patch

        from api.app import create_app

        history.create_run("waiting", "AAPL", status=history.STATUS_QUEUED,
                           inputs={"tier": 2, "max_hold_weeks": 1})
        seen = {}

        def fake_run(code, **kwargs):
            seen.update(kwargs, code=code)
            from tests.test_tiered_api import _outcome
            return _outcome(code)

        with patch.object(run_service, "_run_analysis", fake_run):
            with TestClient(create_app()) as client:
                assert client.get("/api/health").status_code == 200
                deadline = time.time() + 5
                while time.time() < deadline and history.get_run("waiting")["status"] != "done":
                    time.sleep(0.05)
        assert history.get_run("waiting")["status"] == "done"
        assert seen["code"] == "AAPL"
        assert seen["tier"] == 2
        assert seen["max_hold_weeks"] == 1


class TestTranscriptStorage:
    def test_for_run_writes_rows_readable_in_call_order(self, isolated_db):
        transcript = LlmTranscript.for_run("task-9")
        transcript.record(
            stage="preliminary_analysis", llm="gemini/x", temperature=0.0,
            input="first", output="one", input_tokens=3, output_tokens=1,
            time_ms=10, structured="schema",
        )
        transcript.record(
            stage="trade_plan", llm="gemini/x", temperature=0.0,
            input="second", output=None, error="RuntimeError('boom')",
        )

        rows = history.list_transcript("task-9")
        assert [r["call_number"] for r in rows] == [1, 2]
        assert rows[0]["stage"] == "preliminary_analysis"
        assert rows[0]["structured"] == "schema"
        assert (rows[0]["input_chars"], rows[0]["output_chars"]) == (5, 3)
        assert rows[1]["output_chars"] == 0
        assert "boom" in rows[1]["error"]
        first = history.get_transcript_call("task-9", 1)
        assert (first["input"], first["output"]) == ("first", "one")
        assert history.get_transcript_call("task-9", 2)["output"] is None
        assert history.list_transcript("unknown") == []

    def test_transcript_endpoint_serves_the_rows_and_404s_unknown_runs(self, isolated_db):
        app = FastAPI()
        app.include_router(tiered.router, prefix="/tiered")
        client = TestClient(app)

        history.create_run("task-9", "AAPL")
        LlmTranscript.for_run("task-9").record(
            stage="s", llm="m", temperature=0.0, input="p", output="r",
        )

        response = client.get("/tiered/runs/task-9/transcript")
        assert response.status_code == 200
        [item] = response.json()["items"]
        # The index carries sizes, not text; the text is one call away.
        assert "input" not in item and "output" not in item
        assert (item["input_chars"], item["output_chars"]) == (1, 1)
        call = client.get("/tiered/runs/task-9/transcript/1").json()
        assert (call["input"], call["output"]) == ("p", "r")
        assert client.get("/tiered/runs/nope/transcript").status_code == 404


class TestDbCacheStore:
    def test_roundtrip_overwrite_and_missing(self, isolated_db):
        store = DbCacheStore()
        assert store.read("k") is None
        store.write("k", {"a": [1, 2]})
        assert store.read("k") == {"a": [1, 2]}
        store.write("k", [3])
        assert store.read("k") == [3]

    def test_corrupt_row_reads_as_missing(self, isolated_db):
        from src.storage import TieredCacheRecord

        with isolated_db.get_session() as session:
            session.add(TieredCacheRecord(key="bad", value_json="{not json"))
            session.commit()
        assert DbCacheStore().read("bad") is None

    def test_old_rows_are_pruned_fresh_ones_kept(self, isolated_db):
        from src.storage import TieredCacheRecord, utc_naive_now

        with isolated_db.get_session() as session:
            session.add(TieredCacheRecord(
                key="old", value_json="1",
                updated_at=utc_naive_now() - timedelta(days=61),
            ))
            session.add(TieredCacheRecord(key="fresh", value_json="2"))
            session.commit()
        assert prune_cache() == 1
        assert DbCacheStore().read("old") is None
        assert DbCacheStore().read("fresh") == 2

    def test_database_trouble_never_raises(self, monkeypatch):
        from src.storage import DatabaseManager

        def explode():
            raise RuntimeError("no database")

        monkeypatch.setattr(DatabaseManager, "get_instance", staticmethod(explode))
        store = DbCacheStore()
        assert store.read("k") is None
        store.write("k", 1)  # logged, not raised
