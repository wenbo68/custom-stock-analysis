# -*- coding: utf-8 -*-
"""Offline tests for the tiered-analysis API endpoint.

The real run takes minutes (LLM + data fetch), so the endpoint runs it
in a background thread and persists status/result to the tiered_runs
table; the client polls the run list/detail. Tests patch the runner with
fast fakes and use the repo-standard isolated sqlite fixture.
"""
from __future__ import annotations

import os
import threading
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import tiered
from src.tiered_analysis.integration import TieredRunOutcome
from src.tiered_analysis.providers.base import (
    Citation,
    DimensionResult,
    Market,
    SourceKind,
)
from src.tiered_analysis.earnings import EarningsInfo
from src.tiered_analysis.schema import (
    Action,
    Outlook,
    SniperLevels,
    TierReport,
)
from src.tiered_analysis.tiers import TierState


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    db_path = tmp_path / "tiered_api.db"
    os.environ["DATABASE_PATH"] = str(db_path)
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


@pytest.fixture(autouse=True)
def open_clock_gate(monkeypatch):
    """Neutralize the market-hours clock gate (2026-08-08) for the legacy
    endpoint tests — otherwise they pass or fail with the wall clock. The
    gate's own behavior is covered by TestClockGateEndpoint below and
    tests/test_tiered_run_gate.py."""
    from src.tiered_analysis import run_gate

    monkeypatch.setattr(
        run_gate,
        "clock_gate",
        lambda symbol, now=None, override=False: run_gate.ClockGateResult(
            False, "us", "test: gate open"
        ),
    )


@pytest.fixture()
def llm_configured(monkeypatch):
    """The model a run needs, as .env provides it."""
    monkeypatch.setenv("MAIN_LLM", "gemini/test-model")


def _client():
    app = FastAPI()
    app.include_router(tiered.router, prefix="/tiered")
    return TestClient(app)


@pytest.fixture()
def client(isolated_db, llm_configured):
    return _client()


def _outcome(symbol="AAPL"):
    report = TierReport(
        tier=1,
        symbol=symbol,
        market=Market.US,
        outlook=Outlook.NEUTRAL,
        score=56,
        levels=SniperLevels(entry=303.8,
                            stop_loss=290.0, take_profit=325.0),
        narrative="Wait for a pullback.",
        dimensions=[
            DimensionResult(
                dimension="fundamentals", kind=SourceKind.NUMERIC,
                payload={"growth": {"revenue_yoy_pct": 6.4}},
            ),
            DimensionResult(
                dimension="sentiment", kind=SourceKind.TEXTUAL,
                narrative="Sentiment: mixed.",
                citations=[Citation(source_name="Reuters",
                                    url="https://reuters.example/x",
                                    title="Reuters", snippet="q")],
                warnings=["one page blocked"],
            ),
        ],
        warnings=[],
    )
    state = TierState(symbol=symbol, market=Market.US, reports={1: report})
    # The pipeline copies the final report's outlook onto the outcome.
    return TieredRunOutcome(report=report, state=state, outlook=report.outlook)


def _deep_outcome(symbol="AAPL"):
    """Depth-2 outcome with a debate section and a sizing block."""
    base = _outcome(symbol)
    tier2 = TierReport(
        tier=2, symbol=symbol, market=Market.US,
        outlook=Outlook.BULLISH,
        confidence="0.70", levels=base.report.levels,
        narrative="bull case holds",
        debate_detail={"outlook": {"outlook": "bullish", "confidence": 0.7}},
    )
    state = TierState(
        symbol=symbol, market=Market.US,
        reports={1: base.report, 2: tier2},
    )
    sizing = {"enabled": True, "shares": 83,
              "reason_code": None, "refusal_reason": None, "notes": []}
    llm_usage = {"stages": {"tier2_analysis": {"calls": 3, "prompt_tokens": 900,
                                             "completion_tokens": 300}},
                 "total": {"calls": 3, "prompt_tokens": 900,
                           "completion_tokens": 300},
                 "scope": "tiered-package LLM calls only"}
    return TieredRunOutcome(
        report=base.report, state=state,
        depth=2, final_report=tier2, sizing=sizing, llm_usage=llm_usage,
        outlook=Outlook.BULLISH, action=Action.ENTER,
        earnings=EarningsInfo(next_date="2026-07-24", days_until=4),
    )


