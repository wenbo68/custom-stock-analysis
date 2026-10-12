# -*- coding: utf-8 -*-
"""Offline tests for the global run queue (2026-09-15).

At most MAX_CONCURRENT_RUNS runs execute at once; the rest wait
as ``queued`` rows and start first come, first served. The line lives in
the database so a restart resumes it. Uses the repo-standard isolated
sqlite fixture; runners are fakes gated on threading events.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

from src.tiered_analysis import history
from src.tiered_analysis.run_queue import (
    DEFAULT_MAX_CONCURRENT_RUNS,
    MAX_CONCURRENT_RUNS_ENV,
    QueuedRun,
    RunQueue,
    max_concurrent_runs,
)


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "run_queue.db")
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


def _wait_until(predicate, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition never became true")


class _GatedRunner:
    """A runner that records what it was handed and blocks each run until
    the test releases it, so the test controls how many are in flight."""

    def __init__(self) -> None:
        self.started: list = []
        self.finished: list = []
        self.release = threading.Event()

    def __call__(self, run: QueuedRun) -> None:
        self.started.append(run)
        self.release.wait(timeout=5)
        history.mark_succeeded(run.run_id, {"ticker": run.ticker})
        self.finished.append(run.run_id)


class TestMaxConcurrentRuns:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv(MAX_CONCURRENT_RUNS_ENV, raising=False)
        assert max_concurrent_runs() == DEFAULT_MAX_CONCURRENT_RUNS

    def test_env_value_wins(self, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, " 3 ")
        assert max_concurrent_runs() == 3

    @pytest.mark.parametrize("raw", ["0", "-1", "two", "1.5"])
    def test_bad_values_fall_back_to_the_default(self, monkeypatch, raw):
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, raw)
        assert max_concurrent_runs() == DEFAULT_MAX_CONCURRENT_RUNS


class TestRunQueue:
    def test_runs_start_in_order_up_to_the_cap(self, isolated_db, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, "1")
        runner = _GatedRunner()
        queue = RunQueue(runner)
        history.create_run("first", "AAPL", status=history.STATUS_QUEUED,
                           inputs={"tier": 2, "max_hold_weeks": 3})
        history.create_run("second", "MSFT", status=history.STATUS_QUEUED)

        assert queue.submit("first") == "running"
        assert queue.submit("second") == "queued"
        _wait_until(lambda: len(runner.started) == 1)
        assert runner.started[0] == QueuedRun(
            run_id="first", ticker="AAPL", inputs={"tier": 2, "max_hold_weeks": 3},
        )
        assert history.get_run("first")["status"] == "running"
        assert history.get_run("second")["status"] == "queued"
        assert queue.active_count == 1

        runner.release.set()
        _wait_until(lambda: runner.finished == ["first", "second"])
        assert history.get_run("second")["status"] == "succeeded"
        assert queue.active_count == 0

    def test_two_slots_run_two_at_once(self, isolated_db, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, "2")
        runner = _GatedRunner()
        queue = RunQueue(runner)
        for run_id in ("a", "b", "c"):
            history.create_run(run_id, "AAPL", status=history.STATUS_QUEUED)

        assert queue.dispatch() == ["a", "b"]
        _wait_until(lambda: len(runner.started) == 2)
        assert history.get_run("c")["status"] == "queued"
        assert history.get_run("c")["queue_position"] == 1

        runner.release.set()
        _wait_until(lambda: len(runner.finished) == 3)

    def test_resume_picks_up_rows_left_by_a_previous_process(self, isolated_db):
        runner = _GatedRunner()
        runner.release.set()
        history.create_run("left-over", "AAPL", status=history.STATUS_QUEUED)
        history.create_run("finished", "MSFT")
        history.mark_succeeded("finished", {})

        assert RunQueue(runner).resume() == ["left-over"]
        _wait_until(lambda: runner.finished == ["left-over"])
        assert RunQueue(runner).resume() == []

    def test_a_runner_that_raises_frees_its_slot(self, isolated_db, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, "1")
        seen = []

        def bad_runner(run: QueuedRun) -> None:
            seen.append(run.run_id)
            raise RuntimeError("boom")

        queue = RunQueue(bad_runner)
        history.create_run("x", "AAPL", status=history.STATUS_QUEUED)
        history.create_run("y", "AAPL", status=history.STATUS_QUEUED)
        queue.dispatch()
        _wait_until(lambda: seen == ["x", "y"])
        _wait_until(lambda: queue.active_count == 0)

    def test_a_thread_that_cannot_start_fails_the_run_and_frees_the_slot(self, isolated_db, monkeypatch):
        """Regression (2026-10-10): the row was marked running and the
        slot taken before the thread started, so a failed start left a
        run ``running`` forever and one slot lost until restart."""
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, "1")
        runner = _GatedRunner()
        queue = RunQueue(runner)
        history.create_run("doomed", "AAPL", status=history.STATUS_QUEUED)
        history.create_run("next", "MSFT", status=history.STATUS_QUEUED)

        def cannot_start(self):
            raise RuntimeError("can't start new thread")

        monkeypatch.setattr(threading.Thread, "start", cannot_start)
        assert queue.dispatch() == []
        assert queue.active_count == 0
        assert history.get_run("doomed")["status"] == "failed"
        assert "can't start new thread" in history.get_run("doomed")["error"]
        # The line moved on to the next run, which failed the same way.
        assert history.get_run("next")["status"] == "failed"

    def test_remove_cancels_a_queued_run_and_refuses_a_running_one(
        self, isolated_db, monkeypatch,
    ):
        monkeypatch.setenv(MAX_CONCURRENT_RUNS_ENV, "1")
        runner = _GatedRunner()
        queue = RunQueue(runner)
        history.create_run("first", "AAPL", status=history.STATUS_QUEUED)
        history.create_run("second", "MSFT", status=history.STATUS_QUEUED)
        queue.dispatch()
        _wait_until(lambda: len(runner.started) == 1)

        # The executing run cannot be removed; the waiting one leaves the line.
        with pytest.raises(history.RunInProgressError):
            queue.remove("first")
        assert queue.remove("second")["status"] == "queued"
        assert queue.remove("second") is None
        assert not history.run_exists("second")

        # When the slot frees, the cancelled run is not started.
        runner.release.set()
        _wait_until(lambda: runner.finished == ["first"])
        _wait_until(lambda: queue.active_count == 0)
        assert [run.run_id for run in runner.started] == ["first"]
        # And a finished run can go.
        assert queue.remove("first")["status"] == "succeeded"

    def test_queue_ahead_counts_the_earlier_rows(self, isolated_db):
        history.create_run("p", "AAPL", status=history.STATUS_QUEUED)
        history.create_run("q", "MSFT", status=history.STATUS_QUEUED)
        history.create_run("r", "NVDA", status=history.STATUS_QUEUED)
        by_id = {row["run_id"]: row for row in history.list_runs()["items"]}
        assert by_id["p"]["queue_position"] == 1
        assert by_id["q"]["queue_position"] == 2
        assert by_id["r"]["queue_position"] == 3
        assert history.get_run("q")["queue_position"] == 2
        history.mark_succeeded("p", {})
        assert history.get_run("p")["queue_position"] is None


class TestActiveDuplicate:
    INPUTS = {"tier": 1, "capital": 100000.0, "risk_pct": 1.0,
              "reward_ratio": 2.0, "max_hold_weeks": 2}

    def test_same_ticker_and_inputs_is_a_duplicate(self, isolated_db):
        history.create_run("t1", "AAPL", status=history.STATUS_QUEUED,
                           inputs={**self.INPUTS, "sizing_overrides": {"capital": 100000}})
        found = history.find_active_duplicate("aapl ", self.INPUTS)
        assert found == {"run_id": "t1", "status": "queued"}
        history.mark_running("t1")
        assert history.find_active_duplicate("AAPL", self.INPUTS)["status"] == "running"

    def test_finished_failed_or_other_inputs_are_not(self, isolated_db):
        history.create_run("succeeded", "AAPL", inputs=self.INPUTS)
        history.mark_succeeded("succeeded", {})
        history.create_run("failed", "AAPL", inputs=self.INPUTS)
        history.mark_failed("failed", "x")
        history.create_run("deeper", "AAPL",
                           inputs={**self.INPUTS, "tier": 2})
        history.create_run("other", "MSFT", inputs=self.INPUTS)
        assert history.find_active_duplicate("AAPL", self.INPUTS) is None
