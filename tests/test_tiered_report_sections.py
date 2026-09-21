# -*- coding: utf-8 -*-
"""Offline tests for partial report reads (report_sections.py, 2026-09-21)."""
from __future__ import annotations

import pytest

from src.tiered_analysis.report_sections import (
    ALL_SECTIONS,
    UnknownSectionError,
    normalize_sections,
    select_sections,
)

REPORT = {
    "symbol": "AAPL", "outlook": "bullish", "levels": {"entry": 1.0},
    "warnings": [], "llm_usage": {"total": {"calls": 3}},
    "dimensions": [
        {"dimension": "technicals", "payload": {"rsi": 70}},
        {"dimension": "fundamentals", "payload": {"pe": 20}},
        {"dimension": "company_news", "narrative": "quiet"},
    ],
    "levels_detail": {"levels": {}},
    "sizing": {"shares": 3},
    "plan_warnings": {"entry": []},
    "tier2": {"outlook": "bullish", "score": 7.5, "debate_detail": {"items": []}},
    "final": {"outlook": "bullish", "levels": {"entry": 1.0}},
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
    def test_everything_is_a_faithful_copy(self):
        picked = select_sections(REPORT, ALL_SECTIONS)
        assert picked == REPORT
        assert picked is not REPORT

    def test_core_drops_the_heavy_parts_and_the_debate_only(self):
        picked = select_sections(REPORT, ("core",))
        assert set(picked) == {"symbol", "outlook", "levels", "warnings",
                               "llm_usage", "tier2", "final"}
        assert picked["tier2"] == {"outlook": "bullish", "score": 7.5}
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
        assert debate["tier2"] == REPORT["tier2"]
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
        assert select_sections(old, ("core",)) == old
        assert select_sections(old, ("core", "debate")) == old
