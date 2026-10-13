# -*- coding: utf-8 -*-
"""Offline tests for the chat context limit and its measurement
(src/chat/context.py): where the max comes from, how a request is
sized, and how the characters-per-token ratio is learned."""
from __future__ import annotations

import pytest

from src.chat import context
from src.chat.context import (
    COMPACT_AT_PERCENT,
    CONTEXT_WINDOW_ENV,
    DEFAULT_CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    ContextLimit,
    chars_per_token,
    context_limit,
    env_window,
    measure,
)
from src.chat.transcript import render_prompt


@pytest.fixture()
def table(monkeypatch):
    """litellm's model table, scripted: {model: (window, output limit)}."""
    rows = {}
    context.litellm_limits.cache_clear()
    monkeypatch.setattr(context, "litellm_limits", lambda llm: rows.get(llm))
    return rows


class TestContextLimit:
    def test_a_known_model_gets_its_window_minus_its_output_limit(self, table):
        table["gemini/gemini-3.8-flash"] = (1_048_576, 65_536)
        limit = context_limit("gemini/gemini-3.8-flash")
        assert (limit.window, limit.output_limit, limit.max_tokens, limit.source) == (1_048_576, 65_536, 983_040, "litellm")
        assert limit.compact_at == 983_040 * COMPACT_AT_PERCENT // 100

    def test_a_known_model_whose_output_limit_fills_the_window_is_halved(self, table):
        # A local model often reports output == window; the subtraction would leave nothing.
        table["ollama/llama3"] = (8192, 8192)
        assert context_limit("ollama/llama3").max_tokens == 4096
        table["x/no-output-limit"] = (100_000, None)
        assert context_limit("x/no-output-limit").max_tokens == 50_000

    def test_an_unknown_model_gets_half_the_env_window(self, table, monkeypatch):
        monkeypatch.setenv(CONTEXT_WINDOW_ENV, "32000")
        limit = context_limit("openrouter/some/alias")
        assert (limit.window, limit.output_limit, limit.max_tokens, limit.source) == (32_000, None, 16_000, "env")
        # No model at all: the same fallback.
        assert context_limit(None).max_tokens == 16_000

    def test_the_env_window_defaults_when_unset_blank_or_bad(self, monkeypatch):
        monkeypatch.delenv(CONTEXT_WINDOW_ENV, raising=False)
        assert env_window() == DEFAULT_CONTEXT_WINDOW
        monkeypatch.setenv(CONTEXT_WINDOW_ENV, "  ")
        assert env_window() == DEFAULT_CONTEXT_WINDOW
        monkeypatch.setenv(CONTEXT_WINDOW_ENV, "lots")
        assert env_window() == DEFAULT_CONTEXT_WINDOW
        monkeypatch.setenv(CONTEXT_WINDOW_ENV, "-5")
        assert env_window() == DEFAULT_CONTEXT_WINDOW
        monkeypatch.setenv(CONTEXT_WINDOW_ENV, "200000")
        assert env_window() == 200_000

    def test_the_real_table_knows_a_hosted_model_and_not_a_made_up_one(self):
        context.litellm_limits.cache_clear()
        assert context.litellm_limits("gemini/gemini-3.8-flash") is not None
        assert context.litellm_limits("nonsense/not-a-model") is None


class TestCharsPerToken:
    def test_measured_from_the_newest_reply_with_a_receipt_and_its_text(self):
        rows = [
            {"role": "assistant", "usage": {"input_tokens": 100}, "transcript": {"input": "x" * 300}},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "usage": {"input_tokens": 50}, "transcript": {"input": "y" * 250}},
            {"role": "tool", "content": "{}"},
        ]
        assert chars_per_token(rows) == (5.0, True)

    def test_assumed_without_a_usable_receipt(self):
        assert chars_per_token([]) == (DEFAULT_CHARS_PER_TOKEN, False)
        assert chars_per_token([{"role": "assistant", "transcript": {"input": "xxxx"}}]) == (DEFAULT_CHARS_PER_TOKEN, False)
        assert chars_per_token([{"role": "assistant", "usage": {"input_tokens": 0}, "transcript": {"input": "xx"}}]) == (DEFAULT_CHARS_PER_TOKEN, False)
        # A ratio no tokenizer produces is a broken receipt, skipped.
        rows = [
            {"role": "assistant", "usage": {"input_tokens": 100}, "transcript": {"input": "x" * 300}},
            {"role": "assistant", "usage": {"input_tokens": 1}, "transcript": {"input": "y" * 5000}},
        ]
        assert chars_per_token(rows) == (3.0, True)


class TestMeasure:
    LIMIT = ContextLimit(llm="fake", window=1000, output_limit=200, max_tokens=800, source="litellm")

    def test_parts_add_up_to_the_rendered_request(self):
        messages = [
            {"role": "system", "content": "s" * 400},
            {"role": "user", "content": "u" * 100},
            {"role": "assistant", "content": "a" * 100},
        ]
        tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
        usage = measure(self.LIMIT, messages, tools, ratio=2.0, calibrated=True)
        total_chars = len(render_prompt(messages, tools))
        assert usage.used_tokens == pytest.approx(total_chars / 2.0, abs=2)
        assert usage.system_prompt_tokens > 200
        assert usage.tools_tokens > 0
        assert usage.conversation_tokens > 100
        assert usage.chars_per_token == 2.0 and usage.calibrated is True
        assert usage.percent == round(usage.used_tokens * 100 / 800)

    def test_needs_compaction_past_the_line(self):
        small = ContextLimit(llm="fake", window=200, output_limit=100, max_tokens=100, source="litellm")
        light = measure(small, [{"role": "system", "content": "s" * 40}], [], ratio=4.0)
        assert light.needs_compaction is False
        heavy = measure(small, [{"role": "system", "content": "s" * 400}], [], ratio=4.0)
        assert heavy.needs_compaction is True
        assert heavy.view()["compact_at_tokens"] == 85

    def test_the_view_names_every_fact_the_page_shows(self):
        view = measure(self.LIMIT, [{"role": "system", "content": "sys"}], []).view()
        assert set(view) == {
            "llm", "source", "window", "output_limit", "max_tokens", "used_tokens", "percent",
            "compact_at_tokens", "compact_at_percent", "chars_per_token", "calibrated",
            "system_prompt_tokens", "tools_tokens", "conversation_tokens",
        }
        assert view["compact_at_percent"] == COMPACT_AT_PERCENT
        assert view["chars_per_token"] == DEFAULT_CHARS_PER_TOKEN and view["calibrated"] is False
