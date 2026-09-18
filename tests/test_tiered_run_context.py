# -*- coding: utf-8 -*-
"""Offline tests for the LLM and data-key configuration readers
(src/tiered_analysis/run_context.py): everything comes from the
environment, blanks read as None, and litellm gets the model plus the
one provider-agnostic key (LLM_API_KEY) — or no key at all when it is
unset, so litellm reads the provider's own variable itself."""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from src.tiered_analysis.llm_support import default_summarizer, screen_summarizer
from src.tiered_analysis.run_context import (
    data_key,
    llm_api_key,
    llm_model,
    llm_sub_model,
)


class _FakeLitellm:
    def __init__(self):
        self.calls = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )


class TestEnvironmentReaders(unittest.TestCase):
    def test_everything_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"MAIN_LLM": "env/model",
                                          "SUB_LLM": "env/screen",
                                          "LLM_API_KEY": "env-key",
                                          "FRED_API_KEY": "env-fred"}, clear=False):
            self.assertEqual(llm_model(), "env/model")
            self.assertEqual(llm_sub_model(), "env/screen")
            self.assertEqual(llm_api_key(), "env-key")
            self.assertEqual(data_key("fred"), "env-fred")

    def test_missing_values_are_none_not_empty_strings(self):
        with mock.patch.dict(os.environ, {"MAIN_LLM": "  ", "LLM_API_KEY": " ",
                                          "FINNHUB_API_KEY": ""}):
            self.assertIsNone(llm_model())
            self.assertIsNone(llm_api_key())
            self.assertIsNone(data_key("finnhub"))

    def test_screening_falls_back_to_the_main_model(self):
        with mock.patch.dict(os.environ, {"MAIN_LLM": "env/model",
                                          "SUB_LLM": ""}):
            self.assertEqual(llm_sub_model(), "env/model")

    def test_unknown_data_key_name_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            data_key("bloomberg")


class TestSummarizers(unittest.TestCase):
    def test_litellm_gets_the_model_and_the_generic_key(self):
        fake = _FakeLitellm()
        with mock.patch.dict(sys.modules, {"litellm": fake}):
            with mock.patch.dict(os.environ, {"MAIN_LLM": "env/model",
                                              "SUB_LLM": "env/screen",
                                              "LLM_API_KEY": "env-key"}):
                default_summarizer("p")
                screen_summarizer("q")
        self.assertEqual(fake.calls[0]["model"], "env/model")
        self.assertEqual(fake.calls[0]["api_key"], "env-key")
        self.assertEqual(fake.calls[1]["model"], "env/screen")
        self.assertEqual(fake.calls[1]["api_key"], "env-key")

    def test_no_generic_key_means_litellm_reads_the_providers_own(self):
        fake = _FakeLitellm()
        with mock.patch.dict(sys.modules, {"litellm": fake}):
            with mock.patch.dict(os.environ, {"MAIN_LLM": "env/model",
                                              "LLM_API_KEY": ""}):
                default_summarizer("p")
        self.assertNotIn("api_key", fake.calls[0])


if __name__ == "__main__":
    unittest.main()
