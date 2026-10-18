# -*- coding: utf-8 -*-
"""World-news provider — the macro/world backdrop card (2026-08-16).

The macro_economy card is numbers (rates, CPI, yields); this card is the
words the numbers can't carry yet: what just changed in the backdrop —
central-bank language, policy moves, geopolitics, data surprises —
before it is fully reflected in the series. It complements, never
replaces, the numeric macro report.

Sources: Google News' RSS search feed (keyless; owner decision
2026-10-18, after AlphaVantage moved its NEWS_SENTIMENT endpoint behind
its paid plans). The feed takes a date operator (``after:``), so one
run covers the full ``WORLD_WINDOW_DAYS`` calendar-day window directly,
one request per macro query in ``WORLD_QUERIES`` (the queries overlap
on purpose; the merge is by URL). An item carries a headline, a link,
a publisher and a date — no abstract (the feed's description is the
headline again), so the screen judges headlines. Google News down: the
keyless backup is Yahoo Finance's news search via yfinance
(``yf.Search``; the per-ticker ``get_news`` has returned nothing since
2026-10-02 on every yfinance 1.x) — no date control, but its newest
``NEWS_FETCH_COUNT`` articles reach ~2-3 days back, covering the short
window. Every fetch merges into the rolling on-disk article pool
(``world_articles_*.json``, merge-by-URL, pruned past
``ARTICLE_RETENTION_DAYS``) whose depth serves the fetch-failure
fallback. The screen judges EVERYTHING in the window — no sampling;
``MAX_SCREEN_ARTICLES`` is a pure fuse that, when tripped, spreads
across the window's days so no single flood-day swallows the budget
(warned). The payload publishes the ACTUAL date span screened
(``oldest``/``newest``); ``window_days`` stays absent on purpose. A
failed fetch falls back to the pool (warned, never day-cached) — only
an empty pool reads UNAVAILABLE; a fetch that answers with zero
articles is warned and never day-cached either. History: the first
build (2026-08-16) used Finnhub's general feed, dropped because it has
no date range at all (newest ~100 only, verified live 2026-08-17 —
``minId`` merely filters that same set); AlphaVantage's NEWS_SENTIMENT
served from 2026-08-17 until it went premium (first seen 2026-10-13).

The screen is the company-news pipeline with the world lens
(``news_screen.WORLD_PROMPTS``): judge each article (about the macro
backdrop? importance 0-5 for the OVERALL market; URL-cached), group
same-story rewrites, keep events at or above the card bar, rank-trim
past the ceiling, summarize winners. The company card's keyword
WHITELIST ("names the company") has no world equivalent — but the
feed's junk is concentrated enough for a deterministic BLACKLIST:
``is_world_spam`` drops the auto-generated fund-holdings genre
(publisher + title templates) before any tokens are spent, and a
blacklist can only ever drop recognizable spam, never a real macro
story with unusual wording. ``filtered_out`` counts that free cut;
``off_topic`` counts what the LLM judge then dropped.

The backdrop is the same for every ticker, so the screened result is
cached ONCE PER DAY (macro_economy convention) and every ticker in a run
reuses it — the ticker argument is intentionally ignored, and cost
stays flat no matter how many stocks a run covers. Citations ride in
the day cache so a cache hit rebuilds them verbatim.

Payload shape — same ``news_coverage`` contract as company news (the
deep analysis's news-row enumeration and the alt page's events renderer are
keyed on kind/payload, not the data_report name)::

    {
      "news_coverage": {
        "oldest": "2026-08-14", "newest": "2026-08-16",
        "filtered_out": 640, "off_topic": 61, "below_bar": 20,
        "score_bar": 4,
        "items": [
          {"text": "<one-sentence summary>", "date": "2026-08-16",
           "publisher": "Reuters", "citation": 1, "importance": 5,
           "articles_covering_event": 7},
        ]},
    }

TEXTUAL kind: never actionable, never feeds numeric consumers.
"""
from __future__ import annotations

