# -*- coding: utf-8 -*-
"""Offline tests for the chat bot's tool menu (src/chat/tools.py):
the schemas the model reads, argument parsing, and each tool against
the run history."""
from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

import pytest

from src.chat import tools
from src.chat.tools import ToolCatalog, clean_schema
from src.tiered_analysis import history


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "chat_tools.db")
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
    from src.tiered_analysis import run_gate

    monkeypatch.setattr(
        run_gate, "market_open_check",
        lambda ticker, now=None, run_anyway=False: run_gate.MarketOpenCheck(False, "us", "test: open"),
    )


REPORT = {
    "ticker": "AAPL", "outlook": "bullish", "score": 7.5,
    "levels": {"entry": 100.0, "stop_loss": 95.0, "target": 110.0},
    "data_reports": [
        {"name": "technicals", "kind": "numeric", "counted": True,
         "payload": {"rsi_14": 55.0}, "warnings": []},
        {"name": "company_news", "kind": "textual", "counted": False,
         "payload": None, "warnings": ["no key"]},
    ],
    "deep_analysis": {"outlook": "bullish", "detail": {
        "outlook": {"outlook": "bullish"},
        "items": [
            {"data_report": "technicals", "final_status": "counted", "claim": "trend up"},
            {"data_report": "technicals", "final_status": "excluded", "claim": "noise"},
        ],
    }},
    "sizing": {"shares": 10, "inputs": {"capital": 1000.0, "risk_pct": 1.0, "reward_ratio": 2.0}},
    "tier": 2, "max_hold_weeks": 2,
}


def _done_run(run_id="run1", ticker="AAPL", tier=2):
    history.create_run(run_id, ticker, inputs={"tier": tier, "max_hold_weeks": 2}, status="queued")
    history.mark_running(run_id)
    history.mark_done(run_id, REPORT)
    return run_id


def _call(name, **args):
    tool = ToolCatalog().get(name)
    params, problem = tool.parse(json.dumps(args))
    assert problem is None, problem
    return tool, params


class TestSchemas:
    def test_every_tool_has_a_provider_safe_schema(self):
        specs = ToolCatalog().specs()
        assert len(specs) == 10
        text = json.dumps(specs)
        assert '"title"' not in text
        assert "anyOf" not in text
        assert "exclusiveMinimum" not in text
        assert '"default": null' not in text
        names = {s["function"]["name"] for s in specs}
        assert names == {
            "get_server_status", "list_runs", "list_tickers", "get_run",
            "get_data_report", "list_vote_items", "get_transcript",
            "get_transcript_call", "start_run", "delete_run",
        }

    def test_clean_schema_merges_optional_and_keeps_real_defaults(self):
        cleaned = clean_schema({
            "title": "X",
            "properties": {
                "capital": {"anyOf": [{"type": "number"}, {"type": "null"}],
                            "default": None, "title": "Capital", "description": "d"},
                "page": {"type": "integer", "default": 1, "exclusiveMinimum": 0},
            },
        })
        assert cleaned == {"properties": {
            "capital": {"type": "number", "description": "d"},
            "page": {"type": "integer", "default": 1},
        }}

    def test_only_the_gated_tools_confirm(self):
        catalog = ToolCatalog()
        gated = {name for name in catalog.names() if catalog.get(name).needs_confirmation}
        assert gated == {"get_data_report", "get_transcript_call", "start_run", "delete_run"}