def _poll_until_done(client, task_id, timeout_s=5.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"/tiered/runs/{task_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] not in ("queued", "running"):
            return body
        time.sleep(0.05)
    raise AssertionError("run never finished")


class TestTieredAnalyzeEndpoint:
    def test_accepts_and_completes_run(self, client):
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _outcome(code)):
            accepted = client.post("/tiered/analyze",
                                   json={"stock_code": "AAPL"})
            assert accepted.status_code == 202
            task_id = accepted.json()["task_id"]
            body = _poll_until_done(client, task_id)

        assert body["status"] == "done"
        result = body["result"]
        assert result["symbol"] == "AAPL"
        assert result["outlook"] == "neutral"
        assert result["score"] == 56
        # Coverage grades are retired (2026-08-19): the serialized run
        # carries no "coverage" key anywhere — degradation shows as
        # warnings/blank fields instead.
        assert "coverage" not in result
        assert result["levels"]["entry"] == 303.8
        assert "signal" not in result
        dims = {d["dimension"]: d for d in result["dimensions"]}
        assert all("coverage" not in d for d in result["dimensions"])
        # is_actionable = numeric kind AND a payload present.
        assert dims["fundamentals"]["is_actionable"] is True
        assert dims["sentiment"]["is_actionable"] is False
        assert dims["fundamentals"]["payload"]["growth"]["revenue_yoy_pct"] == 6.4
        assert dims["sentiment"]["narrative"] == "Sentiment: mixed."
        assert dims["sentiment"]["citations"][0]["url"] == "https://reuters.example/x"

    def test_failed_run_reports_error(self, client):
        def boom(code, **kwargs):
            raise RuntimeError("upstream exploded")

        with patch.object(tiered, "_run_analysis", boom):
            accepted = client.post("/tiered/analyze",
                                   json={"stock_code": "AAPL"})
            body = _poll_until_done(client, accepted.json()["task_id"])

        assert body["status"] == "failed"
        assert "upstream exploded" in body["error"]

    def test_runs_list_is_history_newest_first(self, client):
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _outcome(code)):
            first = client.post("/tiered/analyze",
                                json={"stock_code": "AAPL"}).json()["task_id"]
            _poll_until_done(client, first)
            second = client.post("/tiered/analyze",
                                 json={"stock_code": "NVDA"}).json()["task_id"]
            _poll_until_done(client, second)

        items = client.get("/tiered/runs").json()["items"]
        assert [item["stock_code"] for item in items[:2]] == ["NVDA", "AAPL"]
        assert all(item["status"] == "done" for item in items[:2])
        # summaries stay light — full reports come from the detail route
        assert all("result" not in item for item in items)

    def test_blank_stock_code_rejected(self, client):
        response = client.post("/tiered/analyze", json={"stock_code": "   "})
        assert response.status_code == 422

    def test_unknown_run_is_404(self, client):
        response = client.get("/tiered/runs/nope")
        assert response.status_code == 404
        assert client.get("/tiered/runs/nope/transcript").status_code == 404
        assert client.get("/tiered/runs/nope/transcript/1").status_code == 404

    def test_sizing_defaults_route_is_gone(self, client):
        assert client.get("/tiered/sizing-defaults").status_code == 404

    def test_finished_report_carries_the_dimension_index(self, client):
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _outcome(code)):
            accepted = client.post("/tiered/analyze", json={"stock_code": "AAPL"})
            body = _poll_until_done(client, accepted.json()["task_id"])
        assert body["result"]["dimension_index"] == [
            {"dimension": "fundamentals", "kind": "numeric",
             "is_actionable": True, "warnings": []},
            {"dimension": "sentiment", "kind": "textual",
             "is_actionable": False, "warnings": ["one page blocked"]},
        ]