import email.utils
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from src.languages import DEFAULT_LANGUAGE

from ..news_screen import WORLD_PROMPTS, NewsJudgmentCache, screen_news
from ..llm_support import run_language
from .base import (
    Citation,
    DataReportProvider,
    DataReport,
    Market,
    SourceKind,
)
from .company_news import (
    CARD_SCORE_BAR,
    NEWS_FETCH_COUNT,
    _parse_date,
    flatten_summary,
    normalize_news_entry,
)
from ..cache_store import CacheStore, default_cache_store

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
_GOOGLE_NEWS_TIMEOUT_SECONDS = 30
#: Politeness pause between the lens requests — the feed publishes no
#: rate limit, and one fetch a day is all the day cache ever needs.
_GOOGLE_NEWS_PAUSE_SECONDS = 1.0
#: The English (US) edition of the feed: the screen prompts and the
#: spam blacklist are written against English headlines; the card's
#: own sentences are written in the run's language by the summary call.
GOOGLE_NEWS_EDITION = {"hl": "en-US", "gl": "US", "ceid": "US:en"}
#: Honest identification; the feed answers python-requests' default
#: too (verified live 2026-10-18).
_USER_AGENT = "custom-stock-analysis (world news fetch)"

#: The macro lenses, one feed query each (Google's search syntax:
#: quoted phrases, OR). They overlap on purpose — the merge is by URL,
#: so a story matching two lenses is fetched once. Measured 2026-10-18:
#: 100 items per query (the feed's cap), ~390 unique across four,
#: spread over the window's days.
WORLD_QUERIES = (
    '"federal reserve" OR "interest rates" OR inflation OR "central bank"',
    'tariffs OR "trade war" OR sanctions OR geopolitics',
    '"stock market" OR "wall street" OR "treasury yields" OR "bond market"',
    'economy OR GDP OR "jobs report" OR unemployment OR recession',
    '"oil prices" OR OPEC OR "dollar index" OR "exchange rate"',
)

#: Lookback in CALENDAR days, today inclusive (owner decision
#: 2026-08-17: "2 days, business or weekend"). World news prices in
#: within hours-to-days, and unlike company news the world's weekend
#: volume is healthy (measured 2026-08-17: Sat ~half a weekday, Sun
#: near-full), so plain calendar days carry no Monday cliff. History:
#: launched at 7 business days; cut after the volume tests showed the
#: extra days' events mostly die at the top-MAX_EVENTS rank anyway.
#: 2 -> 3 calendar days (owner decision 2026-09-18, alongside the
#: 20 -> 30 event cap and the 6-business-day company window); back to
#: 2 (owner decision 2026-09-26).
WORLD_WINDOW_DAYS = 2

#: The Yahoo Finance news-search query that serves as the backup feed
#: — "S&P 500" coverage is the closest thing Yahoo has to a general
#: market-news stream (measured 2026-10-18: ~50 articles, 2 days deep).
YAHOO_WORLD_QUERY = "S&P 500"

#: PURE safety fuse: judging everything in the window is the design —
#: no sampling (measured 2026-08-17: the 2-day window runs ~1.3-1.9k
#: articles, ~340k tokens ≈ 10 cents cold on the screening model, ~3
#: cents/day warm via the URL cache). Set well above the observed
#: ceiling so it only trips if a feed goes haywire; when it does, the
#: cap spreads across the window's days (newest first within each day,
#: trims warned) so no single flood-day swallows the budget.
MAX_SCREEN_ARTICLES = 3000

#: Pooled articles older than this are pruned on load — far past the
#: 2-day window; the extra depth exists only so a failed fetch can
#: still fill the window from disk, whatever day it happens on.
ARTICLE_RETENTION_DAYS = 14

#: The judgment cache's file key — one shared world file, not
#: per-ticker (the feed is ticker-independent).
WORLD_CACHE_KEY = "WORLD"

#: The label the screen prompts use where company news uses the ticker.
_SCREEN_LABEL = "the overall market"

