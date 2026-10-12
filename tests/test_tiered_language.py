# -*- coding: utf-8 -*-
"""The run's language (owner decision 2026-09-26): every sentence a
reader sees in a report is written in the language the user chose for
the app, and every LLM stage that writes such text checks its reply
and asks again — up to LANGUAGE_RETRY_LIMIT times — when the reply is
in the wrong language. Offline: fake summarizers, no network.

The check itself (src/languages.py) is covered in test_chat_language.py;
here it is the run-side plumbing: ``in_language`` (llm_support), the
preliminary analysis and the news summaries. The deep analysis and the
API have their language tests next to their other tests."""
from __future__ import annotations

import json
import unittest

from src.languages import LANGUAGE_RETRY_LIMIT
from src.tiered_analysis.llm_support import (
    LlmUsageTracker,
    in_language,
    language_rule,
    run_language,
)
from src.tiered_analysis.news_screen import llm_summarize_articles
from src.tiered_analysis.preliminary_analysis import PreliminaryAnalysis
from src.tiered_analysis.providers.base import DataReport, SourceKind

ENGLISH = "The stock closed above both moving averages and momentum is improving steadily."
CHINESE = "该股收于两条均线之上，动能正在稳步改善，短线看多。"
CORRECTION_MARKER = "reply not in Simplified Chinese"


def _in_chinese(test):
    """Run ``test`` on a thread whose run speaks Simplified Chinese."""
    tracker = LlmUsageTracker(language="zh")
    with tracker.activate():
        return test()


class Replying:
    """A fake ``ask``: the first reply, then — when the prompt carries the
    language correction — the second; records every prompt."""

    def __init__(self, first, corrected=None):
        self.first = first
        self.corrected = corrected
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if CORRECTION_MARKER in prompt and self.corrected is not None:
            return self.corrected
        return self.first


class TestRunLanguage(unittest.TestCase):
    def test_no_active_run_speaks_the_default(self):
        self.assertEqual(run_language(), "en")
        self.assertIn("English", language_rule())

    def test_the_active_run_carries_its_language_to_every_prompt_builder(self):
        self.assertEqual(_in_chinese(run_language), "zh")
        self.assertIn("Simplified Chinese", _in_chinese(language_rule))


class TestInLanguage(unittest.TestCase):
    def test_a_reply_in_the_right_language_is_asked_once(self):
        ask = Replying(CHINESE)
        warnings = []
        result = _in_chinese(lambda: in_language(ask, "prompt", lambda t: [t], "stage", warnings))
        self.assertEqual(result, CHINESE)
        self.assertEqual(ask.prompts, ["prompt"])
        self.assertEqual(warnings, [])

    def test_a_wrong_language_reply_goes_back_with_a_correction(self):
        ask = Replying(ENGLISH, corrected=CHINESE)
        warnings = []
        result = _in_chinese(lambda: in_language(ask, "prompt", lambda t: [t], "stage", warnings))
        self.assertEqual(result, CHINESE)
        self.assertEqual(len(ask.prompts), 2)
        # The retry keeps the whole prompt and names the problem and the language.
        self.assertTrue(ask.prompts[1].startswith("prompt"))
        self.assertIn(CORRECTION_MARKER, ask.prompts[1])
        self.assertIn("every sentence in Simplified Chinese", ask.prompts[1])
        self.assertEqual(warnings, ["stage needed a retry — reply not in Simplified Chinese"])

    def test_a_stubborn_reply_is_kept_as_written_after_the_retry_limit(self):
        ask = Replying(ENGLISH)
        warnings = []
        result = _in_chinese(lambda: in_language(ask, "prompt", lambda t: [t], "stage", warnings))
        self.assertEqual(result, ENGLISH)
        self.assertEqual(len(ask.prompts), 1 + LANGUAGE_RETRY_LIMIT)
        self.assertEqual(LANGUAGE_RETRY_LIMIT, 2)
        self.assertEqual(
            warnings[-1],
            "stage reply not in Simplified Chinese after 2 retries — shown as written",
        )

    def test_a_retry_that_does_not_parse_keeps_the_earlier_reply(self):
        # The first reply parsed but spoke the wrong language; the retry
        # came back unparseable. A valid reply in the wrong language beats
        # no reply: the stage keeps it, with the "shown as written" warning,
        # instead of reporting "produced no outlook" (review 2026-10-10).
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            return None if CORRECTION_MARKER in prompt else ENGLISH

        warnings = []
        result = _in_chinese(lambda: in_language(ask, "prompt", lambda t: [t], "stage", warnings))
        self.assertEqual(result, ENGLISH)
        self.assertEqual(len(prompts), 2)
        self.assertEqual(warnings, [
            "stage needed a retry — reply not in Simplified Chinese",
            "stage reply not in Simplified Chinese after 1 retry — shown as written",
        ])

    def test_an_unparsed_reply_ends_the_loop_with_nothing_to_check(self):
        ask = Replying(None)
        warnings = []
        result = _in_chinese(lambda: in_language(ask, "prompt", lambda t: [t], "stage", warnings))
        self.assertIsNone(result)
        self.assertEqual(len(ask.prompts), 1)
        self.assertEqual(warnings, [])

    def test_an_english_run_accepts_english_without_a_retry(self):
        ask = Replying(ENGLISH)
        warnings = []
        result = in_language(ask, "prompt", lambda t: [t], "stage", warnings)
        self.assertEqual(result, ENGLISH)
        self.assertEqual(len(ask.prompts), 1)
        self.assertEqual(warnings, [])


