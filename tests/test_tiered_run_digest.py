# -*- coding: utf-8 -*-
"""Offline tests for the run-list facts (run_digest.py) and their
one-time backfill into the tiered_runs columns (2026-09-21)."""
from __future__ import annotations

import json
import os

import pytest

from src.tiered_analysis.run_digest import (
    DIGEST_COLUMNS,
    digest_from_inputs,
    digest_from_json,
    digest_from_result,
)


class TestDigestFromInputs:
    def test_picks_the_input_columns_and_nothing_else(self):
        digest = digest_from_inputs({
            "tier": 2, "capital": 100000, "risk_fraction": 0.01,
            "reward_risk": 2.0, "hold_weeks": 3,
            "sizing_overrides": {"capital": 100000},
        })
        assert digest == {"tier": 2, "capital": 100000, "risk_fraction": 0.01,
                          "reward_risk": 2.0, "hold_weeks": 3}

    def test_missing_inputs_are_none(self):
        assert digest_from_inputs(None) == {
            "tier": None, "capital": None, "risk_fraction": None,
            "reward_risk": None, "hold_weeks": None,
        }


class TestDigestFromResult:
    def test_report_values_only_for_what_the_report_has(self):
        digest = digest_from_result({
            "outlook": "bullish", "depth": 2, "hold_weeks": 2,
            "sizing": {"shares": 41, "inputs": {
                "capital": 50000, "risk_fraction": 0.02, "reward_risk": None,
            }},
        })
        assert digest == {"outlook": "bullish", "shares": 41, "capital": 50000,
                          "risk_fraction": 0.02, "tier": 2, "hold_weeks": 2}

    def test_sizing_that_bought_nothing_is_zero_shares(self):
        assert digest_from_result({"sizing": {"shares": None}}) == {"shares": 0}

    def test_no_sizing_block_means_no_shares_key(self):
        assert digest_from_result({"outlook": "neutral"}) == {"outlook": "neutral"}

    def test_garbage_is_empty(self):
        assert digest_from_result(None) == {}
        assert digest_from_result({"sizing": "nope", "depth": "2"}) == {}


class TestDigestFromJson:
    def test_inputs_then_report_on_finished_runs(self):
        digest = digest_from_json(
            json.dumps({"tier": 2, "capital": 100000, "hold_weeks": 3}),
            json.dumps({"outlook": "bearish", "sizing": {"shares": 5,
                        "inputs": {"capital": 60000}}}),
            "done",
        )
        assert digest == {"tier": 2, "capital": 60000, "risk_fraction": None,
                          "reward_risk": None, "hold_weeks": 3,
                          "outlook": "bearish", "shares": 5}

    def test_report_ignored_unless_done(self):
        digest = digest_from_json(
            json.dumps({"tier": 1}), json.dumps({"outlook": "bullish"}), "failed",
        )
        assert digest["tier"] == 1 and digest["outlook"] is None

    def test_unreadable_json_degrades_to_none(self):
        digest = digest_from_json("{not json", "[1, 2]", "done")
        assert digest == {column: None for column in DIGEST_COLUMNS}


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


class TestBackfillMigration:
    """Rows stored before the columns existed are filled once at startup
    from their JSON, and the marker keeps it from running again."""

    def test_startup_fills_old_rows_once(self, isolated_db):
        from src.storage import (
            DIGEST_MIGRATION_VERSION, DatabaseManager, DatabaseSchemaMigration,
            TieredRunRecord,
        )

        with isolated_db.get_session() as session:
            # A fresh database already carries the marker; pretend it is
            # a database from before the columns.
            session.query(DatabaseSchemaMigration).filter_by(
                version=DIGEST_MIGRATION_VERSION
            ).delete()
            session.add(TieredRunRecord(
                task_id="old-done", stock_code="AAPL", status="done",
                inputs_json=json.dumps({"tier": 2, "capital": 100000,
                                        "risk_fraction": 0.01, "hold_weeks": 2}),
                result_json=json.dumps({"outlook": "bullish", "depth": 2,
                                        "sizing": {"shares": 7, "inputs": {
                                            "capital": 100000, "reward_risk": 2.0}}}),
            ))
            session.add(TieredRunRecord(
                task_id="old-failed", stock_code="NVDA", status="failed",
                inputs_json=json.dumps({"tier": 1, "capital": 5000}),
                result_json=None,
            ))
            session.add(TieredRunRecord(
                task_id="bare", stock_code="MSFT", status="running",
            ))
            session.commit()
            stamped = {
                row.task_id: row.updated_at
                for row in session.query(TieredRunRecord)
            }

        DatabaseManager.reset_instance()
        db = DatabaseManager.get_instance()

        with db.get_session() as session:
            done = session.query(TieredRunRecord).filter_by(task_id="old-done").one()
            assert (done.tier, done.capital, done.risk_fraction, done.reward_risk,
                    done.hold_weeks, done.outlook, done.shares) == (
                2, 100000, 0.01, 2.0, 2, "bullish", 7)
            failed = session.query(TieredRunRecord).filter_by(task_id="old-failed").one()
            assert (failed.tier, failed.capital, failed.outlook) == (1, 5000, None)
            bare = session.query(TieredRunRecord).filter_by(task_id="bare").one()
            assert all(getattr(bare, column) is None for column in DIGEST_COLUMNS)
            # Nobody touched these runs: their timestamps stand.
            for row in session.query(TieredRunRecord):
                assert row.updated_at == stamped[row.task_id]
            assert session.get(DatabaseSchemaMigration, DIGEST_MIGRATION_VERSION) is not None

    def test_columns_are_added_to_a_database_created_before_them(self, isolated_db):
        from sqlalchemy import inspect

        from src.storage import DIGEST_COLUMN_DDL, DatabaseManager

        with isolated_db._engine.begin() as connection:
            for column in DIGEST_COLUMN_DDL:
                connection.exec_driver_sql(f"DROP INDEX IF EXISTS ix_tiered_runs_{column}")
                connection.exec_driver_sql(f"ALTER TABLE tiered_runs DROP COLUMN {column}")
        DatabaseManager.reset_instance()
        db = DatabaseManager.get_instance()
        names = {col["name"] for col in inspect(db._engine).get_columns("tiered_runs")}
        assert set(DIGEST_COLUMN_DDL) <= names
