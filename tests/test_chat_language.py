# -*- coding: utf-8 -*-
"""The app's language table and check (src/languages.py): which texts
count as written in the chosen language, and the chat bot's retry limit
(src/chat/language.py)."""
from __future__ import annotations

from src.chat.language import LANGUAGE_RETRY_LIMIT
from src.languages import (
    LANGUAGES,
    correction_message,
    detect_language,
    is_supported,
    language_name,
    matches_language,
)


class TestMatchesLanguage:
    def test_a_chinese_reply_matches_chinese(self):
        assert matches_language("苹果最近一次一级分析的展望是看涨，评分 7.2。", "zh")

    def test_an_english_reply_does_not_match_chinese(self):
        assert not matches_language("The latest tier-1 run on AAPL is bullish with a score of 7.2.", "zh")

    def test_a_chinese_reply_does_not_match_english(self):
        assert not matches_language("苹果最近一次一级分析的展望是看涨，评分 7.2。", "en")

    def test_tickers_run_ids_and_field_names_do_not_tip_a_chinese_reply(self):
        reply = (
            "AAPL 的一级分析（2026-09-24）展望为 bullish，评分 7.2。"
            "run_id: 3f2a9c1d-7b4e-4c8a-9d1f-0a2b3c4d5e6f。"
            "600519 和 7203.T 的运行还在排队。"
        )
        assert matches_language(reply, "zh")

    def test_a_chinese_company_name_does_not_tip_an_english_reply(self):
        reply = "The run on 600519 (贵州茅台) finished with a neutral outlook and a score of 5.1."
        assert matches_language(reply, "en")

    def test_code_spans_and_urls_are_ignored(self):
        reply = "见 `list_runs` 的结果和 https://example.com/some/english/path/here 。运行已经完成。"
        assert matches_language(reply, "zh")

    def test_too_little_text_passes(self):
        assert matches_language("OK.", "zh")
        assert matches_language("好。", "en")
        assert matches_language(None, "zh")
        assert matches_language("", "en")

    def test_an_unknown_language_passes(self):
        assert matches_language("anything at all, in any script", "fr")

    def test_a_mostly_chinese_reply_full_of_field_names_still_matches_chinese(self):
        reply = "这个 run 的 technicals 报告显示 RSI 偏高，fundamentals 正常，company_news 没有大新闻，action 是 buy_now。"
        assert matches_language(reply, "zh")

    def test_a_long_english_summary_matches_english(self):
        reply = (
            "Outlook: bullish. The stock closed above its 50-day and 200-day averages, and the last two "
            "earnings beat estimates. Against it, the RSI is stretched near 74 and insiders sold shares in "
            "the last month. Over a hold of up to two weeks the trend evidence outweighs the overbought reading."
        )
        assert matches_language(reply, "en")

    def test_detect_reports_the_code_and_the_letters_judged(self):
        code, letters = detect_language("苹果最近一次分析的展望是看涨，评分 7.2，值得继续关注后续走势。")
        assert code == "zh" and letters >= 15
        code, letters = detect_language("OK.")
        assert code is None and letters == 2

    def test_the_same_text_always_gets_the_same_answer(self):
        text = "The latest tier-1 run on AAPL is bullish with a score of 7.2 out of 10."
        assert len({detect_language(text) for _ in range(20)}) == 1


class TestLanguageTable:
    def test_the_offered_languages(self):
        assert set(LANGUAGES) == {"en", "zh"}
        assert is_supported("zh") and not is_supported("fr") and not is_supported(None)


class TestPromptWords:
    def test_language_names(self):
        assert language_name("zh") == "Simplified Chinese"
        assert language_name("en") == "English"
        assert language_name("??") == "English"

    def test_correction_names_the_language(self):
        line = correction_message("zh")
        assert "Simplified Chinese" in line
        assert "tickers" in line

    def test_retry_limit_is_the_agreed_one(self):
        assert LANGUAGE_RETRY_LIMIT == 2