def _dims():
    return [DataReport(name="technicals", kind=SourceKind.NUMERIC, payload={"rsi_14": 56.28})]


def _preliminary_reply(summary):
    return json.dumps({"score": 7, "summary": summary})


class TestPreliminaryAnalysisLanguage(unittest.TestCase):
    def _run(self, summarizer):
        return _in_chinese(
            lambda: PreliminaryAnalysis(summarizer=summarizer).run("AAPL", _dims(), max_hold_weeks=2)
        )

    def test_the_prompt_names_the_run_language(self):
        summarizer = Replying(_preliminary_reply(CHINESE))
        self._run(summarizer)
        self.assertIn("Simplified Chinese", summarizer.prompts[0])

    def test_a_chinese_summary_passes_first_time(self):
        summarizer = Replying(_preliminary_reply(CHINESE))
        result = self._run(summarizer)
        self.assertEqual(result.outlook.summary, CHINESE)
        self.assertEqual(len(summarizer.prompts), 1)
        self.assertEqual(result.warnings, [])

    def test_an_english_summary_is_asked_again_in_chinese(self):
        summarizer = Replying(_preliminary_reply(ENGLISH), corrected=_preliminary_reply(CHINESE))
        result = self._run(summarizer)
        self.assertEqual(result.outlook.summary, CHINESE)
        self.assertEqual(len(summarizer.prompts), 2)
        self.assertIn("preliminary analysis needed a retry — reply not in Simplified Chinese", result.warnings)

    def test_a_stubborn_english_summary_is_kept_with_a_warning(self):
        summarizer = Replying(_preliminary_reply(ENGLISH))
        result = self._run(summarizer)
        self.assertEqual(result.outlook.summary, ENGLISH)
        self.assertEqual(len(summarizer.prompts), 3)
        self.assertIn(
            "preliminary analysis reply not in Simplified Chinese after 2 retries — shown as written",
            result.warnings,
        )


def _entries():
    return [
        {"title": "Alphabet sells bonds", "publisher": "Reuters", "url": "https://example.com/a",
         "date": "2026-08-07", "summary": "Second major debt sale this year."},
        {"title": "Micron outlook improves", "publisher": "Zacks", "url": "https://example.com/b",
         "date": "2026-08-12", "summary": "Chipmakers sell to hyperscalers."},
    ]


def _summaries_reply(*texts):
    return json.dumps({"summaries": [[index + 1, text] for index, text in enumerate(texts)]})


ENGLISH_CARDS = (
    "Alphabet raised money in its second large bond sale of the year.",
    "Micron's outlook improved on demand from the big cloud buyers.",
)
CHINESE_CARDS = (
    "谷歌母公司今年第二次大规模发债筹集资金。",
    "美光因大型云服务商的需求而改善了业绩展望。",
)


class TestNewsSummaryLanguage(unittest.TestCase):
    def _run(self, summarizer):
        return _in_chinese(lambda: llm_summarize_articles("GOOGL", _entries(), summarize=summarizer))

    def test_the_prompt_asks_for_sentences_in_the_run_language(self):
        summarizer = Replying(_summaries_reply(*CHINESE_CARDS))
        self._run(summarizer)
        self.assertIn("Simplified Chinese", summarizer.prompts[0])

    def test_chinese_card_sentences_pass_first_time(self):
        summarizer = Replying(_summaries_reply(*CHINESE_CARDS))
        result = self._run(summarizer)
        self.assertEqual(result["summaries"], list(CHINESE_CARDS))
        self.assertEqual(len(summarizer.prompts), 1)
        self.assertEqual(result["warnings"], [])

    def test_english_card_sentences_are_asked_again_in_chinese(self):
        summarizer = Replying(
            _summaries_reply(*ENGLISH_CARDS), corrected=_summaries_reply(*CHINESE_CARDS)
        )
        result = self._run(summarizer)
        self.assertEqual(result["summaries"], list(CHINESE_CARDS))
        self.assertEqual(len(summarizer.prompts), 2)
        self.assertIn("news summary needed a retry — reply not in Simplified Chinese", result["warnings"])

    def test_stubborn_english_cards_are_kept_with_a_warning(self):
        summarizer = Replying(_summaries_reply(*ENGLISH_CARDS))
        result = self._run(summarizer)
        self.assertEqual(result["summaries"], list(ENGLISH_CARDS))
        self.assertEqual(len(summarizer.prompts), 3)
        self.assertIn(
            "news summary reply not in Simplified Chinese after 2 retries — shown as written",
            result["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