class TestParse:
    def test_bad_json_and_bad_values_become_error_results(self):
        tool = ToolCatalog().get("start_run")
        _, problem = tool.parse("{not json")
        assert problem["error"] == "invalid_arguments"
        _, problem = tool.parse(json.dumps({"ticker": "AAPL", "tier": 3}))
        assert problem["error"] == "invalid_arguments"
        assert "tier" in problem["message"]
        _, problem = tool.parse("{}")
        assert "ticker" in problem["message"]

    def test_inputs_fill_in_every_default_for_the_page(self, isolated_db, monkeypatch):
        # The page shows a call's inputs from here, so the user sees the
        # defaults the model left out, not only what it sent (2026-09-24).
        tool, params = _call("get_run", run_id="run1")
        assert tool.inputs(params) == {"run_id": "run1", "sections": []}
        tool, params = _call("list_runs", ticker=["AAPL"])
        assert tool.inputs(params)["page_size"] == 10
        assert tool.inputs(params)["status"] == []
        # start_run goes further: the server's sizing defaults too, under
        # the web form's names.
        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        tool, params = _call("start_run", ticker="AAPL")
        # ... in the form's order, with risk as the percent it shows, and
        # the turn's language (the app's default outside a chat turn).
        assert list(tool.inputs(params).items()) == [
            ("ticker", "AAPL"), ("capital", 100000.0), ("risk_pct", 1.0),
            ("reward_ratio", 2.0), ("max_hold_weeks", 2), ("tier", 1),
            ("language", "en"), ("run_anyway", False),
        ]

    def test_defaults_fill_what_the_model_leaves_out(self):
        _, params = _call("list_runs")
        assert (params.page, params.page_size, params.ticker) == (1, 10, [])


