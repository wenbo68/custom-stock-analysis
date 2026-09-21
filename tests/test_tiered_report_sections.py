# -*- coding: utf-8 -*-
"""Offline tests for partial report reads (report_sections.py, 2026-09-21)."""
from __future__ import annotations

import pytest

from src.tiered_analysis.report_sections import (
    ALL_SECTIONS,
    DEFAULT_ITEM_PAGE_SIZE,
    MAX_ITEM_PAGE_SIZE,
    UnknownSectionError,
    debate_overview,
    debate_record,
    dimension_index,
    normalize_sections,
    page_count,
    page_debate_items,
    select_sections,
)

ITEMS = [
    {"id": "T1", "dimension": "technicals", "final_status": "counted"},
    {"id": "T2", "dimension": "technicals", "final_status": "excluded"},
    {"id": "F1", "dimension": "fundamentals", "final_status": "counted"},
]
DEBATE = {
    "format": 11,
    "items": ITEMS,
    "outlook": {"outlook": "bullish", "final_score": 6.7},
    "warnings": [],
}
REPORT = {
    "symbol": "AAPL", "outlook": "bullish", "levels": {"entry": 1.0},
    "warnings": [], "llm_usage": {"total": {"calls": 3}},
    "dimensions": [
        {"dimension": "technicals", "kind": "numeric", "is_actionable": True,
         "payload": {"rsi": 70}, "warnings": []},
        {"dimension": "fundamentals", "kind": "numeric", "is_actionable": True,
         "payload": {"pe": 20}, "warnings": ["one field blank"]},
        {"dimension": "company_news", "kind": "textual", "is_actionable": False,
         "narrative": "quiet"},
    ],
    "levels_detail": {"levels": {}},
    "sizing": {"shares": 3},
    "plan_warnings": {"entry": []},
    "tier2": {"outlook": "bullish", "score": 7.5, "debate_detail": DEBATE},
    "final": {"outlook": "bullish", "levels": {"entry": 1.0}},
}
#: The light rows every answer carries, whatever the sections.
INDEX = [
    {"dimension": "technicals", "kind": "numeric", "is_actionable": True, "warnings": []},
    {"dimension": "fundamentals", "kind": "numeric", "is_actionable": True,
     "warnings": ["one field blank"]},
    {"dimension": "company_news", "kind": "textual", "is_actionable": False, "warnings": []},
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
        assert normalize_sections(["Plan", "DIMENSIONS"]) == ("core", "dimensions", "plan")
        assert normalize_sections(["core"]) == ("core",)

    def test_unknown_names_are_named_in_the_error(self):
        with pytest.raises(UnknownSectionError, match="gossip"):
            normalize_sections(["plan", "gossip"])


class TestSelectSections:
    def test_everything_is_the_report_with_the_debate_as_overview(self):
        picked = select_sections(REPORT, ALL_SECTIONS)
        expected = {
            **REPORT,
            "tier2": {**REPORT["tier2"], "debate_detail": OVERVIEW},
            "dimension_index": INDEX,
        }
        assert picked == expected
        # The stored dict is untouched: its items are still there.
        assert REPORT["tier2"]["debate_detail"]["items"] == ITEMS

    def test_core_drops_the_heavy_parts_and_the_debate_only(self):
        picked = select_sections(REPORT, ("core",))
        assert set(picked) == {"symbol", "outlook", "levels", "warnings",
                               "llm_usage", "tier2", "final", "dimension_index"}
        assert picked["tier2"] == {"outlook": "bullish", "score": 7.5}
        assert picked["dimension_index"] == INDEX
        # The stored dict is untouched.
        assert "debate_detail" in REPORT["tier2"]

    def test_each_heavy_section_alone(self):
        dims = select_sections(REPORT, ("core", "dimensions"))
        assert dims["dimensions"] == REPORT["dimensions"]
        assert "sizing" not in dims and "debate_detail" not in dims["tier2"]
        plan = select_sections(REPORT, ("core", "plan"))
        assert {"levels_detail", "sizing", "plan_warnings"} <= set(plan)
        assert "dimensions" not in plan
        debate = select_sections(REPORT, ("core", "debate"))
        assert debate["tier2"] == {"outlook": "bullish", "score": 7.5,
                                   "debate_detail": OVERVIEW}
        assert "dimensions" not in debate and "sizing" not in debate

    def test_named_dimensions_narrow_the_reports(self):
        picked = select_sections(REPORT, ("core", "dimensions"),
                                 dimensions=["FUNDAMENTALS", "company_news"])
        assert [d["dimension"] for d in picked["dimensions"]] == [
            "fundamentals", "company_news"]
        # An unknown name matches nothing, and that is not an error.
        assert select_sections(REPORT, ("core", "dimensions"),
                               dimensions=["weather"])["dimensions"] == []
        # Blank names mean "no narrowing".
        assert select_sections(REPORT, ("core", "dimensions"),
                               dimensions=[""])["dimensions"] == REPORT["dimensions"]

    def test_old_reports_without_tier2_or_dimensions_are_fine(self):
        old = {"symbol": "AAPL", "outlook": "neutral", "tier2": None}
        served = {**old, "dimension_index": []}
        assert select_sections(old, ("core",)) == served
        assert select_sections(old, ("core", "debate")) == served


class TestDimensionIndex:
    def test_one_light_row_per_report(self):
        assert dimension_index(REPORT) == INDEX

    def test_missing_or_odd_dimensions_read_as_none(self):
        assert dimension_index({}) == []
        assert dimension_index({"dimensions": "?"}) == []
        assert dimension_index({"dimensions": [{"dimension": "x"}, 3]}) == [
            {"dimension": "x", "kind": None, "is_actionable": False, "warnings": []},
        ]


class TestDebateOverview:
    def test_record_lookup(self):
        assert debate_record(REPORT) is DEBATE
        assert debate_record({"tier2": None}) is None
        assert debate_record({"tier2": {"outlook": "bullish"}}) is None
        assert debate_record(None) is None

    def test_overview_drops_the_items_and_counts_them(self):
        assert debate_overview(DEBATE) == OVERVIEW
        assert debate_overview({"outlook": None}) == {"outlook": None, "item_count": 0}
        # Anything that is not a record passes through.
        assert debate_overview(None) is None
        assert debate_overview("odd") == "odd"


class TestPageDebateItems:
    def test_default_page_is_everything_in_stored_order(self):
        page = page_debate_items(DEBATE)
        assert page == {
            "items": ITEMS, "page": 1, "page_size": DEFAULT_ITEM_PAGE_SIZE,
            "total": 3, "page_count": 1,
        }
        # Copies, not the stored dicts.
        assert page["items"][0] is not ITEMS[0]

    def test_filters_combine(self):
        assert [i["id"] for i in page_debate_items(
            DEBATE, dimensions=["TECHNICALS"])["items"]] == ["T1", "T2"]
        assert [i["id"] for i in page_debate_items(
            DEBATE, statuses=["counted"])["items"]] == ["T1", "F1"]
        assert [i["id"] for i in page_debate_items(
            DEBATE, dimensions=["technicals"], statuses=["counted"])["items"]] == ["T1"]
        # Blank names mean no filter.
        assert page_debate_items(DEBATE, dimensions=[""])["total"] == 3

    def test_paging(self):
        second = page_debate_items(DEBATE, page=2, page_size=2)
        assert [i["id"] for i in second["items"]] == ["F1"]
        assert second["page_count"] == 2 and second["total"] == 3
        # Past the end is empty, not an error; sizes are clamped.
        assert page_debate_items(DEBATE, page=9, page_size=2)["items"] == []
        assert page_debate_items(DEBATE, page_size=10_000)["page_size"] == MAX_ITEM_PAGE_SIZE
        assert page_debate_items(DEBATE, page=0, page_size=0)["page"] == 1

    def test_no_record_is_an_empty_page(self):
        assert page_debate_items(None)["total"] == 0
        assert page_debate_items({"outlook": None})["items"] == []
        assert page_debate_items({"items": "?"})["page_count"] == 1


def test_page_count():
    assert page_count(0, 10) == 1
    assert page_count(10, 10) == 1
    assert page_count(11, 10) == 2
    assert page_count(5, 0) == 5
