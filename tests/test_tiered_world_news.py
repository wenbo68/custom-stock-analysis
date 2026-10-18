# -*- coding: utf-8 -*-
"""Offline tests for the world-news provider (the macro/world backdrop
card): payload shape and date span, evidence hygiene, the shared
per-day cache, the world prompt set, and the debate's news-row
enumeration picking the card up by TEXTUAL kind.

No network, no LLM: the loader and screener are injected fakes; the
screen's own behavior is covered by test_tiered_news_screen.py.
"""
from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest import mock

from src.tiered_analysis.cache_store import MemoryCacheStore
from src.tiered_analysis.deep_analysis import gradable_field_refs
from src.tiered_analysis.news_screen import (
    COMPANY_PROMPTS,
    WORLD_PROMPTS,
    build_judge_prompt,
    judge_news_cached,
)
from src.tiered_analysis.providers.base import (
    DataReport,
    Market,
    SourceKind,
)
from src.tiered_analysis.providers import world_news
from src.tiered_analysis.providers.world_news import (
    WorldNewsProvider,
    normalize_google_news_item,
    parse_google_news_rss,
)

TODAY = date(2026, 8, 16)


def passthrough_screener(entries):
    """Every entry becomes its own selected event, screen counters zero
    (the real screen's behavior is covered elsewhere)."""
    return {
        "selected": [
            {
                "entry": entry,
                "materiality": 5,
                "group_size": 1,
                "card_text": None,
            }
            for entry in entries
        ],
        "mention_only": 0,
        "below_threshold": 0,
        "trimmed": 0,
        "warnings": [],
        "judgments": [],
        "from_cache": 0,
        "judged": len(entries),
    }


def news_fixture():
    return [
        {
            "title": "Fed holds rates, signals cut",
            "publisher": "Reuters",
            "url": "https://example.com/fed-hold",
            "date": "2026-08-16",
            "summary": "The central bank held rates steady and signaled a cut.",
        },
        {
            "title": "Oil jumps on supply fears",
            "publisher": "Bloomberg",
            "url": "https://example.com/oil-jump",
            "date": "2026-08-15",
            "summary": None,  # headline is the fallback bullet text
        },
        {  # no link — unverifiable, must be dropped with a warning
            "title": "No link story",
            "publisher": "Somewhere",
            "url": None,
            "date": "2026-08-15",
            "summary": None,
        },
        {  # duplicate URL — same story syndicated twice, one bullet
            "title": "Fed holds rates, signals cut (syndicated)",
            "publisher": "Elsewhere",
            "url": "https://example.com/fed-hold",
            "date": "2026-08-16",
            "summary": None,
        },
    ]


