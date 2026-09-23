# -*- coding: utf-8 -*-
"""Offline tests for the chatbot's tool menu (src/chatbot/tools.py):
the schemas the model reads, argument parsing, and each tool against
the run history."""
from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

import pytest

from src.chatbot import tools
from src.chatbot.tools import ToolCatalog, clean_schema
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
        run_gate, "clock_gate",
        lambda symbol, now=None, override=False: run_gate.ClockGateResult(False, "us", "test: open"),
    )


REPORT = {
    "symbol": "AAPL", "outlook": "bullish", "score": 7.5,
    "levels": {"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0},
    "dimensions": [
        {"dimension": "technicals", "kind": "numeric", "is_actionable": True,
         "payload": {"rsi_14": 55.0}, "warnings": []},
        {"dimension": "company_news", "kind": "textual", "is_actionable": False,
         "payload": None, "warnings": ["no key"]},
    ],
    "tier2": {"outlook": "bullish", "debate_detail": {
        "outlook": {"outlook": "bullish"},
        "items": [
            {"dimension": "technicals", "final_status": "counted", "claim": "trend up"},
            {"dimension": "technicals", "final_status": "excluded", "claim": "noise"},
        ],
    }},
    "sizing": {"shares": 10, "inputs": {"capital": 1000.0, "risk_fraction": 0.01, "reward_risk": 2.0}},
    "depth": 2, "hold_weeks": 2,
}


def _done_run(task_id="run1", stock_code="AAPL", tier=2):
    history.create_run(task_id, stock_code, inputs={"tier": tier, "hold_weeks": 2}, status="queued")
    history.mark_running(task_id)
    history.mark_done(task_id, REPORT)
    return task_id


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
            "get_dimension_report", "list_debate_items", "get_transcript",
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
        assert gated == {"get_dimension_report", "get_transcript_call", "start_run", "delete_run"}


class TestParse:
    def test_bad_json_and_bad_values_become_error_results(self):
        tool = ToolCatalog().get("start_run")
        _, problem = tool.parse("{not json")
        assert problem["error"] == "invalid_arguments"
        _, problem = tool.parse(json.dumps({"stock_code": "AAPL", "depth": 3}))
        assert problem["error"] == "invalid_arguments"
        assert "depth" in problem["message"]
        _, problem = tool.parse("{}")
        assert "stock_code" in problem["message"]

    def test_defaults_fill_what_the_model_leaves_out(self):
        _, params = _call("list_runs")
        assert (params.page, params.page_size, params.ticker) == (1, 10, [])


class TestReads:
    def test_list_runs_filters_and_pages(self, isolated_db):
        _done_run("a", "AAPL")
        _done_run("b", "MSFT")
        tool, params = _call("list_runs", ticker=["msft"])
        page = tool.run(params)
        assert [r["task_id"] for r in page["items"]] == ["b"]
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
        tool, params = _call("get_run", task_id="a")
        run = tool.run(params)
        assert run["sections"] == ["core"]
        assert "dimensions" not in run["result"]
        assert [d["dimension"] for d in run["result"]["dimension_index"]] == ["technicals", "company_news"]
        assert "debate_detail" not in run["result"]["tier2"]

        tool, params = _call("get_run", task_id="a", sections=["debate"])
        overview = tool.run(params)["result"]["tier2"]["debate_detail"]
        assert overview["item_count"] == 2
        assert "items" not in overview

        tool, params = _call("get_run", task_id="zzz")
        assert tool.run(params)["error"] == "not_found"

    def test_dimension_report_is_priced_then_read(self, isolated_db):
        _done_run("a")
        tool, params = _call("get_dimension_report", task_id="a", dimension="technicals")
        facts = tool.confirm(params)
        assert facts["chars"] > 0
        assert facts["tokens_estimate"] == -(-facts["chars"] // 4)
        assert tool.run(params)["report"]["payload"] == {"rsi_14": 55.0}

        tool, params = _call("get_dimension_report", task_id="a", dimension="fundamentals")
        assert tool.confirm(params)["error"] == "not_found"
        tool, params = _call("get_dimension_report", task_id="zzz", dimension="technicals")
        assert tool.confirm(params)["error"] == "not_found"

    def test_debate_items_page_and_filter(self, isolated_db):
        _done_run("a")
        tool, params = _call("list_debate_items", task_id="a", status=["counted"])
        page = tool.run(params)
        assert [i["claim"] for i in page["items"]] == ["trend up"]
        tool, params = _call("list_debate_items", task_id="zzz")
        assert tool.run(params)["error"] == "not_found"

    def test_transcript_index_then_priced_call(self, isolated_db):
        _done_run("a")
        from src.storage import TieredRunTranscriptRecord
        with isolated_db.get_session() as session:
            session.add(TieredRunTranscriptRecord(
                task_id="a", seq=1, stage="tier1_analysis", model="m",
                prompt="p" * 400, reply="r" * 100,
            ))
            session.commit()
        tool, params = _call("get_transcript", task_id="a")
        index = tool.run(params)
        assert index["items"][0]["prompt_chars"] == 400
        assert "prompt" not in index["items"][0]

        tool, params = _call("get_transcript_call", task_id="a", seq=1)
        assert tool.confirm(params) == {"chars": 500, "tokens_estimate": 125}
        assert tool.run(params)["reply"] == "r" * 100
        tool, params = _call("get_transcript_call", task_id="a", seq=9)
        assert tool.confirm(params)["error"] == "not_found"


class TestWrites:
    def test_start_run_shows_its_inputs_then_queues_through_the_route_path(self, isolated_db, monkeypatch):
        from api.v1.endpoints import tiered

        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        tool, params = _call("start_run", stock_code="AAPL", depth=2, capital=5000)
        facts = tool.confirm(params)
        assert facts == {"stock_code": "AAPL", "run_anyway": False, "tier": 2,
                         "capital": 5000.0, "risk_fraction": 0.01, "reward_risk": 2.0,
                         "hold_weeks": 2}

        started = {}

        def fake_run(code, **kwargs):
            started["code"] = code
            raise RuntimeError("stop here")

        with patch.object(tiered, "_run_analysis", fake_run):
            accepted = tool.run(params)
            assert accepted["stock_code"] == "AAPL"
            assert accepted["status"] in ("running", "queued")
            deadline = time.time() + 5
            while time.time() < deadline and history.get_run_summary(accepted["task_id"])["status"] != "failed":
                time.sleep(0.02)
        assert started["code"] == "AAPL"

    def test_start_run_refusals_are_results(self, isolated_db, monkeypatch):
        monkeypatch.delenv("MAIN_LLM", raising=False)
        tool, params = _call("start_run", stock_code="AAPL")
        assert tool.run(params)["error"] == "llm_not_configured"

        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        history.create_run("dup", "AAPL", inputs={
            "tier": 1, "capital": 100000.0, "risk_fraction": 0.01,
            "reward_risk": 2.0, "hold_weeks": 2,
        }, status="queued")
        refused = tool.run(params)
        assert refused["error"] == "duplicate_run"
        assert refused["task_id"] == "dup"

    def test_start_run_market_open_refusal(self, isolated_db, monkeypatch):
        from src.tiered_analysis import run_gate

        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        monkeypatch.setattr(
            run_gate, "clock_gate",
            lambda symbol, now=None, override=False: run_gate.ClockGateResult(
                not override, "us", "test: open"),
        )
        tool, params = _call("start_run", stock_code="AAPL")
        assert tool.run(params)["error"] == "market_open"

    def test_delete_run_names_the_run_then_removes_it(self, isolated_db):
        history.create_run("q", "AAPL", inputs={"tier": 1}, status="queued")
        tool, params = _call("delete_run", task_id="q")
        assert tool.confirm(params)["run"]["status"] == "queued"
        assert tool.run(params) == {"deleted": True, "task_id": "q", "stock_code": "AAPL", "was": "queued"}
        assert tool.confirm(params)["error"] == "not_found"
        assert tool.run(params)["error"] == "not_found"

    def test_delete_run_refuses_a_running_run(self, isolated_db):
        history.create_run("r", "AAPL", inputs={"tier": 1}, status="queued")
        history.mark_running("r")
        tool, params = _call("delete_run", task_id="r")
        assert tool.confirm(params)["error"] == "run_in_progress"
        assert tool.run(params)["error"] == "run_in_progress"


def test_token_estimate_rounds_up():
    assert tools.token_estimate(0) == 0
    assert tools.token_estimate(1) == 1
    assert tools.token_estimate(8) == 2
