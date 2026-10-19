# -*- coding: utf-8 -*-
"""The run service lives in ``src``, below the HTTP layer (2026-10-10).

Why: the chat's tools (``src.chat.tools``) used to import the run
queue, ``submit_run`` and the request shape from the tiered route
module in ``api``. Nothing in ``api`` imported ``src.chat`` back, so
there was no cycle yet, but one such import added to the route would
have produced a cycle that only fails at request time. Now both the
route and the chat import the same ``src.tiered_analysis.run_service``
and ``src.tiered_analysis.run_request``, and no module under ``src``
imports from ``api``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from api.v1.endpoints import tiered, tiered_schemas
from src.chat import tools
from src.tiered_analysis import history, run_request, run_service


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "run_service.db")
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

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


class TestLayering:
    def test_nothing_under_src_imports_from_api(self):
        offenders = []
        for path in SRC_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*(?:from api\b|import api\b)", text, re.M):
                offenders.append(str(path.relative_to(SRC_ROOT.parent)))
        assert offenders == []

    def test_the_route_and_the_chat_share_one_queue(self):
        assert tiered.run_service.run_queue is run_service.run_queue
        assert tools.run_service.run_queue is run_service.run_queue

    def test_the_route_and_the_chat_share_one_request_shape(self):
        assert tiered.TieredAnalyzeRequest is run_request.TieredAnalyzeRequest
        assert tiered_schemas.TieredAnalyzeRequest is run_request.TieredAnalyzeRequest
        assert tools.TieredAnalyzeRequest is run_request.TieredAnalyzeRequest


class TestExecuteRunStopped:
    """``_execute_run`` records a stopped run with what finished."""

    def _queued(self, run_id="r1", ticker="AAPL", tier=1):
        from src.tiered_analysis.run_queue import QueuedRun

        history.create_run(run_id, ticker, inputs={"tier": tier}, status=history.STATUS_QUEUED)
        history.mark_running(run_id)
        return QueuedRun(run_id=run_id, ticker=ticker, inputs={"tier": tier, "max_hold_weeks": 2})

    def test_the_runs_stop_flag_reaches_the_engine(self, isolated_db):
        from unittest.mock import patch

        run = self._queued()
        seen = {}

        def fake(code, **kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop here")

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)
        assert seen["stop"] is run.stop

    def test_a_stopped_run_keeps_the_finished_sections(self, isolated_db):
        from unittest.mock import patch

        from src.tiered_analysis.providers.base import DataReport, Market, SourceKind
        from src.tiered_analysis.run_control import RunStopped, RunProgress

        run = self._queued()
        partial = RunProgress(
            stage="positioning", ticker="AAPL", market=Market.US, tier=1, max_hold_weeks=2,
            data_reports=[
                DataReport(name="technicals", kind=SourceKind.NUMERIC, payload={"close": 1}),
                DataReport(name="fundamentals", kind=SourceKind.NUMERIC, payload={"eps": 2}),
            ],
            llm_usage={"stages": {}, "total": {"calls": 0, "input_tokens": 0, "output_tokens": 0}},
        )

        def fake(code, **kwargs):
            raise RunStopped("positioning", partial=partial)

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)

        row = history.get_run("r1")
        assert row["status"] == "stopped"
        assert row["error"] is None
        result = row["result"]
        # No pressed stage recorded: the landing stage stands, unfinished.
        assert result["stopped_stage"] == "positioning"
        assert result["stopped_stage_finished"] is False
        assert result["ticker"] == "AAPL"
        assert result["market"] == "us"
        assert result["tier"] == 1
        assert [d["name"] for d in result["data_reports"]] == ["technicals", "fundamentals"]
        assert result["data_reports"][0]["payload"] == {"close": 1}
        # Nothing after the cards ran: no outlook, no plan.
        assert "outlook" not in result
        assert "action" not in result
        assert result["levels"] == {"entry": None, "stop_loss": None, "target": None}
        assert result["levels_detail"] is None
        assert result["sizing"] is None
        assert result["plan_warnings"] is None
        assert result["deep_analysis"] is None
        assert result["preliminary_analysis"] is None
        assert result["llm_usage"]["total"]["calls"] == 0
        # The row shows no outlook and no shares in the list.
        assert row["outlook"] is None
        assert row["shares"] is None

    def test_a_stop_at_the_trade_plan_keeps_the_analysis(self, isolated_db):
        from unittest.mock import patch

        from src.tiered_analysis.providers.base import DataReport, Market, SourceKind
        from src.tiered_analysis.run_control import RunStopped, RunProgress
        from src.tiered_analysis.schema import Outlook, TierReport, TradePlanLevels

        run = self._queued(tier=2)
        levels = TradePlanLevels(entry=96.0, stop_loss=90.0, target=108.0)
        deep = TierReport(
            tier=2, ticker="AAPL", market=Market.US, outlook=Outlook.BULLISH,
            levels=levels, summary="the vote settled it", warnings=["one lister dropped out"],
            detail={"outlook": {"outlook": "bullish", "final_score": 7.4}, "items": []},
        )
        partial = RunProgress(
            stage="trade_plan", ticker="AAPL", market=Market.US, tier=2, max_hold_weeks=2,
            data_reports=[DataReport(name="technicals", kind=SourceKind.NUMERIC, payload={"close": 1})],
            levels=levels, levels_detail={"levels": {}, "warnings": []},
            level_warnings=["entry: no support found"], deep=deep,
            llm_usage={"stages": {}, "total": {"calls": 7, "input_tokens": 10, "output_tokens": 5}},
            # Stop was pressed during the deep analysis, which still
            # finished; the stop landed at the trade plan.
            pressed_stage="deep_analysis",
        )

        def fake(code, **kwargs):
            raise RunStopped("trade_plan", partial=partial)

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)

        result = history.get_run("r1")["result"]
        assert result["stopped_stage"] == "deep_analysis"
        assert result["stopped_stage_finished"] is True
        assert result["outlook"] == "bullish"
        assert "action" not in result
        assert result["summary"] == "the vote settled it"
        assert result["deep_analysis"]["outlook"] == "bullish"
        assert result["deep_analysis"]["warnings"] == ["one lister dropped out"]
        assert result["deep_analysis"]["detail"]["outlook"]["final_score"] == 7.4
        assert result["levels"] == {"entry": 96.0, "stop_loss": 90.0, "target": 108.0}
        # The plan review never finished, so its receipt is absent even
        # though the formula levels exist.
        assert result["levels_detail"] is None
        assert result["sizing"] is None
        assert result["warnings"] == ["entry: no support found"]
        assert result["llm_usage"]["total"]["calls"] == 7

    def test_a_stop_pressed_between_steps_names_the_step_it_landed_in(self, isolated_db):
        from unittest.mock import patch

        from src.tiered_analysis.providers.base import Market
        from src.tiered_analysis.run_control import RunStopped, RunProgress

        run = self._queued()
        partial = RunProgress(stage="preliminary_analysis", ticker="AAPL", market=Market.US,
                             tier=1, max_hold_weeks=2, pressed_stage="unknown")

        def fake(code, **kwargs):
            raise RunStopped("preliminary_analysis", partial=partial)

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)
        result = history.get_run("r1")["result"]
        assert result["stopped_stage"] == "preliminary_analysis"
        assert result["stopped_stage_finished"] is False

    def test_a_stop_without_a_partial_still_lands_as_stopped(self, isolated_db):
        from unittest.mock import patch

        from src.tiered_analysis.run_control import RunStopped

        run = self._queued()

        def fake(code, **kwargs):
            raise RunStopped("technicals")

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)
        row = history.get_run("r1")
        assert row["status"] == "stopped"
        assert row["result"]["stopped_stage"] == "technicals"
        assert row["result"]["data_reports"] == []
        assert row["result"]["market"] == "us"


class TestExecuteRunProgress:
    """``_execute_run`` stores each progress snapshot on the row while
    the run is running (2026-10-19), and the end replaces it."""

    def _queued(self, run_id="r1", ticker="AAPL"):
        from src.tiered_analysis.run_queue import QueuedRun

        history.create_run(run_id, ticker, inputs={"tier": 1}, status=history.STATUS_QUEUED)
        history.mark_running(run_id)
        return QueuedRun(run_id=run_id, ticker=ticker, inputs={"tier": 1, "max_hold_weeks": 2})

    def _snapshot(self, stage, ticker="AAPL"):
        from src.tiered_analysis.providers.base import DataReport, Market, SourceKind
        from src.tiered_analysis.run_control import RunProgress

        return RunProgress(
            stage=stage, ticker=ticker, market=Market.US, tier=1, max_hold_weeks=2,
            data_reports=[DataReport(name="technicals", kind=SourceKind.NUMERIC, payload={"close": 1})],
            llm_usage={"stages": {}, "total": {"calls": 0, "input_tokens": 0, "output_tokens": 0}},
            stages=["technicals", "fundamentals", "preliminary_analysis", "trade_plan"],
        )

    def test_each_snapshot_lands_on_the_running_row_and_the_end_replaces_it(self, isolated_db):
        from unittest.mock import patch

        from tests.test_tiered_api import _outcome

        run = self._queued()
        during = {}

        def fake(code, progress=None, **kwargs):
            progress(self._snapshot("fundamentals"))
            during.update(history.get_run("r1"))
            return _outcome(code)

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)

        # Mid-run: still running, with the finished card and the step in progress.
        assert during["status"] == "running"
        result = during["result"]
        assert result["running_stage"] == "fundamentals"
        assert result["stages"] == ["technicals", "fundamentals", "preliminary_analysis", "trade_plan"]
        assert [d["name"] for d in result["data_reports"]] == ["technicals"]
        assert result["data_report_index"][0]["name"] == "technicals"
        assert "stopped_stage" not in result
        assert "outlook" not in result
        assert result["sizing"] is None
        assert during["outlook"] is None and during["shares"] is None
        # The end: the full report, no trace of the snapshot.
        row = history.get_run("r1")
        assert row["status"] == "succeeded"
        assert "running_stage" not in row["result"]
        assert row["result"]["outlook"] == "neutral"

    def test_a_failure_after_progress_leaves_no_report(self, isolated_db):
        from unittest.mock import patch

        run = self._queued()

        def fake(code, progress=None, **kwargs):
            progress(self._snapshot("fundamentals"))
            raise RuntimeError("provider down")

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)
        row = history.get_run("r1")
        assert row["status"] == "failed"
        assert row["error"] == "provider down"
        assert row["result"] is None

    def test_a_stop_after_progress_stores_the_stopped_report(self, isolated_db):
        from unittest.mock import patch

        from src.tiered_analysis.run_control import RunStopped

        run = self._queued()

        def fake(code, progress=None, **kwargs):
            progress(self._snapshot("fundamentals"))
            raise RunStopped("fundamentals", partial=self._snapshot("fundamentals"))

        with patch.object(run_service, "_run_analysis", fake):
            run_service._execute_run(run)
        row = history.get_run("r1")
        assert row["status"] == "stopped"
        assert row["result"]["stopped_stage"] == "fundamentals"
        assert "running_stage" not in row["result"]
        assert row["result"]["stages"][-1] == "trade_plan"

    def test_the_running_report_is_the_stopped_shape_plus_the_step(self):
        running = run_service._serialize_running(self._snapshot("fundamentals"))
        assert running["running_stage"] == "fundamentals"
        assert running["final"] is None
        assert running["levels"] == {"entry": None, "stop_loss": None, "target": None}
        assert [d["name"] for d in running["data_reports"]] == ["technicals"]
