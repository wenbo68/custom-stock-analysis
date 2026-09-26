# -*- coding: utf-8 -*-
"""Offline tests for the tiered run history (persistent run list).

Runs persist in the tiered_runs table so the web page keeps a clickable
history across navigation and server restarts. The list is filtered and
paged in SQL (2026-09-21) over real columns; transcripts are served as
an index plus one call at a time. Uses the repo-standard isolated sqlite
fixture.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from src.tiered_analysis.history import (
    RunFilters,
    RunInProgressError,
    create_run,
    delete_run,
    get_vote_items,
    get_run,
    get_transcript_call,
    list_runs,
    list_tickers,
    list_transcript,
    mark_done,
    mark_failed,
    run_exists,
    status_counts,
)


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    db_path = tmp_path / "tiered_history.db"
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


# Deliberately old-shaped stored JSON: coverage grades are retired
# (2026-08-19) and new runs never write the key, but rows persisted
# before the retirement still carry it — history must reload such
# results verbatim, never choke on the stray key.
RESULT = {"ticker": "AAPL", "outlook": "neutral", "score": 56,
          "data_reports": [{"data_report": "technicals", "coverage": "full"}]}


def _rows(**kwargs):
    """The rows of one list page, keyed by run id."""
    return {row["run_id"]: row for row in list_runs(**kwargs)["items"]}


class TestTieredRunHistory:
    def test_create_and_get_running_run(self, isolated_db):
        create_run("task-1", "AAPL")
        run = get_run("task-1")
        assert run["status"] == "running"
        assert run["ticker"] == "AAPL"
        assert run["result"] is None
        assert run["created_at"]
        assert run_exists("task-1") and not run_exists("nope")

    def test_mark_done_stores_result(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_done("task-1", RESULT)
        run = get_run("task-1")
        assert run["status"] == "done"
        assert run["result"]["outlook"] == "neutral"
        assert run["result"]["data_reports"][0]["coverage"] == "full"
        assert run["sections"] == ["core", "data_reports", "deep_analysis", "plan"]

    def test_mark_failed_stores_error(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_failed("task-1", "LLM quota exhausted")
        run = get_run("task-1")
        assert run["status"] == "failed"
        assert "LLM quota exhausted" in run["error"]

    def test_get_unknown_run_returns_none(self, isolated_db):
        assert get_run("nope") is None

    def test_list_runs_newest_first_without_results(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_done("task-1", RESULT)
        create_run("task-2", "NVDA")
        page = list_runs()
        runs = page["items"]
        assert [r["run_id"] for r in runs] == ["task-2", "task-1"]
        assert runs[0]["status"] == "running"
        assert runs[1]["status"] == "done"
        # list is lightweight: no full result payloads
        assert all("result" not in r for r in runs)
        assert (page["page"], page["page_size"], page["total"], page["page_count"]) == (1, 10, 2, 1)

    def test_list_digest_has_outlook_shares_and_tier(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_done("task-1", {**RESULT,
                             "tier": 2,
                             "outlook": "bullish",
                             "final": {"outlook": "bullish", "tier": 2},
                             "sizing": {"shares": 41,
                                        "inputs": {"capital": 100000,
                                                   "risk_pct": 1.0,
                                                   "reward_ratio": 2.0}}})
        create_run("task-2", "NVDA")  # still running — no digest yet
        runs = _rows()
        assert runs["task-1"]["outlook"] == "bullish"
        assert runs["task-1"]["shares"] == 41
        assert runs["task-1"]["tier"] == 2
        assert runs["task-1"]["capital"] == 100000
        # Rows speak the run form's words: risk as a percent, the reward
        # as a ratio (2026-09-24); the columns keep the engine's names.
        assert runs["task-1"]["risk_pct"] == 1.0
        assert runs["task-1"]["reward_ratio"] == 2.0
        assert runs["task-2"]["outlook"] is None
        assert runs["task-2"]["shares"] is None
        assert runs["task-2"]["tier"] is None
        assert runs["task-2"]["capital"] is None
        assert runs["task-2"]["risk_pct"] is None
        assert runs["task-2"]["reward_ratio"] is None

    def test_running_rows_show_the_inputs_recorded_at_creation(self, isolated_db):
        # Owner decision 2026-07-24: capital/risk/reward/tier are visible
        # on the history row while the run is still in flight. max_hold_weeks
        # joined the digest 2026-08-09 (the run-history max-hold column).
        create_run("task-1", "NVDA", inputs={
            "tier": 2, "capital": 100000,
            "risk_pct": 1.0, "reward_ratio": 2.0, "max_hold_weeks": 3,
        })
        row = _rows()["task-1"]
        assert row["status"] == "running"
        assert row["tier"] == 2
        assert row["capital"] == 100000
        assert row["risk_pct"] == 1.0
        assert row["reward_ratio"] == 2.0
        assert row["max_hold_weeks"] == 3

    def test_finished_report_values_beat_the_creation_inputs(self, isolated_db):
        create_run("task-1", "NVDA", inputs={
            "tier": 2, "capital": 100000,
            "risk_pct": 1.0, "reward_ratio": 2.0, "max_hold_weeks": 3,
        })
        mark_done("task-1", {**RESULT,
                             "tier": 2,
                             "outlook": "bullish",
                             "final": {"outlook": "bullish", "tier": 2},
                             "max_hold_weeks": 2,
                             "sizing": {"shares": 51,
                                        "inputs": {"capital": 50000,
                                                   "risk_pct": 2.0,
                                                   "reward_ratio": 3.0}}})
        row = _rows()["task-1"]
        assert row["capital"] == 50000
        assert row["risk_pct"] == 2.0
        assert row["reward_ratio"] == 3.0
        assert row["max_hold_weeks"] == 2

    def test_failed_rows_keep_the_creation_inputs(self, isolated_db):
        create_run("task-1", "NVDA", inputs={"tier": 1, "capital": 5000})
        mark_failed("task-1", "boom")
        row = _rows()["task-1"]
        assert row["capital"] == 5000 and row["tier"] == 1
        assert row["outlook"] is None

    def test_list_digest_degrades_on_refused_runs(self, isolated_db):
        # no sizing block at all -> dash shares
        create_run("task-1", "AAPL")
        mark_done("task-1", {**RESULT, "tier": 1})
        # sizing ran but refused to buy (shares None) -> 0, like the report
        # card
        create_run("task-2", "MSFT")
        mark_done("task-2", {**RESULT, "tier": 2,
                             "final": {"outlook": "neutral", "tier": 2},
                             "sizing": {"shares": None}})
        runs = _rows()
        assert runs["task-1"]["outlook"] == "neutral"
        assert runs["task-1"]["shares"] is None
        assert runs["task-1"]["tier"] == 1
        assert runs["task-2"]["shares"] == 0
        assert runs["task-2"]["tier"] == 2

    def test_corrupt_result_json_surfaces_as_failed_parse(self, isolated_db):
        from src.storage import DatabaseManager, TieredRunRecord

        create_run("task-1", "AAPL")
        mark_done("task-1", RESULT)
        with DatabaseManager.get_instance().get_session() as session:
            row = session.query(TieredRunRecord).filter_by(run_id="task-1").one()
            row.result_json = "{not json"
            session.commit()
        run = get_run("task-1")
        assert run["result"] is None
        assert "unreadable" in (run["error"] or "")


class TestPaging:
    def test_pages_newest_first_with_totals(self, isolated_db):
        for index in range(7):
            create_run(f"task-{index}", "AAPL")
        first = list_runs(page=1, page_size=3)
        assert [r["run_id"] for r in first["items"]] == ["task-6", "task-5", "task-4"]
        assert (first["total"], first["page_count"]) == (7, 3)
        last = list_runs(page=3, page_size=3)
        assert [r["run_id"] for r in last["items"]] == ["task-0"]
        # Past the end: empty, not an error.
        assert list_runs(page=4, page_size=3)["items"] == []

    def test_page_size_is_clamped(self, isolated_db):
        create_run("task-1", "AAPL")
        assert list_runs(page_size=0)["page_size"] == 1
        assert list_runs(page_size=10_000)["page_size"] == 200
        assert list_runs(page=0)["page"] == 1

    def test_empty_history_is_one_empty_page(self, isolated_db):
        page = list_runs()
        assert page == {"items": [], "page": 1, "page_size": 10, "total": 0, "page_count": 1}


class TestFilters:
    def _seed(self):
        create_run("bull", "AAPL", inputs={
            "tier": 2, "capital": 100000, "risk_pct": 1.0,
            "reward_ratio": 2.0, "max_hold_weeks": 2,
        })
        mark_done("bull", {**RESULT, "outlook": "bullish", "tier": 2})
        create_run("bear", "nvda", inputs={
            "tier": 1, "capital": 50000, "risk_pct": 2.0,
            "reward_ratio": 3.0, "max_hold_weeks": 4,
        })
        mark_done("bear", {**RESULT, "outlook": "bearish", "tier": 1})
        create_run("blank", "MSFT", inputs={"tier": 1, "capital": 20000})
        mark_done("blank", {**RESULT, "outlook": "no_outlook", "tier": 1})
        create_run("dead", "AAPL", inputs={"tier": 1, "capital": 100000})
        mark_failed("dead", "boom")
        create_run("live", "TSLA", inputs={"tier": 2, "capital": 100000})

    def _ids(self, **kwargs):
        return sorted(_rows(filters=RunFilters(**kwargs)))

    def test_ticker_filter_ignores_case_and_takes_several(self, isolated_db):
        self._seed()
        assert self._ids(tickers=["aapl"]) == ["bull", "dead"]
        assert self._ids(tickers=["NVDA", "tsla"]) == ["bear", "live"]

    def test_status_filter(self, isolated_db):
        self._seed()
        assert self._ids(statuses=["failed"]) == ["dead"]
        assert self._ids(statuses=["running", "failed"]) == ["dead", "live"]

    def test_outlook_filter_and_the_no_opinion_dash(self, isolated_db):
        self._seed()
        assert self._ids(outlooks=["bullish"]) == ["bull"]
        assert self._ids(outlooks=["bullish", "bearish"]) == ["bear", "bull"]
        # "no_outlook": unfinished, failed, and finished-with-no-outlook rows.
        assert self._ids(outlooks=["no_outlook"]) == ["blank", "dead", "live"]
        assert self._ids(outlooks=["no_outlook", "bearish"]) == ["bear", "blank", "dead", "live"]

    def test_tier_and_hold_filters(self, isolated_db):
        self._seed()
        assert self._ids(tiers=[2]) == ["bull", "live"]
        assert self._ids(max_hold_weeks=[4]) == ["bear"]
        assert self._ids(max_hold_weeks=[2, 4]) == ["bear", "bull"]

    def test_ranges_are_inclusive_and_skip_rows_without_the_value(self, isolated_db):
        self._seed()
        assert self._ids(capital_min=100000) == ["bull", "dead", "live"]
        assert self._ids(capital_max=50000) == ["bear", "blank"]
        assert self._ids(capital_min=20000, capital_max=50000) == ["bear", "blank"]
        assert self._ids(risk_pct_min=2.0) == ["bear"]
        assert self._ids(risk_pct_max=1.0) == ["bull"]
        # Rows with no reward recorded never match a reward range.
        assert self._ids(reward_ratio_min=2.0) == ["bear", "bull"]
        assert self._ids(reward_ratio_max=2.5) == ["bull"]

    def test_filters_combine_with_and(self, isolated_db):
        self._seed()
        assert self._ids(tickers=["AAPL"], statuses=["done"]) == ["bull"]
        assert self._ids(tiers=[1], outlooks=["no_outlook"]) == ["blank", "dead"]

    def test_date_range_compares_in_utc(self, isolated_db):
        from src.storage import DatabaseManager, TieredRunRecord

        create_run("old", "AAPL")
        create_run("new", "AAPL")
        with DatabaseManager.get_instance().get_session() as session:
            row = session.query(TieredRunRecord).filter_by(run_id="old").one()
            row.created_at = datetime(2026, 1, 1, 12, 0, 0)  # UTC-naive
            session.commit()
        # An aware bound in another zone is converted before comparing.
        jan_2_local = datetime(2026, 1, 2, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        assert self._ids(created_after=jan_2_local) == ["new"]
        assert self._ids(created_before=jan_2_local) == ["old"]
        # created_before is exclusive, created_after inclusive.
        noon = datetime(2026, 1, 1, 12, 0, 0)
        assert self._ids(created_after=noon) == ["new", "old"]
        assert self._ids(created_before=noon) == []

    def test_total_counts_matches_not_page(self, isolated_db):
        self._seed()
        page = list_runs(RunFilters(statuses=["done"]), page=1, page_size=2)
        assert page["total"] == 3 and page["page_count"] == 2
        assert len(page["items"]) == 2

    def test_tickers_are_distinct_and_sorted(self, isolated_db):
        self._seed()
        assert list_tickers() == ["AAPL", "MSFT", "TSLA", "nvda"]
        create_run("again", "AAPL")
        assert list_tickers().count("AAPL") == 1


class TestSections:
    FULL = {
        "ticker": "AAPL", "outlook": "bullish", "levels": {"entry": 1},
        "data_reports": [
            {"name": "technicals", "payload": {"rsi": 70}},
            {"name": "fundamentals", "payload": {"pe": 20}},
        ],
        "levels_detail": {"levels": {}}, "sizing": {"shares": 3},
        "plan_warnings": {},
        "deep_analysis": {"outlook": "bullish", "score": 7.5,
                  "detail": {"items": [{"id": "t1"}]}},
    }

    INDEX = [
        {"name": "technicals", "kind": None, "counted": False, "warnings": []},
        {"name": "fundamentals", "kind": None, "counted": False, "warnings": []},
    ]

    def test_default_is_everything_with_the_deep_analysis_as_overview(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_done("task-1", self.FULL)
        assert get_run("task-1")["result"] == {
            **self.FULL,
            "deep_analysis": {"outlook": "bullish", "score": 7.5,
                      "detail": {"item_count": 1}},
            "data_report_index": self.INDEX,
        }

    def test_core_only_drops_the_heavy_parts_but_keeps_tier2_headline(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_done("task-1", self.FULL)
        run = get_run("task-1", sections=("core",))
        assert run["sections"] == ["core"]
        assert run["result"] == {
            "ticker": "AAPL", "outlook": "bullish", "levels": {"entry": 1},
            "deep_analysis": {"outlook": "bullish", "score": 7.5},
            "data_report_index": self.INDEX,
        }

    def test_one_section_plus_a_named_data_report(self, isolated_db):
        create_run("task-1", "AAPL")
        mark_done("task-1", self.FULL)
        run = get_run("task-1", sections=("core", "data_reports"),
                      data_reports=["Fundamentals"])
        assert run["result"]["data_reports"] == [
            {"name": "fundamentals", "payload": {"pe": 20}}]
        assert "sizing" not in run["result"]
        plan = get_run("task-1", sections=("core", "plan"))["result"]
        assert plan["sizing"] == {"shares": 3} and "data_reports" not in plan
        debate = get_run("task-1", sections=("core", "deep_analysis"))["result"]
        assert debate["deep_analysis"]["detail"] == {"item_count": 1}

    def test_unfinished_run_has_null_result_whatever_is_asked(self, isolated_db):
        create_run("task-1", "AAPL")
        run = get_run("task-1", sections=("core", "plan"))
        assert run["result"] is None and run["sections"] == ["core", "plan"]


class TestDebateItems:
    def test_unknown_run_is_none_and_a_run_without_a_record_is_empty(self, isolated_db):
        assert get_vote_items("nope") is None
        create_run("task-1", "AAPL")
        assert get_vote_items("task-1")["total"] == 0
        mark_done("task-1", RESULT)  # tier 1: no debate record
        assert get_vote_items("task-1") == {
            "items": [], "page": 1, "page_size": 20, "total": 0, "page_count": 1,
        }

    def test_pages_and_filters_the_stored_items(self, isolated_db):
        items = [
            {"id": "T1", "data_report": "technicals", "final_status": "counted"},
            {"id": "T2", "data_report": "technicals", "final_status": "excluded"},
            {"id": "F1", "data_report": "fundamentals", "final_status": "counted"},
        ]
        create_run("task-1", "AAPL")
        mark_done("task-1", {**RESULT, "deep_analysis": {"detail": {"items": items}}})
        page = get_vote_items("task-1", statuses=["counted"], page=2, page_size=1)
        assert [i["id"] for i in page["items"]] == ["F1"]
        assert page["total"] == 2 and page["page_count"] == 2
        assert get_vote_items("task-1", data_reports=["technicals"])["total"] == 2


def _record_call(run_id, seq, prompt="hello there", reply="ok", error=None):
    from src.storage import DatabaseManager, TieredRunTranscriptRecord

    with DatabaseManager.get_instance().get_session() as session:
        session.add(TieredRunTranscriptRecord(
            run_id=run_id, call_number=seq, stage="preliminary_analysis",
            llm="gemini/flash", temperature=0.0, time_ms=120,
            input_tokens=10, output_tokens=5, structured="schema",
            error=error, input=prompt, output=reply,
        ))
        session.commit()


class TestDeleteRun:
    def test_unknown_run_is_none(self, isolated_db):
        assert delete_run("nope") is None

    def test_finished_run_goes_with_its_transcript(self, isolated_db):
        create_run("task-1", "AAPL", inputs={"tier": 2})
        mark_done("task-1", RESULT)
        _record_call("task-1", 1)
        create_run("task-2", "NVDA")
        _record_call("task-2", 1)

        deleted = delete_run("task-1")

        assert deleted["run_id"] == "task-1" and deleted["status"] == "done"
        assert deleted["ticker"] == "AAPL" and deleted["tier"] == 2
        assert not run_exists("task-1")
        assert list_transcript("task-1") == []
        # The neighbour and its transcript are untouched.
        assert run_exists("task-2") and len(list_transcript("task-2")) == 1

    def test_queued_and_failed_runs_can_go_but_a_running_one_stays(self, isolated_db):
        create_run("queued", "AAPL", status="queued")
        create_run("failed", "AAPL")
        mark_failed("failed", "boom")
        create_run("running", "AAPL")

        assert delete_run("queued")["status"] == "queued"
        assert delete_run("failed")["status"] == "failed"
        with pytest.raises(RunInProgressError) as caught:
            delete_run("running")
        assert caught.value.run_id == "running"
        assert run_exists("running")


class TestStatusCounts:
    def test_every_status_is_present(self, isolated_db):
        assert status_counts() == {"queued": 0, "running": 0, "done": 0, "failed": 0}
        create_run("a", "AAPL", status="queued")
        create_run("b", "AAPL", status="queued")
        create_run("c", "AAPL")
        create_run("d", "AAPL")
        mark_done("d", RESULT)
        assert status_counts() == {"queued": 2, "running": 1, "done": 1, "failed": 0}


class TestTranscript:
    def _record(self, run_id, seq, prompt="hello there", reply="ok", error=None):
        _record_call(run_id, seq, prompt=prompt, reply=reply, error=error)

    def test_index_has_facts_and_sizes_but_no_text(self, isolated_db):
        create_run("task-1", "AAPL")
        self._record("task-1", 2, prompt="second", reply=None, error="boom")
        self._record("task-1", 1)
        rows = list_transcript("task-1")
        assert [row["call_number"] for row in rows] == [1, 2]
        first = rows[0]
        assert "input" not in first and "output" not in first
        assert first["input_chars"] == len("hello there")
        assert first["output_chars"] == 2
        assert first["stage"] == "preliminary_analysis" and first["llm"] == "gemini/flash"
        assert first["time_ms"] == 120 and first["input_tokens"] == 10
        assert rows[1]["output_chars"] == 0 and rows[1]["error"] == "boom"
        assert list_transcript("unknown") == []

    def test_one_call_carries_its_text(self, isolated_db):
        create_run("task-1", "AAPL")
        self._record("task-1", 1)
        call = get_transcript_call("task-1", 1)
        assert call["input"] == "hello there" and call["output"] == "ok"
        assert call["call_number"] == 1 and call["stage"] == "preliminary_analysis"
        assert "input_chars" not in call
        assert get_transcript_call("task-1", 2) is None
        assert get_transcript_call("nope", 1) is None