def _finish(client, stock_code, **overrides):
    """Start and finish one run through the endpoint; returns its task id.
    The fake runner reports the depth and hold it was asked for, as the
    real one does, so the row's tier and hold columns are meaningful."""
    from dataclasses import replace

    def fake_run(code, **kwargs):
        return replace(_outcome(code), depth=kwargs.get("depth", 1),
                       hold_weeks=kwargs.get("hold_weeks", 2))

    with patch.object(tiered, "_run_analysis", fake_run):
        task_id = client.post("/tiered/analyze", json={
            "stock_code": stock_code, **overrides,
        }).json()["task_id"]
        _poll_until_done(client, task_id)
    return task_id


class TestRunListEndpoint:
    """GET /runs: one page at a time, filtered in SQL (2026-09-21)."""

    def test_page_envelope_and_row_shape(self, client):
        _finish(client, "AAPL", depth=2, hold_weeks=3,
                sizing={"capital": 50000, "risk_fraction": 0.02, "reward_risk": 3})
        body = client.get("/tiered/runs").json()
        assert set(body) == {"items", "page", "page_size", "total", "page_count"}
        assert (body["page"], body["page_size"], body["total"], body["page_count"]) == (1, 10, 1, 1)
        row = body["items"][0]
        assert set(row) == {
            "task_id", "stock_code", "status", "error", "created_at",
            "updated_at", "queue_ahead", "tier", "capital", "risk_fraction",
            "reward_risk", "hold_weeks", "outlook", "shares",
        }
        assert row["stock_code"] == "AAPL" and row["status"] == "done"
        assert (row["tier"], row["hold_weeks"]) == (2, 3)
        assert (row["capital"], row["risk_fraction"], row["reward_risk"]) == (50000, 0.02, 3.0)
        assert row["outlook"] == "neutral"

    def test_filters_and_paging_reach_the_database(self, client):
        _finish(client, "AAPL")
        _finish(client, "NVDA", depth=2)
        _finish(client, "MSFT")
        page = client.get("/tiered/runs", params={"page": 2, "page_size": 2}).json()
        assert [r["stock_code"] for r in page["items"]] == ["AAPL"]
        assert (page["total"], page["page_count"]) == (3, 2)
        by_ticker = client.get("/tiered/runs", params={"ticker": ["nvda", "msft"]}).json()
        assert sorted(r["stock_code"] for r in by_ticker["items"]) == ["MSFT", "NVDA"]
        assert client.get("/tiered/runs", params={"tier": 2}).json()["total"] == 1
        assert client.get("/tiered/runs", params={"outlook": "neutral"}).json()["total"] == 3
        assert client.get("/tiered/runs", params={"outlook": "none"}).json()["total"] == 0
        assert client.get("/tiered/runs", params={"status": "failed"}).json()["total"] == 0
        assert client.get("/tiered/runs", params={
            "capital_min": 100000, "risk_max": 0.01,
        }).json()["total"] == 3
        assert client.get("/tiered/runs", params={
            "created_after": "2000-01-01T00:00:00Z",
            "created_before": "2000-01-02T00:00:00+08:00",
        }).json()["total"] == 0

    def test_bad_filter_values_are_422(self, client):
        assert client.get("/tiered/runs", params={"status": "sleeping"}).status_code == 422
        assert client.get("/tiered/runs", params={"outlook": "sideways"}).status_code == 422
        assert client.get("/tiered/runs", params={"page": 0}).status_code == 422
        assert client.get("/tiered/runs", params={"page_size": 201}).status_code == 422
        assert client.get("/tiered/runs", params={"risk_min": 1.5}).status_code == 422
        assert client.get("/tiered/runs", params={"created_after": "yesterday"}).status_code == 422

    def test_tickers_route(self, client):
        assert client.get("/tiered/runs/tickers").json() == {"items": []}
        _finish(client, "NVDA")
        _finish(client, "AAPL")
        _finish(client, "NVDA")
        assert client.get("/tiered/runs/tickers").json() == {"items": ["AAPL", "NVDA"]}


