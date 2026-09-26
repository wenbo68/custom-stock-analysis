# -*- coding: utf-8 -*-
"""Offline tests for partial report reads (report_sections.py, 2026-09-21)."""
from __future__ import annotations

import pytest

from src.tiered_analysis.report_sections import (
    ALL_SECTIONS,
    DEFAULT_ITEM_PAGE_SIZE,
    MAX_ITEM_PAGE_SIZE,
    UnknownSectionError,
    deep_analysis_overview,
    deep_analysis_record,
    data_report_index,
    normalize_sections,
    page_count,
    page_vote_items,
    select_sections,
)

ITEMS = [
    {"id": "T1", "data_report": "technicals", "final_status": "counted"},
    {"id": "T2", "data_report": "technicals", "final_status": "excluded"},
    {"id": "F1", "data_report": "fundamentals", "final_status": "counted"},
]
DEBATE = {
    "format": 11,
    "items": ITEMS,
    "outlook": {"outlook": "bullish", "final_score": 6.7},
    "warnings": [],
}
REPORT = {
    "ticker": "AAPL", "outlook": "bullish", "levels": {"entry": 1.0},
    "warnings": [], "llm_usage": {"total": {"calls": 3}},
    "data_reports": [
        {"name": "technicals", "kind": "numeric", "counted": True,
         "payload": {"rsi": 70}, "warnings": []},
        {"name": "fundamentals", "kind": "numeric", "counted": True,
         "payload": {"pe": 20}, "warnings": ["one field blank"]},
        {"name": "company_news", "kind": "textual", "counted": False,
         "summary": "quiet"},
    ],
    "levels_detail": {"levels": {}},
    "sizing": {"shares": 3},
    "plan_warnings": {"entry": []},
    "deep_analysis": {"outlook": "bullish", "score": 7.5, "detail": DEBATE},
    "final": {"outlook": "bullish", "levels": {"entry": 1.0}},
}
#: The light rows every answer carries, whatever the sections.
INDEX = [
    {"name": "technicals", "kind": "numeric", "counted": True, "warnings": []},
    {"name": "fundamentals", "kind": "numeric", "counted": True,
     "warnings": ["one field blank"]},
    {"name": "company_news", "kind": "textual", "counted": False, "warnings": []},
]
#: The debate section as served: the record minus its items, plus a count.
OVERVIEW = {
    "format": 11,
    "outlook": {"outlook": "bullish", "final_score": 6.7},
    "warnings": [],
    "item_count": 3,
}


class TestNormalizeSections:
    def test_nothing_named_means_everything(self):
        assert normalize_sections(None) == ALL_SECTIONS
        assert normalize_sections([]) == ALL_SECTIONS
        assert normalize_sections(["", "  "]) == ALL_SECTIONS

    def test_core_always_rides_along_in_canonical_order(self):
        assert normalize_sections(["plan"]) == ("core", "plan")
        assert normalize_sections(["Plan", "DATA_REPORTS"]) == ("core", "data_reports", "plan")
        assert normalize_sections(["core"]) == ("core",)

    def test_unknown_names_are_named_in_the_error(self):
        with pytest.raises(UnknownSectionError, match="gossip"):
            normalize_sections(["plan", "gossip"])


