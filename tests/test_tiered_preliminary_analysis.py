# -*- coding: utf-8 -*-
"""Offline tests for the tier-1 quick judge (the one-call outlook that
replaced the legacy DSA-blob delegate, 2026-08-10). No LLM, no network."""
from __future__ import annotations

import unittest

from src.tiered_analysis.deep_analysis import NEUTRAL_MAX, BEARISH_BELOW
from src.tiered_analysis.llm_support import LlmConfigError
from src.tiered_analysis.providers.base import (
    DataReport,
    SourceKind,
)
from src.tiered_analysis.preliminary_analysis import (
    MAX_ATTEMPTS,
    PRELIMINARY_DETAIL_FORMAT,
    PreliminaryAnalysis,
    PreliminaryResult,
    PreliminaryOutlook,
)
from src.tiered_analysis.schema import Outlook


def _dims():
    return [
        DataReport(
            name="technicals",
            kind=SourceKind.NUMERIC,
            payload={"rsi_14": 56.28},
        ),
        DataReport(
            name="macro_economy",
            kind=SourceKind.TEXTUAL,
            payload={"headline": "rates unchanged"},
        ),
    ]


def _run(summarizer, max_hold_weeks=3):
    return PreliminaryAnalysis(summarizer=summarizer).run(
        "AAPL", _dims(), max_hold_weeks=max_hold_weeks
    )


class TestPrompt(unittest.TestCase):
    def test_prompt_carries_hold_time_and_evidence_but_no_plan_levels(self):
        prompts = []

        def summarizer(prompt):
            prompts.append(prompt)
            return '{"score": 7, "summary": "Looks constructive overall."}'

        _run(summarizer, max_hold_weeks=3)

        self.assertEqual(len(prompts), 1)
        prompt = prompts[0]
        self.assertIn("3 weeks", prompt)
        self.assertIn("AAPL", prompt)
        # Plan levels are not the judge's business (2026-09-16).
        self.assertNotIn("plan levels", prompt)
        self.assertNotIn("entry=", prompt)
        self.assertIn("technicals", prompt)
        self.assertIn("56.28", prompt)
        self.assertIn("rates unchanged", prompt)

    def test_single_week_wording(self):
        prompts = []

        def summarizer(prompt):
            prompts.append(prompt)
            return '{"score": 5, "summary": "Mixed picture."}'

        _run(summarizer, max_hold_weeks=1)
        self.assertIn("1 week", prompts[0])
        self.assertNotIn("1 weeks", prompts[0])


class TestOutlook(unittest.TestCase):
    def test_score_maps_to_outlook_with_deep_analysis_cutpoints(self):
        cases = [
            (7.4, Outlook.BULLISH),
            (NEUTRAL_MAX, Outlook.NEUTRAL),
            (5.0, Outlook.NEUTRAL),
            (BEARISH_BELOW - 0.1, Outlook.BEARISH),
            (0.0, Outlook.BEARISH),
            (10.0, Outlook.BULLISH),
        ]
        for score, expected in cases:
            result = _run(
                lambda p, s=score: f'{{"score": {s}, "summary": "Reasoning."}}'
            )
            self.assertIsNotNone(result.outlook, score)
            self.assertEqual(result.outlook.outlook, expected, score)
            self.assertEqual(result.outlook.final_score, round(score, 2))

    def test_score_rounds_to_two_decimals(self):
        result = _run(lambda p: '{"score": 6.666, "summary": "Close call."}')
        self.assertEqual(result.outlook.final_score, 6.67)

    def test_summary_is_stripped(self):
        result = _run(lambda p: '{"score": 7, "summary": "  Padded.  "}')
        self.assertEqual(result.outlook.summary, "Padded.")

    def test_fenced_json_is_accepted(self):
        result = _run(
            lambda p: '```json\n{"score": 7, "summary": "Fenced reply."}\n```'
        )
        self.assertIsNotNone(result.outlook)


class TestFailures(unittest.TestCase):
    def test_bad_reply_retries_with_the_problem_named(self):
        prompts = []

        def summarizer(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return "not json at all"
            return '{"score": 3, "summary": "Bearish on review."}'

        result = _run(summarizer)

        self.assertEqual(len(prompts), 2)
        self.assertIn("rejected", prompts[1])
        self.assertEqual(result.outlook.outlook, Outlook.BEARISH)
        self.assertTrue(any("rejected" in w for w in result.warnings))

    def test_out_of_range_or_missing_fields_are_rejected(self):
        for reply in (
            '{"score": 11, "summary": "Too high."}',
            '{"score": -1, "summary": "Too low."}',
            '{"score": "n/a", "summary": "Not a number."}',
            '{"summary": "No score."}',
            '{"score": 7, "summary": ""}',
            '{"score": 7}',
            "[]",
        ):
            result = _run(lambda p, r=reply: r)
            self.assertIsNone(result.outlook, reply)

    def test_all_attempts_bad_means_no_outlook_and_honest_warnings(self):
        calls = []

        def summarizer(prompt):
            calls.append(prompt)
            return "garbage"

        result = _run(summarizer)
        self.assertEqual(len(calls), MAX_ATTEMPTS)
        self.assertIsNone(result.outlook)
        self.assertTrue(any("no outlook" in w for w in result.warnings))

    def test_llm_config_error_stops_immediately(self):
        calls = []

        def summarizer(prompt):
            calls.append(prompt)
            raise LlmConfigError("MAIN_LLM is not set")

        result = _run(summarizer)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(result.outlook)
        self.assertTrue(any("MAIN_LLM" in w for w in result.warnings))

    def test_transient_llm_crash_is_retried_then_reported(self):
        calls = []

        def summarizer(prompt):
            calls.append(prompt)
            raise RuntimeError("socket closed")

        result = _run(summarizer)
        self.assertEqual(len(calls), MAX_ATTEMPTS)
        self.assertIsNone(result.outlook)
        self.assertTrue(any("socket closed" in w for w in result.warnings))


class TestDetail(unittest.TestCase):
    def test_detail_carries_format_and_outlook_score(self):
        detail = PreliminaryResult(
            outlook=PreliminaryOutlook(
                outlook=Outlook.BULLISH, final_score=7.25, summary="Up."
            )
        ).to_detail()
        self.assertEqual(detail["format"], PRELIMINARY_DETAIL_FORMAT)
        self.assertEqual(detail["outlook"]["final_score"], 7.25)
        self.assertEqual(detail["outlook"]["outlook"], "bullish")

    def test_failed_result_detail_has_no_outlook(self):
        detail = PreliminaryResult(warnings=["boom"]).to_detail()
        self.assertEqual(detail["format"], PRELIMINARY_DETAIL_FORMAT)
        self.assertNotIn("outlook", detail)


if __name__ == "__main__":
    unittest.main()