class TestRunDetailSections:
    """GET /runs/{task_id}?section=…: the report by section (2026-09-21)."""

    def test_whole_report_by_default_and_sections_named(self, client):
        task_id = _finish(client, "AAPL")
        body = client.get(f"/tiered/runs/{task_id}").json()
        assert body["sections"] == ["core", "dimensions", "debate", "plan"]
        assert body["result"]["dimensions"]
        assert "sizing" in body["result"]

    def test_core_only(self, client):
        task_id = _finish(client, "AAPL")
        body = client.get(f"/tiered/runs/{task_id}", params={"section": "core"}).json()
        assert body["sections"] == ["core"]
        result = body["result"]
        assert result["symbol"] == "AAPL" and result["outlook"] == "neutral"
        assert result["levels"]["entry"] == 303.8
        for heavy in ("dimensions", "levels_detail", "sizing", "plan_warnings"):
            assert heavy not in result

    def test_named_sections_and_one_dimension(self, client):
        task_id = _finish(client, "AAPL")
        body = client.get(f"/tiered/runs/{task_id}", params={
            "section": ["dimensions", "plan"], "dimension": "sentiment",
        }).json()
        assert body["sections"] == ["core", "dimensions", "plan"]
        assert [d["dimension"] for d in body["result"]["dimensions"]] == ["sentiment"]
        assert "sizing" in body["result"]

    def test_unknown_section_is_422(self, client):
        task_id = _finish(client, "AAPL")
        response = client.get(f"/tiered/runs/{task_id}", params={"section": "gossip"})
        assert response.status_code == 422


class TestDeleteEndpoint:
    """DELETE /runs/{task_id} (2026-09-21): a queued run is cancelled, a
    finished one removed, a running one refused."""

    def test_finished_run_goes_with_its_transcript(self, client):
        task_id = _finish(client, "AAPL")
        other = _finish(client, "NVDA")
        from tests.test_tiered_history import _record_call
        _record_call(task_id, 1)

        response = client.delete(f"/tiered/runs/{task_id}")

        assert response.status_code == 200
        assert response.json() == {"task_id": task_id, "stock_code": "AAPL",
                                   "status": "done"}
        assert client.get(f"/tiered/runs/{task_id}").status_code == 404
        assert client.get(f"/tiered/runs/{task_id}/transcript").status_code == 404
        assert client.delete(f"/tiered/runs/{task_id}").status_code == 404
        assert client.get(f"/tiered/runs/{other}").status_code == 200
        assert client.get("/tiered/runs/tickers").json() == {"items": ["NVDA"]}

    def test_queued_run_is_cancelled_and_a_running_one_refused(self, client, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "1")
        runner, release = TestRunQueueEndpoint._gated_runner()
        with patch.object(tiered, "_run_analysis", runner):
            first = client.post("/tiered/analyze", json={"stock_code": "AAPL"}).json()
            second = client.post("/tiered/analyze", json={"stock_code": "MSFT"}).json()
            assert second["status"] == "queued"

            refused = client.delete(f"/tiered/runs/{first['task_id']}")
            assert refused.status_code == 409
            assert refused.json()["detail"] == {
                "code": "run_in_progress", "task_id": first["task_id"],
            }
            cancelled = client.delete(f"/tiered/runs/{second['task_id']}")
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "queued"

            release.set()
            assert _poll_until_done(client, first["task_id"])["status"] == "done"
        # The cancelled run never ran and is not in the history.
        items = client.get("/tiered/runs").json()["items"]
        assert [item["task_id"] for item in items] == [first["task_id"]]