class TestWorldNewsProvider(unittest.TestCase):
    def setUp(self):
        self.cache = MemoryCacheStore()

    def make_provider(self, news=None, loader=None, today=lambda: TODAY):
        calls = []

        def default_loader():
            calls.append(1)
            return news if news is not None else news_fixture()

        provider = WorldNewsProvider(
            news_loader=loader or default_loader,
            today=today,
            screener=passthrough_screener,
            cache=self.cache,
        )
        return provider, calls

    def test_supports_every_market(self):
        provider, _ = self.make_provider()
        for market in (Market.US, Market.CN, Market.HK, Market.UNKNOWN):
            self.assertTrue(provider.supports(market))

    def test_payload_shape_span_and_citation_alignment(self):
        provider, _ = self.make_provider()
        result = provider.collect("AAPL")
        self.assertEqual(result.name, "world_news")
        self.assertEqual(result.kind, SourceKind.TEXTUAL)
        self.assertIsNotNone(result.payload)  # no card-level grade anymore
        news = result.payload["news_coverage"]
        # The honest horizon: the actual span fetched, no window promise.
        self.assertEqual(news["oldest"], "2026-08-15")
        self.assertEqual(news["newest"], "2026-08-16")
        self.assertNotIn("window_days", news)
        self.assertEqual(news["score_bar"], 4)
        # Newest first; the no-summary item falls back to its headline.
        self.assertEqual(
            [item["text"] for item in news["items"]],
            [
                "The central bank held rates steady and signaled a cut.",
                "Oil jumps on supply fears",
            ],
        )
        self.assertEqual(
            [item["importance"] for item in news["items"]], [5, 5]
        )
        # Citations align 1-based with the bullets.
        for item in news["items"]:
            citation = result.citations[item["citation"] - 1]
            self.assertEqual(citation.url is not None, True)
        # The linkless item was dropped, loudly.
        self.assertTrue(any("skipped" in warning for warning in result.warnings))

    def test_loader_failure_with_empty_pool_ships_empty_timeline_not_cached(self):
        # Degradation lives on the card notes now, never on a card-level
        # grade: fetch failed AND nothing pooled still ships the card's
        # payload shape — an empty timeline (no dates to bound it) with
        # the warnings saying why.
        def failing_loader():
            failing_loader.calls += 1
            raise RuntimeError("every world feed failed")

        failing_loader.calls = 0
        provider, _ = self.make_provider(loader=failing_loader)
        result = provider.collect("AAPL")
        self.assertEqual(
            result.payload,
            {
                "news_coverage": {
                    "oldest": None,
                    "newest": None,
                    "filtered_out": 0,
                    "off_topic": 0,
                    "below_bar": 0,
                    "score_bar": 4,
                    "items": [],
                }
            },
        )
        self.assertTrue(
            any("world news fetch failed" in w for w in result.warnings),
            result.warnings,
        )
        self.assertTrue(
            any("no pooled articles" in w for w in result.warnings),
            result.warnings,
        )
        # A failure must not persist as the day's answer.
        provider.collect("MSFT")
        self.assertEqual(failing_loader.calls, 2)

    def test_loader_failure_falls_back_to_the_pool_warned_not_cached(self):
        # Day 1 fills the pool; day 2's feed is down.
        provider, _ = self.make_provider()
        provider.collect("AAPL")

        def failing_loader():
            failing_loader.calls += 1
            raise RuntimeError("boom")

        failing_loader.calls = 0
        tomorrow, _ = self.make_provider(
            loader=failing_loader, today=lambda: date(2026, 8, 17)
        )
        result = tomorrow.collect("AAPL")
        # The pooled articles inside the later run's 2-day window
        # (08-16..17) still make the card, loudly warned (the warning is
        # the degradation signal now — no card-level grade); the 08-15
        # article ages out.
        self.assertEqual(len(result.payload["news_coverage"]["items"]), 1)
        self.assertTrue(
            any("world news fetch failed" in warning for warning in result.warnings)
        )
        self.assertTrue(
            any("previously fetched" in warning for warning in result.warnings)
        )
        # A degraded card is never the day's cached answer — the next
        # run the same day retries the feed.
        tomorrow.collect("MSFT")
        self.assertEqual(failing_loader.calls, 2)

    def test_pool_accumulates_across_days_beyond_one_fetch(self):
        provider, _ = self.make_provider()
        provider.collect("AAPL")

        extra = [
            {
                "title": "ECB cuts rates",
                "publisher": "FT",
                "url": "https://example.com/ecb-cut",
                "date": "2026-08-17",
                "summary": "The ECB cut its policy rate.",
            }
        ]
        tomorrow, _ = self.make_provider(
            news=extra, today=lambda: date(2026, 8, 17)
        )
        result = tomorrow.collect("AAPL")
        news = result.payload["news_coverage"]
        # The later run's single-article fetch screens WITH the earlier
        # pooled articles that are still inside the 2-day window
        # (08-16..17); the 08-15 article ages out of it.
        self.assertEqual(
            [item["text"] for item in news["items"]],
            [
                "The ECB cut its policy rate.",
                "The central bank held rates steady and signaled a cut.",
            ],
        )
        self.assertEqual(news["oldest"], "2026-08-16")
        self.assertEqual(news["newest"], "2026-08-17")

    def test_pool_prunes_past_retention(self):
        stale = [
            {
                "title": "Ancient story",
                "publisher": "Wire",
                "url": "https://example.com/ancient",
                "date": "2026-07-01",  # far past ARTICLE_RETENTION_DAYS
                "summary": None,
            }
        ] + news_fixture()
        provider, _ = self.make_provider(news=stale)
        result = provider.collect("AAPL")
        texts = [i["text"] for i in result.payload["news_coverage"]["items"]]
        self.assertNotIn("Ancient story", texts)

    def test_screen_reads_only_the_calendar_day_window(self):
        # TODAY is 2026-08-16: the 2-calendar-day window starts
        # 2026-08-15. An article inside the pool's retention but before
        # that boundary stays pooled (failure-fallback tier) yet never
        # reaches the screen or the card.
        aged = [
            {
                "title": "Pre-window story",
                "publisher": "Wire",
                "url": "https://example.com/pre-window",
                "date": "2026-08-13",
                "summary": None,
            }
        ] + news_fixture()
        provider, _ = self.make_provider(news=aged)
        result = provider.collect("AAPL")
        news = result.payload["news_coverage"]
        self.assertNotIn(
            "Pre-window story", [item["text"] for item in news["items"]]
        )
        self.assertEqual(news["oldest"], "2026-08-15")
        # Still pooled for the fetch-failure fallback path.
        pool_key = next(k for k in self.cache.keys() if k.startswith("world_articles_"))
        self.assertIn("pre-window", self.cache.data[pool_key])

    def test_screen_cap_spreads_across_days_instead_of_newest_first(self):
        # Six articles over two days with a cap of 4: a newest-first
        # cut would take all of day 2 and starve day 1; the day-spread
        # keeps both days represented (2 + 2), and the trim is warned.
        crowd = [
            {
                "title": f"Story {day} {index}",
                "publisher": "Wire",
                "url": f"https://example.com/{day}-{index}",
                "date": f"2026-08-{day}",
                "summary": None,
            }
            for day in (16, 15)
            for index in range(3)
        ]
        with mock.patch.object(world_news, "MAX_SCREEN_ARTICLES", 4):
            provider, _ = self.make_provider(news=crowd)
            result = provider.collect("AAPL")
        news = result.payload["news_coverage"]
        dates = [item["date"] for item in news["items"]]
        self.assertEqual(dates.count("2026-08-16"), 2)
        self.assertEqual(dates.count("2026-08-15"), 2)
        self.assertEqual(news["oldest"], "2026-08-15")
        self.assertTrue(
            any("busy world window" in warning for warning in result.warnings)
        )

    def test_degraded_loader_tuple_is_warned_and_not_day_cached(self):
        # The default loader signals "primary feed down, backup used"
        # by returning (entries, warnings): the card still fills, the
        # loader's warning rides along (the only degradation signal —
        # no card-level grade), and it is never day-cached — the same
        # day's next run retries the primary feed.
        def degraded_loader():
            degraded_loader.calls += 1
            return (
                news_fixture(),
                ["world news: Google News failed (boom); used the Yahoo"
                 " backup feed"],
            )

        degraded_loader.calls = 0
        provider, _ = self.make_provider(loader=degraded_loader)
        result = provider.collect("AAPL")
        self.assertEqual(len(result.payload["news_coverage"]["items"]), 2)
        self.assertTrue(
            any("Google News failed" in warning for warning in result.warnings)
        )
        provider.collect("MSFT")
        self.assertEqual(degraded_loader.calls, 2)

    def test_empty_feed_is_warned_and_not_day_cached(self):
        # A feed that answers with zero articles is not a news-free day
        # (observed 2026-10-18: both feeds silently empty): the card is
        # warned, and the blank is never day-cached — the same day's
        # next run fetches again.
        def empty_loader():
            empty_loader.calls += 1
            return []

        empty_loader.calls = 0
        provider, _ = self.make_provider(loader=empty_loader)
        result = provider.collect("AAPL")
        self.assertEqual(result.payload["news_coverage"]["items"], [])
        self.assertIn(
            "world news: the feed returned no articles", result.warnings
        )
        provider.collect("MSFT")
        self.assertEqual(empty_loader.calls, 2)

    def test_day_cache_shares_one_screen_across_symbols(self):
        provider, calls = self.make_provider()
        first = provider.collect("AAPL")
        second = provider.collect("MSFT")  # same day: served from disk
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.payload, first.payload)
        self.assertEqual(
            [(c.source_name, c.url, c.title) for c in second.citations],
            [(c.source_name, c.url, c.title) for c in first.citations],
        )
        # A fresh provider instance (new run, same day) also hits it.
        fresh, fresh_calls = self.make_provider()
        fresh.collect("NVDA")
        self.assertEqual(len(fresh_calls), 0)

    def test_next_day_refetches(self):
        provider, calls = self.make_provider()
        provider.collect("AAPL")
        tomorrow, tomorrow_calls = self.make_provider(
            today=lambda: date(2026, 8, 17)
        )
        tomorrow.collect("AAPL")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(tomorrow_calls), 1)