class TestReads:
    def test_list_runs_filters_and_pages(self, isolated_db):
        _done_run("a", "AAPL")
        _done_run("b", "MSFT")
        tool, params = _call("list_runs", ticker=["msft"])
        page = tool.run(params)
        assert [r["run_id"] for r in page["items"]] == ["b"]
        assert page["total"] == 1
        tool, params = _call("list_runs", created_after="bad date")
        assert tool.run(params)["error"] == "invalid_arguments"

    def test_list_tickers_and_status(self, isolated_db, monkeypatch):
        monkeypatch.delenv("MAIN_LLM", raising=False)
        _done_run("a", "AAPL")
        tool, params = _call("list_tickers")
        assert tool.run(params) == {"items": ["AAPL"]}
        tool, params = _call("get_server_status")
        status = tool.run(params)
        assert status["runs"]["max_concurrent"] >= 1
        assert "api_key_set" in status["llm"]

    def test_get_run_core_plus_named_sections(self, isolated_db):
        _done_run("a")
        tool, params = _call("get_run", run_id="a")
        run = tool.run(params)
        assert run["sections"] == ["core"]
        assert "data_reports" not in run["result"]
        assert [d["name"] for d in run["result"]["data_report_index"]] == ["technicals", "company_news"]
        assert "detail" not in run["result"]["deep_analysis"]

        tool, params = _call("get_run", run_id="a", sections=["deep_analysis"])
        overview = tool.run(params)["result"]["deep_analysis"]["detail"]
        assert overview["item_count"] == 2
        assert "items" not in overview

        tool, params = _call("get_run", run_id="zzz")
        assert tool.run(params)["error"] == "not_found"

    def test_data_report_report_is_priced_then_read(self, isolated_db):
        _done_run("a")
        tool, params = _call("get_data_report", run_id="a", data_report="technicals")
        facts = tool.confirm(params)
        assert facts["chars"] > 0
        assert facts["tokens_estimate"] == -(-facts["chars"] // 4)
        assert tool.run(params)["report"]["payload"] == {"rsi_14": 55.0}

        tool, params = _call("get_data_report", run_id="a", data_report="fundamentals")
        assert tool.confirm(params)["error"] == "not_found"
        tool, params = _call("get_data_report", run_id="zzz", data_report="technicals")
        assert tool.confirm(params)["error"] == "not_found"

    def test_deep_analysis_items_page_and_filter(self, isolated_db):
        _done_run("a")
        tool, params = _call("list_vote_items", run_id="a", status=["counted"])
        page = tool.run(params)
        assert [i["claim"] for i in page["items"]] == ["trend up"]
        tool, params = _call("list_vote_items", run_id="zzz")
        assert tool.run(params)["error"] == "not_found"

    def test_transcript_index_then_priced_call(self, isolated_db):
        _done_run("a")
        from src.storage import TieredRunTranscriptRecord
        with isolated_db.get_session() as session:
            session.add(TieredRunTranscriptRecord(
                run_id="a", call_number=1, stage="preliminary_analysis", llm="m",
                input="p" * 400, output="r" * 100,
            ))
            session.commit()
        tool, params = _call("get_transcript", run_id="a")
        index = tool.run(params)
        assert index["items"][0]["input_chars"] == 400
        assert "input" not in index["items"][0]

        tool, params = _call("get_transcript_call", run_id="a", call_number=1)
        assert tool.confirm(params) == {"chars": 500, "tokens_estimate": 125}
        assert tool.run(params)["output"] == "r" * 100
        tool, params = _call("get_transcript_call", run_id="a", call_number=9)
        assert tool.confirm(params)["error"] == "not_found"


class TestWrites:
    def test_start_run_shows_its_inputs_then_queues_through_the_route_path(self, isolated_db, monkeypatch):
        from src.tiered_analysis import run_service

        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        tool, params = _call("start_run", ticker="AAPL", tier=2, capital=5000, risk_pct=0.5)
        facts = tool.confirm(params)
        assert facts == {"ticker": "AAPL", "capital": 5000.0, "risk_pct": 0.5,
                         "reward_ratio": 2.0, "max_hold_weeks": 2, "tier": 2,
                         "language": "en", "run_anyway": False}

        started = {}

        def fake_run(code, **kwargs):
            started["code"] = code
            raise RuntimeError("stop here")

        with patch.object(run_service, "_run_analysis", fake_run):
            accepted = tool.run(params)
            assert accepted["ticker"] == "AAPL" and accepted["tier"] == 2
            assert accepted["status"] in ("running", "queued")
            deadline = time.time() + 5
            while time.time() < deadline and history.get_run_summary(accepted["run_id"])["status"] != "failed":
                time.sleep(0.02)
        assert started["code"] == "AAPL"

    def test_start_run_refusals_are_results(self, isolated_db, monkeypatch):
        monkeypatch.delenv("MAIN_LLM", raising=False)
        tool, params = _call("start_run", ticker="AAPL")
        assert tool.run(params)["error"] == "llm_not_configured"

        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        # The language is one of the inputs a duplicate must share.
        history.create_run("dup", "AAPL", inputs={
            "tier": 1, "capital": 100000.0, "risk_pct": 1.0,
            "reward_ratio": 2.0, "max_hold_weeks": 2, "language": "en",
        }, status="queued")
        refused = tool.run(params)
        assert refused["error"] == "duplicate_run"
        assert refused["run_id"] == "dup"

    def test_start_run_market_open_refusal(self, isolated_db, monkeypatch):
        from src.tiered_analysis import run_gate

        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        monkeypatch.setattr(
            run_gate, "market_open_check",
            lambda ticker, now=None, run_anyway=False: run_gate.MarketOpenCheck(
                not run_anyway, "us", "test: open"),
        )
        tool, params = _call("start_run", ticker="AAPL")
        assert tool.run(params)["error"] == "market_open"

    def test_delete_run_names_the_run_then_removes_it(self, isolated_db):
        history.create_run("q", "AAPL", inputs={"tier": 1}, status="queued")
        tool, params = _call("delete_run", run_id="q")
        assert tool.confirm(params)["run"]["status"] == "queued"
        assert tool.run(params) == {"deleted": True, "run_id": "q", "ticker": "AAPL", "status": "queued"}
        assert tool.confirm(params)["error"] == "not_found"
        assert tool.run(params)["error"] == "not_found"

    def test_delete_run_refuses_a_running_run(self, isolated_db):
        history.create_run("r", "AAPL", inputs={"tier": 1}, status="queued")
        history.mark_running("r")
        tool, params = _call("delete_run", run_id="r")
        assert tool.confirm(params)["error"] == "run_in_progress"
        assert tool.run(params)["error"] == "run_in_progress"


def test_token_estimate_rounds_up():
    assert tools.token_estimate(0) == 0
    assert tools.token_estimate(1) == 1
    assert tools.token_estimate(8) == 2