class TestStatusEndpoint:
    def test_status_document(self, client, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "3")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("SUB_LLM", raising=False)
        _finish(client, "AAPL")

        response = client.get("/tiered/status")

        assert response.status_code == 200
        body = response.json()
        assert body["llm"] == {"main_model": "gemini/test-model",
                               "sub_model": "gemini/test-model", "api_key_set": False}
        assert body["runs"] == {"max_concurrent": 3, "running": 0, "queued": 0}
        assert body["defaults"]["capital"] == 100_000.0
        assert set(body["data_sources"]) == {"finnhub", "alphavantage", "fred", "sec_edgar"}
        assert [m["market"] for m in body["markets"]] == ["cn", "hk", "us", "jp", "kr", "tw"]
        assert set(body["markets"][0]) == {
            "market", "timezone", "local_time", "session_open", "session_close",
            "runs_blocked", "runs_allowed_from",
        }
        assert body["server_time"].endswith("+00:00")
        assert body["transcript_retention_days"] == 14


class TestDebateItemsEndpoint:
    """GET /runs/{task_id}/debate/items (2026-09-21): the vote items,
    paged, while the debate section carries only the overview."""

    ITEMS = [
        {"id": "T1", "dimension": "technicals", "final_status": "counted"},
        {"id": "T2", "dimension": "technicals", "final_status": "excluded"},
        {"id": "F1", "dimension": "fundamentals", "final_status": "counted"},
    ]

    def _deep_run(self, client):
        from dataclasses import replace

        def fake_run(code, **kwargs):
            outcome = _deep_outcome(code)
            tier2 = replace(outcome.final_report, debate_detail={
                "format": 11, "items": self.ITEMS,
                "outlook": {"outlook": "bullish"}, "warnings": [],
            })
            state = TierState(symbol=code, market=Market.US,
                              reports={1: outcome.report, 2: tier2})
            return replace(outcome, state=state, final_report=tier2)

        with patch.object(tiered, "_run_analysis", fake_run):
            task_id = client.post("/tiered/analyze", json={
                "stock_code": "AAPL", "depth": 2,
            }).json()["task_id"]
            _poll_until_done(client, task_id)
        return task_id

    def test_debate_section_is_the_overview_and_items_are_paged(self, client):
        task_id = self._deep_run(client)
        detail = client.get(f"/tiered/runs/{task_id}",
                            params={"section": "debate"}).json()
        assert detail["result"]["tier2"]["debate_detail"] == {
            "format": 11, "outlook": {"outlook": "bullish"}, "warnings": [],
            "item_count": 3,
        }
        # Every answer carries the light per-report index.
        assert [d["dimension"] for d in detail["result"]["dimension_index"]] == [
            "fundamentals", "sentiment"]

        page = client.get(f"/tiered/runs/{task_id}/debate/items",
                          params={"status": "counted", "page_size": 1, "page": 2})
        assert page.status_code == 200
        assert page.json() == {
            "items": [self.ITEMS[2]], "page": 2, "page_size": 1,
            "total": 2, "page_count": 2,
        }
        by_dimension = client.get(f"/tiered/runs/{task_id}/debate/items",
                                  params={"dimension": ["technicals"]}).json()
        assert [i["id"] for i in by_dimension["items"]] == ["T1", "T2"]

    def test_tier1_run_has_an_empty_page_and_unknown_run_404(self, client):
        task_id = _finish(client, "AAPL")
        page = client.get(f"/tiered/runs/{task_id}/debate/items").json()
        assert page["items"] == [] and page["total"] == 0
        assert client.get("/tiered/runs/nope/debate/items").status_code == 404
        bad = client.get(f"/tiered/runs/{task_id}/debate/items",
                         params={"status": "maybe"})
        assert bad.status_code == 422