#: Deterministic spam blacklist (owner request 2026-08-19, token cost).
#: The world feed's junk is dominated by one auto-generated genre:
#: "Fund X bought N shares of Company Y" holdings notices. Measured
#: over every article the judge had judged to date (3,828):
#: MarketBeat alone accounted for 1,856 of the 3,442 off-topic
#: judgments against 3 on-topic ever — and all 3 were themselves
#: single-fund holdings pieces, i.e. judge slips, not macro stories.
SPAM_PUBLISHERS = frozenset({"marketbeat"})

#: Title templates of the same holdings-notice genre from other
#: outlets (measured 2026-08-19 on the judgment cache: 838 off-topic
#: matches vs 1 on-topic — itself a MarketBeat holdings piece).
#: Together with the publisher list this cut 54% of all off-topic
#: articles. Deliberately narrow: each phrase is the fixed wording of
#: an auto-generated headline, not a topic keyword.
SPAM_TITLE_RE = re.compile(
    r"(?i)\b("
    r"shares? (?:sold|purchased|bought|acquired) by"
    r"|(?:boosts?|raises?|lowers?|trims?|cuts?|increases?|decreases?"
    r"|reduces?) (?:its )?(?:stock )?(?:position|holdings|stake) in"
    r"|(?:takes?|has|buys?) (?:a )?(?:new )?"
    r"(?:\$[\d.,]+ (?:million|billion) )?"
    r"(?:stock )?(?:position|stake|holdings) in"
    r"|invests? \$[\d.,]+ (?:million|billion) in"
    r"|(?:sells?|acquires?|purchases?|buys?) [\d,]+ shares"
    r"|short interest (?:update|down|up)"
    r"|stock (?:position|holdings) (?:raised|lowered|boosted|trimmed"
    r"|increased|decreased)"
    r")\b"
)


def is_world_spam(entry: Mapping[str, Any]) -> bool:
    """True when the article is recognizable auto-generated single-stock
    spam that should never reach (or pay for) the LLM judge."""
    publisher = str(entry.get("publisher") or "").strip().lower()
    if publisher in SPAM_PUBLISHERS:
        return True
    return bool(SPAM_TITLE_RE.search(str(entry.get("title") or "")))