class TestSelectSections:
    def test_everything_is_the_report_with_the_deep_analysis_as_overview(self):
        picked = select_sections(REPORT, ALL_SECTIONS)
        expected = {
            **REPORT,
            "deep_analysis": {**REPORT["deep_analysis"], "detail": OVERVIEW},
            "data_report_index": INDEX,
        }
        assert picked == expected
        # The stored dict is untouched: its items are still there.
        assert REPORT["deep_analysis"]["detail"]["items"] == ITEMS

    def test_core_drops_the_heavy_parts_and_the_deep_analysis_only(self):
        picked = select_sections(REPORT, ("core",))
        assert set(picked) == {"ticker", "outlook", "levels", "warnings",
                               "llm_usage", "deep_analysis", "final", "data_report_index"}
        assert picked["deep_analysis"] == {"outlook": "bullish", "score": 7.5}
        assert picked["data_report_index"] == INDEX
        # The stored dict is untouched.
        assert "detail" in REPORT["deep_analysis"]

    def test_each_heavy_section_alone(self):
        dims = select_sections(REPORT, ("core", "data_reports"))
        assert dims["data_reports"] == REPORT["data_reports"]
        assert "sizing" not in dims and "detail" not in dims["deep_analysis"]
        plan = select_sections(REPORT, ("core", "plan"))
        assert {"levels_detail", "sizing", "plan_warnings"} <= set(plan)
        assert "data_reports" not in plan
        debate = select_sections(REPORT, ("core", "deep_analysis"))
        assert debate["deep_analysis"] == {"outlook": "bullish", "score": 7.5,
                                   "detail": OVERVIEW}
        assert "data_reports" not in debate and "sizing" not in debate

    def test_named_data_reports_narrow_the_reports(self):
        picked = select_sections(REPORT, ("core", "data_reports"),
                                 data_reports=["FUNDAMENTALS", "company_news"])
        assert [d["name"] for d in picked["data_reports"]] == [
            "fundamentals", "company_news"]
        # An unknown name matches nothing, and that is not an error.
        assert select_sections(REPORT, ("core", "data_reports"),
                               data_reports=["weather"])["data_reports"] == []
        # Blank names mean "no narrowing".
        assert select_sections(REPORT, ("core", "data_reports"),
                               data_reports=[""])["data_reports"] == REPORT["data_reports"]

    def test_old_reports_without_tier2_or_data_reports_are_fine(self):
        old = {"ticker": "AAPL", "outlook": "neutral", "deep_analysis": None}
        served = {**old, "data_report_index": []}
        assert select_sections(old, ("core",)) == served
        assert select_sections(old, ("core", "deep_analysis")) == served


class TestDimensionIndex:
    def test_one_light_row_per_report(self):
        assert data_report_index(REPORT) == INDEX

    def test_missing_or_odd_data_reports_read_as_none(self):
        assert data_report_index({}) == []
        assert data_report_index({"data_reports": "?"}) == []
        assert data_report_index({"data_reports": [{"name": "x"}, 3]}) == [
            {"name": "x", "kind": None, "counted": False, "warnings": []},
        ]


class TestDebateOverview:
    def test_record_lookup(self):
        assert deep_analysis_record(REPORT) is DEBATE
        assert deep_analysis_record({"deep_analysis": None}) is None
        assert deep_analysis_record({"deep_analysis": {"outlook": "bullish"}}) is None
        assert deep_analysis_record(None) is None

    def test_overview_drops_the_items_and_counts_them(self):
        assert deep_analysis_overview(DEBATE) == OVERVIEW
        assert deep_analysis_overview({"outlook": None}) == {"outlook": None, "item_count": 0}
        # Anything that is not a record passes through.
        assert deep_analysis_overview(None) is None
        assert deep_analysis_overview("odd") == "odd"


class TestPageDebateItems:
    def test_default_page_is_everything_in_stored_order(self):
        page = page_vote_items(DEBATE)
        assert page == {
            "items": ITEMS, "page": 1, "page_size": DEFAULT_ITEM_PAGE_SIZE,
            "total": 3, "page_count": 1,
        }
        # Copies, not the stored dicts.
        assert page["items"][0] is not ITEMS[0]

    def test_filters_combine(self):
        assert [i["id"] for i in page_vote_items(
            DEBATE, data_reports=["TECHNICALS"])["items"]] == ["T1", "T2"]
        assert [i["id"] for i in page_vote_items(
            DEBATE, statuses=["counted"])["items"]] == ["T1", "F1"]
        assert [i["id"] for i in page_vote_items(
            DEBATE, data_reports=["technicals"], statuses=["counted"])["items"]] == ["T1"]
        # Blank names mean no filter.
        assert page_vote_items(DEBATE, data_reports=[""])["total"] == 3

    def test_paging(self):
        second = page_vote_items(DEBATE, page=2, page_size=2)
        assert [i["id"] for i in second["items"]] == ["F1"]
        assert second["page_count"] == 2 and second["total"] == 3
        # Past the end is empty, not an error; sizes are clamped.
        assert page_vote_items(DEBATE, page=9, page_size=2)["items"] == []
        assert page_vote_items(DEBATE, page_size=10_000)["page_size"] == MAX_ITEM_PAGE_SIZE
        assert page_vote_items(DEBATE, page=0, page_size=0)["page"] == 1

    def test_no_record_is_an_empty_page(self):
        assert page_vote_items(None)["total"] == 0
        assert page_vote_items({"outlook": None})["items"] == []
        assert page_vote_items({"items": "?"})["page_count"] == 1


def test_page_count():
    assert page_count(0, 10) == 1
    assert page_count(10, 10) == 1
    assert page_count(11, 10) == 2
    assert page_count(5, 0) == 5