class TestTranscriptEndpoints:
    """The transcript as an index plus one call at a time (2026-09-21)."""

    @staticmethod
    def _record(task_id, seq, prompt, reply):
        from src.storage import DatabaseManager, TieredRunTranscriptRecord

        with DatabaseManager.get_instance().get_session() as session:
            session.add(TieredRunTranscriptRecord(
                task_id=task_id, seq=seq, stage="tier1_analysis",
                model="gemini/flash", temperature=0.0, duration_ms=120,
                prompt_tokens=10, completion_tokens=5, structured="schema",
                prompt=prompt, reply=reply,
            ))
            session.commit()

    def test_index_then_one_call(self, client):
        task_id = _finish(client, "AAPL")
        self._record(task_id, 1, "ask one", "answer one")
        self._record(task_id, 2, "ask two", None)
        index = client.get(f"/tiered/runs/{task_id}/transcript").json()["items"]
        assert [row["seq"] for row in index] == [1, 2]
        assert set(index[0]) == {
            "seq", "created_at", "stage", "model", "temperature", "duration_ms",
            "prompt_tokens", "completion_tokens", "structured", "error",
            "prompt_chars", "reply_chars",
        }
        assert (index[0]["prompt_chars"], index[0]["reply_chars"]) == (7, 10)
        assert (index[1]["prompt_chars"], index[1]["reply_chars"]) == (7, 0)

        call = client.get(f"/tiered/runs/{task_id}/transcript/2").json()
        assert call["prompt"] == "ask two" and call["reply"] is None
        assert call["seq"] == 2 and call["model"] == "gemini/flash"
        assert "prompt_chars" not in call
        assert client.get(f"/tiered/runs/{task_id}/transcript/3").status_code == 404

    def test_run_without_calls_has_an_empty_index(self, client):
        task_id = _finish(client, "AAPL")
        assert client.get(f"/tiered/runs/{task_id}/transcript").json() == {"items": []}


class TestLlmConfiguration:
    """A run needs MAIN_LLM in the environment; without it the start
    is refused up front instead of failing minutes later."""

    def test_run_without_a_model_is_refused_before_starting(self, isolated_db, monkeypatch):
        monkeypatch.delenv("MAIN_LLM", raising=False)
        client = _client()
        response = client.post("/tiered/analyze", json={"stock_code": "AAPL"})
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "llm_not_configured"
        assert client.get("/tiered/runs").json()["items"] == []
        # reads need no model
        assert client.get("/tiered/runs/tickers").json() == {"items": []}


class TestTieredDepthAndSizingApi:
    """v2 slice 6: depth parameter, sizing override, new response sections."""

    def test_depth_out_of_range_rejected(self, client):
        # Tier 3 is retired: depth 3 is an error, not a clamp (user
        # decision, 2026-07-20).
        for depth in (0, 3, 4):
            response = client.post(
                "/tiered/analyze", json={"stock_code": "AAPL", "depth": depth})
            assert response.status_code == 422

    def test_invalid_sizing_override_rejected(self, client):
        response = client.post("/tiered/analyze", json={
            "stock_code": "AAPL",
            "sizing": {"capital": -5, "risk_fraction": 0.01},
        })
        assert response.status_code == 422
        response = client.post("/tiered/analyze", json={
            "stock_code": "AAPL",
            "sizing": {"risk_fraction": 1.5},
        })
        assert response.status_code == 422

    def test_depth_and_sizing_reach_the_runner(self, client):
        captured = {}

        def fake_run(code, depth=1, sizing_overrides=None, hold_weeks=2,
                     **kwargs):
            captured["code"] = code
            captured["depth"] = depth
            captured["sizing_overrides"] = sizing_overrides
            return _deep_outcome(code)

        with patch.object(tiered, "_run_analysis", fake_run):
            accepted = client.post("/tiered/analyze", json={
                "stock_code": "AAPL",
                "depth": 2,
                "sizing": {"capital": 50000, "risk_fraction": 0.02},
            })
            assert accepted.status_code == 202
            assert accepted.json()["depth"] == 2
            _poll_until_done(client, accepted.json()["task_id"])

        assert captured["depth"] == 2
        assert captured["sizing_overrides"] == {"capital": 50000.0,
                                                "risk_fraction": 0.02}

    def test_deep_run_response_contract(self, client):
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _deep_outcome(code)):
            accepted = client.post("/tiered/analyze",
                                   json={"stock_code": "AAPL", "depth": 2})
            body = _poll_until_done(client, accepted.json()["task_id"])

        result = body["result"]
        assert result["depth"] == 2
        # tier-1 fields keep their v1 shape for the existing UI; the
        # one outlook on the report is the deepest tier's
        assert "direction" not in result
        assert result["tier"] == 1
        # the deepest tier is what the user should act on
        assert result["final"]["tier"] == 2
        assert result["final"]["outlook"] == "bullish"
        assert result["final"]["action"] == "enter"
        # No coverage grades anywhere in the serialized run (2026-08-19).
        assert "coverage" not in result["final"]
        assert "coverage" not in result["tier2"]
        assert result["tier2"]["debate_detail"]["outlook"]["outlook"] == "bullish"
        assert result["sizing"]["shares"] == 83
        assert result["llm_usage"]["total"]["calls"] == 3
        # outlook redesign additions
        assert result["outlook"] == "bullish"
        assert result["action"] == "enter"
        assert result["earnings"]["next_date"] == "2026-07-24"
        assert result["earnings"]["is_near"] is True
        assert "risk_card" not in result

    def test_v1_shaped_outcome_serializes_with_defaults(self, client):
        # An outcome without the new fields (depth-1 run) must still
        # produce the additive keys, as explicit "not run" values.
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _outcome(code)):
            accepted = client.post("/tiered/analyze",
                                   json={"stock_code": "AAPL"})
            body = _poll_until_done(client, accepted.json()["task_id"])

        result = body["result"]
        assert result["depth"] == 1
        assert result["final"]["tier"] == 1
        assert result["tier2"] is None
        assert result["sizing"] is None
        assert result["llm_usage"] is None
        # The one outlook on the report is the final report's own.
        assert result["outlook"] == "neutral"
        assert result["final"]["outlook"] == "neutral"
        assert result["action"] == "unknown"
        assert result["earnings"] is None