def parse_google_news_rss(xml_text: str) -> List[Dict[str, Optional[str]]]:
    """The items of one Google News RSS document, each as the raw
    {title, link, pubDate, source} mapping (verified live 2026-10-18:
    ``title`` is "Headline - Publisher", ``link`` a news.google.com
    redirect unique per story, ``pubDate`` RFC 2822, ``source`` the
    publisher's name). Anything that is not an RSS document — a block
    page, an error page — is a ValueError: a failure for the backup
    feed to take over, never an empty news day."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"not an RSS document: {exc}") from exc
    if root.find("channel") is None:
        raise ValueError("not an RSS document: no channel element")
    items: List[Dict[str, Optional[str]]] = []
    for item in root.iter("item"):
        source = item.find("source")
        items.append(
            {
                "title": item.findtext("title"),
                "link": item.findtext("link"),
                "pubDate": item.findtext("pubDate"),
                "source": source.text if source is not None else None,
            }
        )
    return items


def normalize_google_news_item(
    item: Mapping[str, Any]
) -> Dict[str, Optional[str]]:
    """One Google News RSS item -> the shared five-field entry shape.
    The headline loses its " - Publisher" suffix (the publisher is its
    own field); the date is the UTC day of ``pubDate``; ``summary`` is
    None because the feed carries no abstract. Anything missing stays
    None (the caller decides what is fatal)."""
    publisher = str(item.get("source") or "").strip() or None
    title = str(item.get("title") or "").strip()
    if publisher:
        suffix = f" - {publisher}"
        if title.endswith(suffix):
            title = title[: -len(suffix)].rstrip()
    stamp = str(item.get("pubDate") or "").strip()
    pub_date: Optional[str] = None
    if stamp:
        try:
            published = email.utils.parsedate_to_datetime(stamp)
        except (TypeError, ValueError):
            published = None
        if published is not None:
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            pub_date = published.astimezone(timezone.utc).date().isoformat()
    return {
        "title": title or None,
        "publisher": publisher,
        "url": item.get("link") or None,
        "date": pub_date,
        "summary": None,
    }


def _google_news_world_loader() -> List[Dict[str, Optional[str]]]:
    """Macro/market news from Google News' RSS search feed — the
    primary feed. Its ``after:`` operator takes a date, so one run
    covers the full window directly: one request per WORLD_QUERIES
    lens, merged and deduped by URL. The operator is asked one day
    wider than the window (its day boundary is the edition's, not
    UTC); the collect step cuts the pool to the window anyway."""
    import requests

    since = date.today() - timedelta(days=WORLD_WINDOW_DAYS)
    merged: Dict[str, Dict[str, Optional[str]]] = {}
    for index, query in enumerate(WORLD_QUERIES):
        if index:
            time.sleep(_GOOGLE_NEWS_PAUSE_SECONDS)
        response = requests.get(
            GOOGLE_NEWS_RSS_URL,
            params={"q": f"{query} after:{since.isoformat()}", **GOOGLE_NEWS_EDITION},
            timeout=_GOOGLE_NEWS_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        try:
            items = parse_google_news_rss(response.text)
        except ValueError as exc:
            raise ValueError(
                f"Google News returned no feed for query {query!r}: {exc}"
            ) from exc
        for item in items:
            entry = normalize_google_news_item(item)
            if entry["url"]:
                merged.setdefault(entry["url"], entry)
    return list(merged.values())


def _yahoo_world_news_loader() -> List[Dict[str, Optional[str]]]:
    """Market news from Yahoo Finance's news SEARCH via yfinance — the
    keyless backup. No date control: just the newest NEWS_FETCH_COUNT
    articles (Yahoo answers ~50), which reach ~2-3 days back — enough
    for the 2-day window; the rolling pool adds failure-fallback depth.
    The per-ticker news tab (``Ticker.get_news``) is not used: it has
    returned an empty list for every symbol since 2026-10-02, on every
    yfinance 1.x release through 1.7.0."""
    import yfinance as yf

    raw = yf.Search(YAHOO_WORLD_QUERY, news_count=NEWS_FETCH_COUNT).news or []
    return [
        normalize_news_entry(entry) for entry in raw if isinstance(entry, Mapping)
    ]


def _default_world_news_loader() -> Tuple[
    List[Dict[str, Optional[str]]], List[str]
]:
    """Google News first, Yahoo's news search when it fails — both
    keyless. Returns (entries, warnings): a Google News failure falls
    back to Yahoo WITH a warning, which also keeps the degraded result
    out of the day cache so the next run retries the primary feed."""
    try:
        return _google_news_world_loader(), []
    except Exception as exc:
        try:
            return (
                _yahoo_world_news_loader(),
                [
                    "world news: Google News failed"
                    f" ({exc}); used the Yahoo backup feed"
                ],
            )
        except Exception as backup_exc:
            raise RuntimeError(
                f"Google News failed ({exc}) and the Yahoo backup"
                f" failed ({backup_exc})"
            ) from backup_exc


class WorldNewsProvider(DataReportProvider):
    """World/macro news: Google News RSS (Yahoo backup), screened, cited."""

    name = "world_news"
    kind = SourceKind.TEXTUAL
    #: Day-cache format marker — bump when the payload shape or the
    #: collection behavior changes so a same-day cache written by older
    #: code is refetched, not misread (v2: the rolling article pool;
    #: v3: AlphaVantage/Yahoo sources + the business-day window;
    #: v4: the 2-calendar-day window, sampling off; v5: the
    #: deterministic spam prefilter + its filtered_out counter; v6: the
    #: window back from 3 to 2 calendar days; v7: Google News RSS
    #: primary + Yahoo news-search backup, headline-only entries).
    cache_version = "v7"

    def __init__(
        self,
        news_loader: Callable[
            [], Any
        ] = _default_world_news_loader,
        today: Callable[[], date] = date.today,
        screener: Optional[
            Callable[[Sequence[Mapping[str, Any]]], Dict[str, Any]]
        ] = None,
        cache: Optional[CacheStore] = None,
    ) -> None:
        self._load_news = news_loader
        self._today = today
        self._screen = screener or self._default_screener
        self._cache = cache if cache is not None else default_cache_store()

    @staticmethod
    def _default_screener(entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        """The production screen with the world prompt set. Judgments and
        summaries cache by URL in one shared world file."""
        return screen_news(
            _SCREEN_LABEL,
            entries,
            threshold=CARD_SCORE_BAR,
            cache=NewsJudgmentCache(WORLD_CACHE_KEY),
            prompts=WORLD_PROMPTS,
        )

    # The backdrop is global context: every market gets the same card
    # (macro_economy convention — the judge scores world relevance, and a
    # US-centric feed is still the backdrop that moves global risk).
    def supports(self, market: Market) -> bool:
        return True

    #: One lock for every instance: several runs starting on a cold day
    #: used to each miss the day cache, each fetch the feed, each run
    #: the LLM news screen, and overwrite each other's article pool. The
    #: first holds the lock through fetch-screen-store; the rest wait,
    #: then read its result (review 2026-10-10).
    _cold_day_lock = threading.Lock()

    # The ticker is intentionally ignored: world news is per-day, not
    # per-stock — the day cache makes a multi-ticker run screen once.
    def collect(self, ticker: str) -> DataReport:
        cached = self._read_cache()
        if cached is not None:
            return cached
        with self._cold_day_lock:
            cached = self._read_cache()
            if cached is not None:
                return cached
            return self._collect_uncached()

    def _collect_uncached(self) -> DataReport:
        warnings: List[str] = []
        fetched: List[Dict[str, Optional[str]]] = []
        fetch_ok = True
        degraded_fetch = False
        try:
            loaded = self._load_news()
        except Exception as exc:
            # The rolling pool is the fallback: a transient feed failure
            # degrades to yesterday's articles (warned), never to a
            # blank card while news exists on disk.
            fetch_ok = False
            entries: List[Any] = []
            warnings.append(f"world news fetch failed: {exc}")
        else:
            # The default loader reports source degradation (primary
            # feed down, backup used) as (entries, warnings); injected
            # plain-sequence loaders keep working unchanged.
            if isinstance(loaded, tuple):
                entries = list(loaded[0])
                loader_warnings = list(loaded[1])
            else:
                entries, loader_warnings = list(loaded), []
            if loader_warnings:
                degraded_fetch = True
                warnings.extend(loader_warnings)
            if not entries:
                # A feed that answers with nothing is not a news-free
                # day (both feeds went silently empty in October 2026):
                # warn, and never day-cache the blank — the same day's
                # next run fetches again.
                degraded_fetch = True
                warnings.append("world news: the feed returned no articles")

        # Same evidence hygiene as company news: an unverifiable item
        # (no link) or an undatable one must not masquerade as evidence;
        # one URL = one story.
        dropped = 0
        seen_urls = set()
        for entry in entries:
            title, url = entry.get("title"), entry.get("url")
            published = _parse_date(entry.get("date")) if entry.get("date") else None
            if not title or not url or published is None:
                dropped += 1
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            fetched.append({**entry, "date": published.isoformat()})
        if dropped:
            warnings.append(
                f"{dropped} world news item(s) skipped (missing headline, link,"
                " or date)"
            )

        # The rolling pool: the Yahoo backup only ever serves its
        # newest articles, so successive fetches accumulate on disk
        # until the pool covers the window; the Google News primary
        # covers the window in one fetch and the pool then just adds
        # resilience. Merge by URL (a refetch refreshes its entry),
        # prune past retention, persist.
        pool = self._load_pool()
        for entry in fetched:
            pool[entry["url"]] = entry
        oldest_kept = self._today() - timedelta(days=ARTICLE_RETENTION_DAYS)
        pool = {
            url: entry
            for url, entry in pool.items()
            if str(entry.get("date") or "") >= oldest_kept.isoformat()
        }
        if fetch_ok:
            self._save_pool(pool)
        elif not pool:
            # A failed fetch with an empty pool still ships the card's
            # shape — an empty timeline with the warning saying why
            # (degradation lives on the card notes, never on a
            # card-level grade, 2026-08-19).
            return DataReport(
                name=self.name,
                kind=self.kind,
                payload={
                    "news_coverage": {
                        "oldest": None,
                        "newest": None,
                        "filtered_out": 0,
                        "off_topic": 0,
                        "below_bar": 0,
                        "score_bar": CARD_SCORE_BAR,
                        "items": [],
                    }
                },
                warnings=warnings + ["world news unavailable: no pooled articles"],
            )
        else:
            warnings.append(
                f"showing {len(pool)} previously fetched article(s) instead"
            )

        # The calendar-day window is the cut the card promises; the
        # pool's extra retention days exist only so a failed fetch can
        # still fill the whole window from disk.
        since = self._today() - timedelta(days=WORLD_WINDOW_DAYS - 1)
        in_window = [
            entry
            for entry in sorted(
                pool.values(), key=lambda entry: entry["date"] or "", reverse=True
            )
            if str(entry.get("date") or "") >= since.isoformat()
        ]

        # Identical body text = the same syndicated story under another
        # URL; one bullet is enough.
        seen_text = set()
        deduped: List[Dict[str, Optional[str]]] = []
        for entry in in_window:
            body = flatten_summary(entry.get("summary") or entry["title"]).lower()
            if body in seen_text:
                continue
            seen_text.add(body)
            deduped.append(entry)

        # The free deterministic cut, before any tokens are spent:
        # recognizable holdings-notice spam never reaches the judge.
        # Counted in the payload (filtered_out), never silent.
        kept = [entry for entry in deduped if not is_world_spam(entry)]
        spam_cut = len(deduped) - len(kept)

        # The screen cap, spread across the window's days: round-robin
        # one article per day (newest first within each day) until the
        # cap fills, so every day stays represented — a plain
        # newest-first cut hands the whole budget to today and
        # collapses the card's span to one day (observed live
        # 2026-08-17 on the first AlphaVantage run). Trims are warned —
        # a silent cap would read as "covered the window" when it
        # didn't.
        if len(kept) <= MAX_SCREEN_ARTICLES:
            unique = kept
        else:
            by_day: Dict[str, List[Dict[str, Optional[str]]]] = {}
            for entry in kept:  # already newest-first within a day
                by_day.setdefault(str(entry["date"]), []).append(entry)
            days = sorted(by_day, reverse=True)
            unique = []
            while len(unique) < MAX_SCREEN_ARTICLES:
                took_any = False
                for day in days:
                    if not by_day[day]:
                        continue
                    unique.append(by_day[day].pop(0))
                    took_any = True
                    if len(unique) >= MAX_SCREEN_ARTICLES:
                        break
                if not took_any:
                    break
            unique.sort(key=lambda entry: entry["date"] or "", reverse=True)
            warnings.append(
                f"busy world window: screening {len(unique)} of"
                f" {len(kept)} article(s), spread evenly across the"
                " window's days"
            )

        # The actual horizon screened — published instead of a window
        # promise (the Yahoo backup cannot guarantee the full window).
        newest = unique[0]["date"] if unique else None
        oldest = unique[-1]["date"] if unique else None

        screen = self._screen(unique)
        warnings.extend(screen["warnings"])

        shown = sorted(
            screen["selected"],
            key=lambda event: event["entry"].get("date") or "",
            reverse=True,
        )
        citations: List[Citation] = []
        items: List[Dict[str, Any]] = []
        for event in shown:
            entry = event["entry"]
            body = event.get("card_text") or flatten_summary(
                entry.get("summary") or entry["title"]
            )
            citations.append(
                Citation(
                    source_name=entry.get("publisher") or "news feed",
                    url=entry["url"],
                    title=entry["title"],
                )
            )
            item: Dict[str, Any] = {
                "text": body,
                "date": entry["date"],
                "publisher": entry.get("publisher"),
                "citation": len(citations),
            }
            if event.get("materiality") is not None:
                item["importance"] = event["materiality"]
            if event.get("group_size", 1) > 1:
                item["articles_covering_event"] = event["group_size"]
            items.append(item)

        result = DataReport(
            name=self.name,
            kind=self.kind,
            payload={
                "news_coverage": {
                    "oldest": oldest,
                    "newest": newest,
                    # Screen transparency: the deterministic spam cut
                    # (free, pre-judge), the judge's off-topic cut
                    # (select_events' mention_only under the world lens)
                    # and the importance bar applied.
                    "filtered_out": spam_cut,
                    "off_topic": screen["mention_only"],
                    "below_bar": screen["below_threshold"],
                    "score_bar": CARD_SCORE_BAR,
                    "items": items,
                }
            },
            citations=citations,
            warnings=warnings,
        )
        # A degraded result (pool fallback, or the backup feed standing
        # in for a failed primary) is never day-cached: the next run the
        # same day should retry the real feed, not inherit the
        # degradation.
        if fetch_ok and not degraded_fetch:
            self._write_cache(result)
        return result

    # ---- rolling article pool (the feed has no lookback) ----

    #: Pool format marker — bump when the entry shape changes.
    pool_version = "v1"

    def _pool_key(self) -> str:
        return f"world_articles_{self.pool_version}"

    def _load_pool(self) -> Dict[str, Dict[str, Optional[str]]]:
        try:
            raw = self._cache.read(self._pool_key())
            articles = raw.get("articles") if isinstance(raw, Mapping) else None
            if not isinstance(articles, Mapping):
                return {}
            return {
                str(url): dict(entry)
                for url, entry in articles.items()
                if isinstance(entry, Mapping) and entry.get("title")
            }
        except Exception:
            return {}  # corrupt pool: rebuild from fetches, never fail

    def _save_pool(self, pool: Dict[str, Dict[str, Optional[str]]]) -> None:
        # The store never raises: a thinner pool tomorrow is acceptable,
        # failing the run is not.
        self._cache.write(self._pool_key(), {"articles": pool})

    # ---- per-day cache (macro_economy convention) ----

    def _cache_key(self) -> str:
        # The card's sentences are written in the run's language, so each
        # language has its own day cache; English keeps the pre-2026-09-26
        # key so a same-day English card is not refetched.
        language = run_language()
        tag = "" if language == DEFAULT_LANGUAGE else f"_{language}"
        return f"world_news_{self.cache_version}{tag}_{self._today().isoformat()}"

    def _read_cache(self) -> Optional[DataReport]:
        raw = self._cache.read(self._cache_key())
        if not isinstance(raw, Mapping):
            return None
        try:
            return DataReport(
                name=self.name,
                kind=self.kind,
                payload=raw["payload"],
                citations=[
                    Citation(
                        source_name=entry.get("source_name") or "news feed",
                        url=entry.get("url"),
                        title=entry.get("title"),
                    )
                    for entry in raw.get("citations", [])
                    if isinstance(entry, Mapping)
                ],
                warnings=list(raw.get("warnings", [])),
            )
        except Exception:
            return None  # corrupt cache: refetch, never fail on cache

    def _write_cache(self, result: DataReport) -> None:
        self._cache.write(
            self._cache_key(),
            {
                "payload": result.payload,
                "citations": [
                    {
                        "source_name": citation.source_name,
                        "url": citation.url,
                        "title": citation.title,
                    }
                    for citation in result.citations
                ],
                "warnings": result.warnings,
            },
        )
