# -*- coding: utf-8 -*-
"""Offline tests for the run-list facts (run_digest.py, 2026-09-21) and
the startup reset of run tables from before the page vocabulary
(2026-09-24)."""
from __future__ import annotations

import json
import os

import pytest

from src.tiered_analysis.run_digest import (
    RUN_LIST_COLUMNS,
    digest_from_inputs,
    digest_from_json,
    digest_from_result,
)


class TestDigestFromInputs:
    def test_picks_the_input_columns_and_nothing_else(self):
        digest = digest_from_inputs({
            "tier": 2, "capital": 100000, "risk_pct": 1.0,
            "reward_ratio": 2.0, "max_hold_weeks": 3,
            "run_anyway": True,
        })
        assert digest == {"tier": 2, "capital": 100000, "risk_pct": 1.0,
                          "reward_ratio": 2.0, "max_hold_weeks": 3}

    def test_missing_inputs_are_none(self):
        assert digest_from_inputs(None) == {
            "tier": None, "capital": None, "risk_pct": None,
            "reward_ratio": None, "max_hold_weeks": None,
        }


class TestDigestFromResult:
    def test_report_values_only_for_what_the_report_has(self):
        digest = digest_from_result({
            "outlook": "bullish", "tier": 2, "max_hold_weeks": 2,
            "sizing": {"shares": 41, "inputs": {
                "capital": 50000, "risk_pct": 2.0, "reward_ratio": None,
            }},
        })
        assert digest == {"outlook": "bullish", "shares": 41, "capital": 50000,
                          "risk_pct": 2.0, "tier": 2, "max_hold_weeks": 2}

    def test_sizing_that_bought_nothing_is_zero_shares(self):
        assert digest_from_result({"sizing": {"shares": None}}) == {"shares": 0}

    def test_no_sizing_block_means_no_shares_key(self):
        assert digest_from_result({"outlook": "neutral"}) == {"outlook": "neutral"}

    def test_garbage_is_empty(self):
        assert digest_from_result(None) == {}
        assert digest_from_result({"sizing": "nope", "tier": "2"}) == {}


class TestDigestFromJson:
    def test_inputs_then_report_on_finished_runs(self):
        digest = digest_from_json(
            json.dumps({"tier": 2, "capital": 100000, "max_hold_weeks": 3}),
            json.dumps({"outlook": "bearish", "sizing": {"shares": 5,
                        "inputs": {"capital": 60000}}}),
            "done",
        )
        assert digest == {"tier": 2, "capital": 60000, "risk_pct": None,
                          "reward_ratio": None, "max_hold_weeks": 3,
                          "outlook": "bearish", "shares": 5}

    def test_report_ignored_unless_done(self):
        digest = digest_from_json(
            json.dumps({"tier": 1}), json.dumps({"outlook": "bullish"}), "failed",
        )
        assert digest["tier"] == 1 and digest["outlook"] is None

    def test_unreadable_json_degrades_to_none(self):
        digest = digest_from_json("{not json", "[1, 2]", "done")
        assert digest == {column: None for column in RUN_LIST_COLUMNS}


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "digest.db")
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


class TestLegacyTableReset:
    """A database whose run tables predate the page vocabulary (they
    still carry ``task_id``) has those tables dropped and recreated
    empty at startup; the chat and cache tables are untouched and a
    marker records that it happened (owner decision 2026-09-24: the old
    runs were test runs)."""

    def test_old_shaped_run_tables_are_recreated_empty(self, isolated_db):
        from sqlalchemy import inspect

        from src.storage import (
            VOCABULARY_RESET_VERSION, DatabaseManager, DatabaseSchemaMigration,
            TieredCacheRecord, TieredRunRecord, TieredRunTranscriptRecord,
        )

        with isolated_db.get_session() as session:
            session.add(TieredCacheRecord(key="keep", value_json="1"))
            session.commit()
        with isolated_db._engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE tiered_run_transcripts")
            connection.exec_driver_sql("DROP TABLE tiered_runs")
            connection.exec_driver_sql(
                "CREATE TABLE tiered_runs (id INTEGER PRIMARY KEY, task_id VARCHAR(64), "
                "stock_code VARCHAR(16), status VARCHAR(16))"
            )
            connection.exec_driver_sql(
                "INSERT INTO tiered_runs (task_id, stock_code, status) VALUES ('old', 'AAPL', 'done')"
            )
            connection.exec_driver_sql(
                "CREATE TABLE tiered_run_transcripts (id INTEGER PRIMARY KEY, task_id VARCHAR(64), seq INTEGER)"
            )

        DatabaseManager.reset_instance()
        db = DatabaseManager.get_instance()

        names = {col["name"] for col in inspect(db._engine).get_columns("tiered_runs")}
        assert {"run_id", "ticker", "risk_pct", "reward_ratio", "max_hold_weeks"} <= names
        assert "task_id" not in names
        transcript_names = {
            col["name"] for col in inspect(db._engine).get_columns("tiered_run_transcripts")
        }
        assert {"run_id", "call_number", "llm", "input", "output"} <= transcript_names
        with db.get_session() as session:
            assert session.query(TieredRunRecord).count() == 0
            assert session.query(TieredRunTranscriptRecord).count() == 0
            assert session.get(TieredCacheRecord, "keep") is not None
            assert session.get(DatabaseSchemaMigration, VOCABULARY_RESET_VERSION) is not None

    def test_a_current_database_is_left_alone(self, isolated_db):
        from src.storage import (
            VOCABULARY_RESET_VERSION, DatabaseManager, DatabaseSchemaMigration,
            TieredRunRecord,
        )

        with isolated_db.get_session() as session:
            session.add(TieredRunRecord(run_id="fresh", ticker="AAPL", status="done"))
            session.commit()
        DatabaseManager.reset_instance()
        db = DatabaseManager.get_instance()
        with db.get_session() as session:
            assert session.query(TieredRunRecord).filter_by(run_id="fresh").one()
            assert session.get(DatabaseSchemaMigration, VOCABULARY_RESET_VERSION) is None