class TestClockGateEndpoint:
    """The market-hours clock gate (owner decisions 2026-08-08)."""

    def _gate(self, blocked):
        from src.tiered_analysis import run_gate

        def fake(symbol, now=None, override=False):
            return run_gate.ClockGateResult(
                blocked and not override, "us", "test"
            )

        return fake

    def test_blocked_market_returns_409_with_code(self, client, monkeypatch):
        from src.tiered_analysis import run_gate

        monkeypatch.setattr(run_gate, "clock_gate", self._gate(blocked=True))
        response = client.post("/tiered/analyze", json={"stock_code": "AAPL"})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "market_open"
        assert detail["market"] == "us"

    def test_blocked_409_carries_session_bounds_as_iso(
        self, client, monkeypatch
    ):
        """2026-08-11: the popup words the market's hours (market time +
        the user's time), so the 409 body ships the session bounds as
        ISO datetimes with the market's own UTC offset embedded."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from src.tiered_analysis import run_gate

        tz = ZoneInfo("America/New_York")

        def fake(symbol, now=None, override=False):
            return run_gate.ClockGateResult(
                not override, "us", "test",
                session_open=datetime(2026, 8, 11, 9, 30, tzinfo=tz),
                session_close=datetime(2026, 8, 11, 16, 0, tzinfo=tz),
            )

        monkeypatch.setattr(run_gate, "clock_gate", fake)
        response = client.post("/tiered/analyze", json={"stock_code": "AAPL"})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["session_open"] == "2026-08-11T09:30:00-04:00"
        assert detail["session_close"] == "2026-08-11T16:00:00-04:00"

    def test_blocked_409_survives_the_global_error_handlers(
        self, isolated_db, llm_configured, monkeypatch
    ):
        """Regression (2026-08-11): the server registers add_error_handlers,
        which used to flatten any non-ErrorResponse dict detail into a
        Python-repr string — the web app then couldn't see detail.code and
        showed raw text instead of the run-anyway popup. Structured dict
        details must reach the client intact through the real handlers."""
        from api.middlewares.error_handler import add_error_handlers
        from src.tiered_analysis import run_gate

        app = FastAPI()
        add_error_handlers(app)
        app.include_router(tiered.router, prefix="/tiered")
        handled_client = TestClient(app)

        monkeypatch.setattr(run_gate, "clock_gate", self._gate(blocked=True))
        response = handled_client.post(
            "/tiered/analyze", json={"stock_code": "AAPL"}
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail == {"code": "market_open", "market": "us"}

    def test_run_anyway_overrides_the_gate(self, client, monkeypatch):
        from src.tiered_analysis import run_gate

        monkeypatch.setattr(run_gate, "clock_gate", self._gate(blocked=True))
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _outcome(code)):
            response = client.post(
                "/tiered/analyze",
                json={"stock_code": "AAPL", "run_anyway": True},
            )
            assert response.status_code == 202
            _poll_until_done(client, response.json()["task_id"])

    def test_hold_weeks_reaches_the_runner_and_inputs(self, client):
        seen = {}

        def runner(code, **kwargs):
            seen.update(kwargs)
            return _outcome(code)

        with patch.object(tiered, "_run_analysis", runner):
            accepted = client.post(
                "/tiered/analyze",
                json={"stock_code": "AAPL", "hold_weeks": 3},
            )
            assert accepted.status_code == 202
            _poll_until_done(client, accepted.json()["task_id"])
        assert seen["hold_weeks"] == 3

    def test_hold_weeks_out_of_range_is_rejected(self, client):
        response = client.post(
            "/tiered/analyze", json={"stock_code": "AAPL", "hold_weeks": 5}
        )
        assert response.status_code == 422


class TestRunQueueEndpoint:
    """The global run queue (2026-09-15): a run past the concurrency cap
    waits as ``queued`` and starts by itself; an exact duplicate of an
    unfinished run is refused with a 409."""

    @staticmethod
    def _gated_runner():
        release = threading.Event()

        def runner(code, **kwargs):
            release.wait(timeout=5)
            return _outcome(code)

        return runner, release

    def test_second_run_past_the_cap_waits_then_runs(self, client, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "1")
        runner, release = self._gated_runner()
        with patch.object(tiered, "_run_analysis", runner):
            first = client.post("/tiered/analyze", json={"stock_code": "AAPL"}).json()
            second = client.post("/tiered/analyze", json={"stock_code": "MSFT"}).json()
            assert first["status"] == "running"
            assert second["status"] == "queued"

            items = {r["task_id"]: r for r in client.get("/tiered/runs").json()["items"]}
            assert items[first["task_id"]]["status"] == "running"
            assert items[second["task_id"]]["status"] == "queued"
            assert items[second["task_id"]]["queue_ahead"] == 0
            # queued rows already show the inputs they were made with
            assert items[second["task_id"]]["tier"] == 1

            release.set()
            assert _poll_until_done(client, first["task_id"])["status"] == "done"
            assert _poll_until_done(client, second["task_id"])["status"] == "done"

    def test_exact_duplicate_of_an_unfinished_run_is_409(self, client, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_RUNS", "1")
        runner, release = self._gated_runner()
        body = {"stock_code": "AAPL", "depth": 2, "hold_weeks": 3,
                "sizing": {"capital": 50000, "risk_fraction": 0.02, "reward_risk": 2}}
        with patch.object(tiered, "_run_analysis", runner):
            accepted = client.post("/tiered/analyze", json=body)
            assert accepted.status_code == 202
            task_id = accepted.json()["task_id"]

            again = client.post("/tiered/analyze", json={**body, "stock_code": "aapl"})
            assert again.status_code == 409
            assert again.json()["detail"] == {
                "code": "duplicate_run", "task_id": task_id, "status": "running",
            }
            # one input changed: a different run, so it joins the line
            other = client.post("/tiered/analyze", json={**body, "hold_weeks": 4})
            assert other.status_code == 202
            assert other.json()["status"] == "queued"
            # and the queued one is a duplicate too
            assert client.post("/tiered/analyze",
                               json={**body, "hold_weeks": 4}).status_code == 409

            release.set()
            _poll_until_done(client, task_id)
            _poll_until_done(client, other.json()["task_id"])

        # finished runs never block a re-run
        with patch.object(tiered, "_run_analysis",
                          lambda code, **kwargs: _outcome(code)):
            assert client.post("/tiered/analyze", json=body).status_code == 202