class TestSpamPrefilter(unittest.TestCase):
    """The deterministic blacklist (owner request 2026-08-19): the
    auto-generated fund-holdings genre never reaches — or pays for —
    the LLM judge. A blacklist only drops recognizable spam; real macro
    stories must always pass."""

    def test_blacklisted_publisher_is_spam_case_insensitive(self):
        for publisher in ("MarketBeat", "marketbeat", " MARKETBEAT "):
            self.assertTrue(
                world_news.is_world_spam(
                    {"title": "Any headline at all", "publisher": publisher}
                ),
                publisher,
            )

    def test_holdings_title_templates_are_spam_from_any_outlet(self):
        titles = [
            "Example Capital Management Trims Stake in Microsoft Co.",
            "Hedgeco LLC Buys 12,345 Shares of Apple Inc.",
            "Shares Sold by Example Advisors: Tesla Inc. (NASDAQ:TSLA)",
            "Example Fund Takes $1.2 Million Position in Nvidia",
            "Vanguard Group Inc. Boosts Stock Position in Amazon.com",
        ]
        for title in titles:
            self.assertTrue(
                world_news.is_world_spam(
                    {"title": title, "publisher": "Whatever Wire"}
                ),
                title,
            )

    def test_real_macro_headlines_pass(self):
        titles = [
            "Fed holds rates, signals September cut",
            "Oil jumps as OPEC trims supply outlook",
            "China raises tariffs on US goods in trade escalation",
            "Jobs report surprises with 350,000 new positions",
        ]
        for title in titles:
            self.assertFalse(
                world_news.is_world_spam(
                    {"title": title, "publisher": "Reuters"}
                ),
                title,
            )

    def test_missing_fields_are_not_spam(self):
        self.assertFalse(world_news.is_world_spam({}))
        self.assertFalse(
            world_news.is_world_spam({"title": None, "publisher": None})
        )

    def test_spam_is_cut_before_the_screen_and_counted(self):
        seen = []

        def recording_screener(entries):
            seen.extend(entries)
            return passthrough_screener(entries)

        spam_title = {
            "title": "Example Capital Trims Stake in Apple Inc.",
            "publisher": "Whatever Wire",
            "url": "https://example.com/spam-title",
            "date": "2026-08-16",
            "summary": None,
        }
        spam_publisher = {
            "title": "Institutional flows update",
            "publisher": "MarketBeat",
            "url": "https://example.com/spam-publisher",
            "date": "2026-08-16",
            "summary": None,
        }
        provider = WorldNewsProvider(
            news_loader=lambda: news_fixture() + [spam_title, spam_publisher],
            today=lambda: TODAY,
            screener=recording_screener,
            cache=MemoryCacheStore(),
        )
        result = provider.collect("AAPL")
        urls = [entry["url"] for entry in seen]
        self.assertNotIn("https://example.com/spam-title", urls)
        self.assertNotIn("https://example.com/spam-publisher", urls)
        self.assertIn("https://example.com/fed-hold", urls)
        news = result.payload["news_coverage"]
        # The deterministic cut is counted separately from the judge's
        # own off-topic cut — never silent, never conflated.
        self.assertEqual(news["filtered_out"], 2)
        self.assertEqual(news["off_topic"], 0)
        # No spam bullet made the card.
        self.assertEqual(len(news["items"]), 2)


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>"federal reserve" - Google News</title>
<item>
<title>Fed holds rates, signals cut - Reuters</title>
<link>https://news.google.com/rss/articles/AAA?oc=5</link>
<guid isPermaLink="false">AAA</guid>
<pubDate>Sun, 18 Oct 2026 11:33:03 GMT</pubDate>
<description>&lt;a href="https://news.google.com/rss/articles/AAA?oc=5"&gt;Fed holds rates, signals cut&lt;/a&gt;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Reuters&lt;/font&gt;</description>
<source url="https://www.reuters.com">Reuters</source>
</item>
<item>
<title>Oil jumps on supply fears - Bloomberg</title>
<link>https://news.google.com/rss/articles/BBB?oc=5</link>
<pubDate>Sat, 17 Oct 2026 23:58:03 GMT</pubDate>
<source url="https://www.bloomberg.com">Bloomberg</source>
</item>
</channel></rss>
"""


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestLoaderStack(unittest.TestCase):
    def test_parse_google_news_rss_reads_the_items(self):
        items = parse_google_news_rss(SAMPLE_RSS)
        self.assertEqual(
            items,
            [
                {
                    "title": "Fed holds rates, signals cut - Reuters",
                    "link": "https://news.google.com/rss/articles/AAA?oc=5",
                    "pubDate": "Sun, 18 Oct 2026 11:33:03 GMT",
                    "source": "Reuters",
                },
                {
                    "title": "Oil jumps on supply fears - Bloomberg",
                    "link": "https://news.google.com/rss/articles/BBB?oc=5",
                    "pubDate": "Sat, 17 Oct 2026 23:58:03 GMT",
                    "source": "Bloomberg",
                },
            ],
        )

    def test_parse_google_news_rss_rejects_non_rss_replies(self):
        # A block page or an error page is a failure (the backup feed
        # takes over), never an empty news day.
        with self.assertRaises(ValueError):
            parse_google_news_rss("<html><body>Sorry, blocked</body></html>")
        with self.assertRaises(ValueError):
            parse_google_news_rss("not xml at all <<<")

    def test_normalize_google_news_item_strips_the_publisher_suffix(self):
        # Google appends " - Publisher" to every headline; the entry's
        # title is the headline alone, the publisher its own field. The
        # feed carries no abstract, so summary stays None (the screen
        # judges the headline).
        entry = normalize_google_news_item(
            {
                "title": "Fed holds rates, signals cut - Reuters",
                "link": "https://news.google.com/rss/articles/AAA?oc=5",
                "pubDate": "Sun, 18 Oct 2026 11:33:03 GMT",
                "source": "Reuters",
            }
        )
        self.assertEqual(
            entry,
            {
                "title": "Fed holds rates, signals cut",
                "publisher": "Reuters",
                "url": "https://news.google.com/rss/articles/AAA?oc=5",
                "date": "2026-10-18",
                "summary": None,
            },
        )
        # A headline that does not end in its own publisher is kept whole.
        self.assertEqual(
            normalize_google_news_item(
                {"title": "Oil jumps - on supply fears", "source": "Bloomberg"}
            )["title"],
            "Oil jumps - on supply fears",
        )

    def test_normalize_google_news_item_dates_in_utc(self):
        # 23:58 in New York on the 17th is already the 18th in UTC: the
        # date is the UTC day, the same convention as the Yahoo entries.
        entry = normalize_google_news_item(
            {"title": "x", "pubDate": "Sat, 17 Oct 2026 23:58:03 -0400"}
        )
        self.assertEqual(entry["date"], "2026-10-18")

    def test_normalize_google_news_item_missing_fields_stay_none(self):
        self.assertEqual(
            normalize_google_news_item({}),
            {
                "title": None,
                "publisher": None,
                "url": None,
                "date": None,
                "summary": None,
            },
        )
        self.assertIsNone(
            normalize_google_news_item({"pubDate": "garbage"})["date"]
        )

    def test_google_loader_queries_every_lens_with_the_date_operator(self):
        calls = []

        def fake_get(url, params=None, timeout=None, headers=None):
            calls.append((url, dict(params or {})))
            return FakeResponse(SAMPLE_RSS)

        with mock.patch("requests.get", fake_get), mock.patch.object(
            world_news.time, "sleep"
        ) as sleep:
            entries = world_news._google_news_world_loader()
        # One request per lens, all against the English (US) edition.
        self.assertEqual(len(calls), len(world_news.WORLD_QUERIES))
        self.assertTrue(all(url == world_news.GOOGLE_NEWS_RSS_URL for url, _ in calls))
        since = date.today() - timedelta(days=world_news.WORLD_WINDOW_DAYS)
        for (_, params), query in zip(calls, world_news.WORLD_QUERIES):
            self.assertEqual(params["q"], f"{query} after:{since.isoformat()}")
            for key, value in world_news.GOOGLE_NEWS_EDITION.items():
                self.assertEqual(params[key], value)
        # Paced between requests, not before the first.
        self.assertEqual(sleep.call_count, len(world_news.WORLD_QUERIES) - 1)
        # The same two stories came back from every lens: merged by URL.
        self.assertEqual(
            sorted(entry["url"] for entry in entries),
            [
                "https://news.google.com/rss/articles/AAA?oc=5",
                "https://news.google.com/rss/articles/BBB?oc=5",
            ],
        )
        self.assertEqual(entries[0]["publisher"], "Reuters")

    def test_google_loader_fails_on_a_non_rss_reply(self):
        with mock.patch(
            "requests.get",
            return_value=FakeResponse("<html><body>blocked</body></html>"),
        ), mock.patch.object(world_news.time, "sleep"):
            with self.assertRaises(ValueError) as ctx:
                world_news._google_news_world_loader()
        self.assertIn("Google News", str(ctx.exception))

    def test_yahoo_loader_uses_the_news_search(self):
        # Yahoo's per-ticker news tab has returned nothing since
        # 2026-10-02 (every yfinance 1.x); the news SEARCH still answers.
        fake_search = mock.Mock()
        fake_search.return_value.news = [
            {
                "title": "Stocks slip as yields climb",
                "publisher": "Reuters",
                "link": "https://example.com/yields",
                "providerPublishTime": 1792324800,  # 2026-10-18 UTC
                "relatedTickers": ["^GSPC"],
            },
            "not a mapping",
        ]
        with mock.patch("yfinance.Search", fake_search):
            entries = world_news._yahoo_world_news_loader()
        fake_search.assert_called_once_with(
            world_news.YAHOO_WORLD_QUERY, news_count=world_news.NEWS_FETCH_COUNT
        )
        self.assertEqual(
            entries,
            [
                {
                    "title": "Stocks slip as yields climb",
                    "publisher": "Reuters",
                    "url": "https://example.com/yields",
                    "date": "2026-10-18",
                    "summary": None,
                }
            ],
        )

    def test_default_loader_prefers_google_news(self):
        with mock.patch.object(
            world_news, "_google_news_world_loader", return_value=["google"]
        ), mock.patch.object(
            world_news, "_yahoo_world_news_loader", return_value=["yahoo"]
        ):
            self.assertEqual(
                world_news._default_world_news_loader(), (["google"], [])
            )

    def test_default_loader_falls_back_to_yahoo_with_warning(self):
        with mock.patch.object(
            world_news,
            "_google_news_world_loader",
            side_effect=RuntimeError("HTTP 503"),
        ), mock.patch.object(
            world_news, "_yahoo_world_news_loader", return_value=["yahoo"]
        ):
            entries, warnings = world_news._default_world_news_loader()
        self.assertEqual(entries, ["yahoo"])
        self.assertEqual(
            warnings,
            ["world news: Google News failed (HTTP 503); used the Yahoo backup feed"],
        )

    def test_default_loader_raises_when_both_feeds_fail(self):
        with mock.patch.object(
            world_news,
            "_google_news_world_loader",
            side_effect=RuntimeError("HTTP 503"),
        ), mock.patch.object(
            world_news,
            "_yahoo_world_news_loader",
            side_effect=RuntimeError("yahoo down"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                world_news._default_world_news_loader()
        self.assertIn("HTTP 503", str(ctx.exception))
        self.assertIn("yahoo down", str(ctx.exception))


class TestWorldPromptSet(unittest.TestCase):
    def test_world_judge_prompt_swaps_the_lens(self):
        entries = [
            {
                "title": "Fed holds rates",
                "publisher": "Reuters",
                "url": "https://example.com/fed",
                "date": "2026-08-16",
                "summary": "Held steady.",
            }
        ]
        company = build_judge_prompt("AAPL", entries, prompts=COMPANY_PROMPTS)
        world = build_judge_prompt("ignored", entries, prompts=WORLD_PROMPTS)
        self.assertIn("about this company", company)
        self.assertIn("macro/world backdrop", world)
        self.assertIn("OVERALL stock market", world)
        # Article lines render identically under both lenses.
        self.assertIn("[1] (2026-08-16, Reuters)", world)

    def test_judge_parses_world_judgments_through_the_shared_parser(self):
        prompts_seen = []

        def fake_llm(prompt):
            prompts_seen.append(prompt)
            return '{"articles": [[1, 1, 5], [2, 0, 0]]}'

        entries = [
            {
                "title": "Fed holds rates",
                "url": "https://example.com/fed",
                "date": "2026-08-16",
            },
            {
                "title": "Celebrity gossip",
                "url": "https://example.com/gossip",
                "date": "2026-08-16",
            },
        ]
        outcome = judge_news_cached(
            "ignored", entries, summarize=fake_llm, prompts=WORLD_PROMPTS
        )
        self.assertIn("macro/world backdrop", prompts_seen[0])
        self.assertEqual(outcome["judgments"][0]["about_company"], True)
        self.assertEqual(outcome["judgments"][0]["materiality"], 5)
        self.assertEqual(outcome["judgments"][1]["about_company"], False)


class TestDebateEnumeration(unittest.TestCase):
    def test_world_news_rows_enumerate_by_textual_kind(self):
        world = DataReport(
            name="world_news",
            kind=SourceKind.TEXTUAL,
            payload={
                "news_coverage": {
                    "oldest": "2026-08-14",
                    "newest": "2026-08-16",
                    "items": [
                        {"text": "Fed held rates.", "citation": 1},
                        {"text": "Oil jumped.", "citation": 2},
                    ],
                }
            },
        )
        refs = gradable_field_refs([world])
        self.assertEqual(
            refs["world_news"],
            [
                "world_news.news_coverage.items.0.text",
                "world_news.news_coverage.items.1.text",
            ],
        )


if __name__ == "__main__":
    unittest.main()


class TestColdDayConcurrency(unittest.TestCase):
    """Two runs starting on a cold day used to both fetch the feed and
    both run the news screen; the second now waits and reads the
    first's day cache."""

    def test_concurrent_cold_runs_fetch_and_screen_once(self):
        import threading

        fetches, screens = [], []
        started, release = threading.Event(), threading.Event()

        def loader():
            fetches.append(1)
            started.set()
            release.wait(timeout=5)
            return news_fixture()

        def screener(entries):
            screens.append(1)
            return passthrough_screener(entries)

        provider = WorldNewsProvider(
            news_loader=loader, today=lambda: TODAY,
            screener=screener, cache=MemoryCacheStore(),
        )
        results = []
        workers = [
            threading.Thread(target=lambda: results.append(provider.collect("AAPL")))
            for _ in range(2)
        ]
        workers[0].start()
        self.assertTrue(started.wait(timeout=5))
        workers[1].start()
        release.set()
        for worker in workers:
            worker.join(timeout=10)

        self.assertEqual(len(fetches), 1)
        self.assertEqual(len(screens), 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].payload, results[1].payload)
