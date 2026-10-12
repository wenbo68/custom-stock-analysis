# -*- coding: utf-8 -*-
"""Tier 2: the evidence vote (v12 — graded sheet).

v12 revision (owner spec 2026-07-31, replacing the v8-v11 free-form
lists): the opening stage is a GRADE SHEET. Code enumerates every
gradable report field (each non-blank leaf, in report order) and each
of the two blind LISTERS must return exactly one grade per field —
bullish, bearish or neutral. The one-grade-per-field rule is enforced
structurally (``check_grade_sheet`` rejects a reply that skips, invents
or double-grades a field; JSON object keys make a double grade
impossible to express), not by prompt wording. One tolerance (owner
decision 2026-08-05): a grade on a field that exists in the report but
is blank is silently dropped, never a sheet failure — the report text
shows blank fields and the AIs kept grading them, voiding whole runs. Code converts the
non-neutral grades into vote items — ids assigned by code in
field order, the graded field's citation injected by code with the
exact display value — and MATCHES the two sheets by field in pure code
(same field + same item outlook = the same vote item; an opposite-outlook
clash is a dispute and stays unmatched). The old merge LLM call is
gone. Membership is a majority vote with at most three votes per
vote item:

- A vote item's lister is automatically its first valid vote, so a vote item
  BOTH listers listed independently starts 2-0 — confirmed, no checking.
- A CHECK round casts the second vote on every single-lister vote item:
  2-0 confirmed or 1-1 tied.
- A DECIDING round breaks the ties: 2-1 in or 1-2 out. Three votes,
  so a tie is impossible.

Citations are code's job alone (carried over from v7): links are
``{ref, value}`` with the value copied exactly as the report pages
display it (``display_value``).
Code verifies every link — including the links inside vote reasons —
and sends failures back to the same AI in up to ``MAX_FIX_ROUNDS``
focused fix calls; vote items that cannot be fixed are STRUCK (crossed
out, never voted on, in no pool) and unfixable votes are discarded.

No LLM writes any number, but every voter RATES each vote item's
importance 1-5 (v11 owner spec, 2026-07-20: 1 = very minor, 3 = normal
evidence, 5 = very important — thesis-changing) and gives one short
plain sentence saying why (``score_reason``, shown in the UI's check
modals). Listers rate their own vote items in the same call; check/decider
votes carry a score alongside the validity. A vote item's final score is
the MEDIAN of its voters' scores (two voters → their mean, so halves
happen). The outlook score is computed by code from the item-outlook tags
and the scores:
``10 × Σweight(bullish) / Σweight(all)`` over the whole pool
(per-data_report counts and score sums are stored for the section
headers). Two snapshots: initial (the merged list before voting,
weighted by the lister_count' own ratings, stored for the audit trail only)
and final (the vote items the votes left standing, weighted by the full
voter median — the displayed score). Outlook on the 2-decimal final:
< 4 sell, 4-6 hold, > 6 buy. Empty final pool → 5.00, hold, warning.

4-5 base LLM calls (two grade sheets parallel with their fix loops →
code merge → check round → deciding round only when there are ties →
summary), all temperature 0. Every stage fills a strict Pydantic form;
an invalid reply gets ONE retry with the errors shown, then: both
sheets failing voids the tier-2 outlook — the run has no outlook and
says re-run (no fallback: tier 2 never runs the tier-1 one-blob
outlook, so there is nothing to fall back to); one
sheet failing proceeds with the other; a failed check round counts
vote items on their lister's vote alone; a failed deciding round excludes
the tied vote items as unresolved; the summary's failure never voids
anything.

2026-08-16 (owner decision): the news cards joined the sheet — every
card news event is one gradable row
(``company_news.news_coverage.items.{i}.text``, id prefix N;
``world_news.…``, id prefix W — both keyed by TEXTUAL kind, not by
name). News rows relax the value-copy rule only (the ref anchors the
claim to the event; a 40-word summary has no short display value to
copy) — everything else (votes, scores, pools, the summary group)
treats them like any other field.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import ValidationError

from .deep_analysis_models import (
    CitationFixModel,
    DATA_REPORT_PREFIX,
    DATA_REPORTS,
    EvidenceItemModel,
    GradeSheetModel,
    LinkModel,
    StructuredSummaryModel,
    VoteFixModel,
    VoteModel,
    VoteRoundModel,
    check_exact_keys,
    check_grade_sheet,
    check_summary_groups,
)
from .llm_support import (
    JSON_REPLY,
    LlmConfigError,
    active_tracker,
    deterministic_summarizer,
    display_value,
    evidence_block,
    in_language,
    language_rule,
    parse_llm_json,
    summarize_with_schema,
)
from .providers.base import DataReport, SourceKind
from .providers.technicals import is_envelope
from .schema import (
    DEFAULT_MAX_HOLD_WEEKS,
    Outlook,
    TierReport,
    max_hold_weeks_text,
)

#: Outlook bands on the 2-decimal final score (owner spec).
BEARISH_BELOW = 4.0
NEUTRAL_MAX = 6.0

#: How many focused fix calls a broken citation gets before its vote item is
#: struck (or its vote discarded).
MAX_FIX_ROUNDS = 3

#: Stored-detail version marker — the frontend picks its renderer by this.
#: 11 = 1-5 scores with per-voter score reasons and lister attribution
#: (``lister_votes``: which lister listed the vote item, their rating and
#: why); 10 = 1-3 scores, ratings only; stored format-9 runs are the
#: same shapes minus the score keys, with flat counting. The v12 graded
#: opening (2026-07-31) only ADDS the per-vote item ``field`` key, so the
#: stored shape stays format 11.
DETAIL_FORMAT = 11

#: A vote reason that states a report-style number (a decimal or a
#: percentage) must cite it — bare integers like "above 50" are usually
#: thresholds, not report fields, so they are not forced.
_NUMERIC_REASON_RE = re.compile(r"\d+\.\d+|\d+(?:\.\d+)?\s?%")


def outlook_from_final(final: float) -> Outlook:
    """The fixed mapping from the 0-10 final score to an outlook."""
    if final < BEARISH_BELOW:
        return Outlook.BEARISH
    if final <= NEUTRAL_MAX:
        return Outlook.NEUTRAL
    return Outlook.BULLISH


@dataclass(frozen=True)
class AnchoredReason:
    """A claim tied to evidence refs — still used by the tier-3 risk stage."""

    claim: str
    evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DeepAnalysisOutlook:
    outlook: Outlook
    #: The final pool's weighted score: 10 × Σweight(bullish) / Σweight(all).
    final_score: float
    summary: str
    #: The same formula over the merged list before any voting, weighted
    #: by the lister_count' own ratings.
    initial_score: float
    #: Per-pool audit: {initial|final: {data_reports, bullish, bearish,
    #: total, score}}.
    pools: Dict[str, Any] = field(default_factory=dict)
    #: The report as the fixed outline (StructuredSummaryModel dump);
    #: ``summary`` above is its flat-text rendering (the tier-2 report's
    #: summary). None when the summary stage failed.
    summary_structure: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class DeepAnalysisResult:
    #: The evidence list, one dict per vote item (see _base_item for the shape).
    items: List[Dict[str, Any]] = field(default_factory=list)
    outlook: Optional[DeepAnalysisOutlook] = None
    warnings: List[str] = field(default_factory=list)

    def to_detail(self) -> Dict[str, Any]:
        """JSON-ready audit trail for storage and the vote-tree UI."""
        outlook: Optional[Dict[str, Any]] = None
        if self.outlook is not None:
            v = self.outlook
            outlook = {
                "outlook": v.outlook.value,
                "final_score": v.final_score,
                "summary": v.summary,
                "summary_structure": v.summary_structure,
                "initial_score": v.initial_score,
                "pools": v.pools,
            }
        return {
            "format": DETAIL_FORMAT,
            "items": [dict(item) for item in self.items],
            "outlook": outlook,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Payload helpers (leaf counting, value lookup, display-string matching)
# ---------------------------------------------------------------------------


def _leaf_refs(dim: DataReport) -> List[str]:
    """Every payload leaf ref of one data_report, in report order — an
    envelope {name, explanation[, interpretation], value} is one leaf."""
    rows: List[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict) and not is_envelope(node):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
            return
        rows.append(path)

    for key, value in (dim.payload or {}).items():
        walk(value, f"{dim.name}.{key}")
    return rows


def _news_item_refs(dim: DataReport) -> List[str]:
    """One gradable ref per vote item of a textual card: the item's
    summary sentence (``items.{i}.text``), enumerated from EVERY
    payload group that carries an items list (the news cards' single
    ``news_coverage`` group today, payload order). The groups' other
    keys (window/date-span, screen counters) are bookkeeping, not
    evidence, and get no rows — the EVENT is the gradable fact."""
    refs: List[str] = []
    for group_key, group in (dim.payload or {}).items():
        items = group.get("items") if isinstance(group, dict) else None
        if not isinstance(items, list):
            continue
        refs.extend(
            f"{dim.name}.{group_key}.items.{index}.text"
            for index, item in enumerate(items)
            if isinstance(item, dict) and item.get("text")
        )
    return refs


def gradable_field_refs(
    data_reports: Sequence[DataReport],
) -> Dict[str, List[str]]:
    """The grade sheet's row set: every citable leaf ref per data_report,
    in report order. An envelope {name, explanation[, interpretation],
    value} is ONE gradable fact (its prose keys are documentation);
    blank fields (value null) carry no evidence and get no row — code
    already knows why they are blank. News cards are textual (kind, not
    name — company_news and world_news alike): their rows are the
    news EVENTS (one per vote item, ``_news_item_refs``), never their
    bookkeeping counters."""
    refs: Dict[str, List[str]] = {}
    for dim in data_reports:
        if dim.name not in DATA_REPORTS or not dim.payload:
            continue
        if dim.kind == SourceKind.TEXTUAL:
            rows = _news_item_refs(dim)
        else:
            rows = [
                path for path in _leaf_refs(dim) if _payload_value(path, [dim])[0]
            ]
        if rows:
            refs[dim.name] = rows
    return refs


def blank_field_refs(data_reports: Sequence[DataReport]) -> set:
    """Payload leaves that exist but are blank (value null). They get no
    grade-sheet row, but the report text the listers read still shows
    them, and the AIs keep grading them anyway — so a grade landing on
    one is DROPPED (it would have been an invisible neutral at best),
    never a reason to fail the whole sheet (owner decision 2026-08-05:
    a voided outlook over meaningless grades is the worse outcome)."""
    refs: set = set()
    for dim in data_reports:
        if dim.name not in DATA_REPORTS or not dim.payload:
            continue
        if dim.kind == SourceKind.TEXTUAL:
            continue  # news rows are enumerated non-blank by construction
        refs.update(
            path
            for path in _leaf_refs(dim)
            if not _payload_value(path, [dim])[0]
        )
    return refs


def _payload_value(ref: str, data_reports: Sequence[DataReport]) -> Tuple[bool, Any]:
    """(resolves-to-a-leaf, value) for a ``data_report.key[.subkey…]`` ref.

    A ref that lands on a {name, explanation[, interpretation], value}
    envelope resolves to its ``value`` — the envelope path IS the citable
    leaf; its prose keys are documentation, not separately citable facts.
    A numeric segment indexes a list (``news_coverage.items.3.text`` —
    how the company-news rows resolve); lists themselves are never
    leaves.
    """
    parts = ref.split(".")
    if len(parts) < 2:
        return False, None
    data_report_name, path = parts[0], parts[1:]
    for dim in data_reports:
        if dim.name != data_report_name or not dim.payload:
            continue
        node: Any = dim.payload
        for segment in path:
            if isinstance(node, dict) and segment in node:
                node = node[segment]
            elif (
                isinstance(node, list)
                and segment.isdigit()
                and int(segment) < len(node)
            ):
                node = node[int(segment)]
            else:
                node = None
                break
        if is_envelope(node):
            node = node.get("value")
        if isinstance(node, str) and not node.strip():
            # An empty string is a blank field, like null: it carries no
            # evidence, and a grade-sheet row for it would get an
            # injected link with an empty value, which LinkModel refuses
            # — inside the lister thread, failing the whole deep
            # analysis (review 2026-10-10; an SEC entity name or sector
            # can arrive as "").
            node = None
        if node is not None and not isinstance(node, (dict, list)):
            return True, node
    return False, None


def _is_textual_ref(ref: str, data_reports: Sequence[DataReport]) -> bool:
    """Whether a ref points into a TEXTUAL data_report (the company-news
    card). Textual refs anchor a claim to a news event — there is no
    short display value to copy verbatim, so the value-copy and
    value-in-sentence rules do not apply; the ref resolving is the
    check. Everything numeric keeps the strict contract."""
    name = ref.split(".", 1)[0]
    return any(
        dim.name == name and dim.kind == SourceKind.TEXTUAL
        for dim in data_reports
    )


def _link_value_text(value: Any) -> str:
    """The link's claimed value as a display string (numbers a model sends
    as JSON numbers are normalized through the same formatter)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value).strip()
    return display_value(value)


def _norm_text_value(text: str) -> str:
    """Loose comparison form for TEXT values only ("Golden_Cross" ↔
    "golden cross") — numbers never come through here."""
    return re.sub(r"[_\s]+", " ", text).strip().lower()


def _values_equal(claimed: str, expected: str) -> bool:
    if claimed == expected:
        return True
    if any(char.isdigit() for char in expected):
        return False  # numeric display strings must be copied exactly
    return _norm_text_value(claimed) == _norm_text_value(expected)


def value_pattern(value_text: str) -> "re.Pattern[str]":
    """Where a display value may appear in a sentence: the exact string,
    tolerating thousands separators ("1,234" for "1234") and — for text
    values — case/underscore looseness. Digit boundaries stop "205" from
    matching inside "1205" or "205.4". The frontend underliner builds the
    same pattern to highlight exactly the cited value."""
    parts: List[str] = []
    for index, char in enumerate(value_text):
        parts.append("[_ ]" if char == "_" else re.escape(char))
        if (
            char.isdigit()
            and index + 1 < len(value_text)
            and value_text[index + 1].isdigit()
        ):
            parts.append(",?")
    pattern = "".join(parts)
    if value_text[:1].isdigit() or (
        value_text[:1] == "-" and value_text[1:2].isdigit()
    ):
        pattern = r"(?<![\d.])" + pattern
    if value_text[-1:].isdigit():
        pattern += r"(?!\.?\d)"
    flags = 0 if any(char.isdigit() for char in value_text) else re.IGNORECASE
    return re.compile(pattern, flags)


def _value_in_text(value_text: str, sentence: str) -> bool:
    return bool(value_pattern(value_text).search(sentence))


# ---------------------------------------------------------------------------
# Prompts — one marker phrase per stage so tests can route replies.
# ---------------------------------------------------------------------------

_CONTEXT_TEMPLATE = """Stock under analysis: {ticker}
This is a SWING TRADE held for up to {hold_text} (the user's chosen max
hold time). Judge every piece of evidence against that horizon — use
your own judgment about what matters at this timescale (owner decision
2026-08-08: the same number drives the report and the forward test).

Collected evidence (the ONLY facts you may use — no outside knowledge):
{evidence_block}

{language_rule}
"""

# _LINK_RULES and _VOTE_RULES are passed to str.format as VALUES (the
# templates below take them as {link_rules} / {vote_rules}), so they are
# never formatted themselves: braces here are literal, single. Doubled
# braces showed the model {{"ref": …}} as the shape to copy (2026-10-10).
_LINK_RULES = """Link rules (all checked mechanically by code):
- Every vote item carries "links": one entry per report field the sentence
  uses, each {"ref": the leaf field, "value": the value copied EXACTLY
  as the report above displays it}.
- The claim sentence must contain each linked value verbatim — "The
  14-day RSI (56.28) is above 50", never "RSI is high". Copy the
  displayed string exactly: if the report shows 56.28, write 56.28,
  never 56.3 or 56.280. Write values as plain numbers in the sentence —
  do not wrap them in quotation marks.
- A "ref" must point at ONE exact value, like "technicals.daily.rsi_14"
  — grouping paths ("technicals.daily" when it holds sub-fields) are
  rejected; cite the field ("technicals.daily.rsi_14"). A report field
  may be an envelope {"name", "explanation", "interpretation", "value"}:
  cite the FIELD path, never ".value"/".name" — the ref resolves to the
  value automatically.
- Code verifies every link and sends failures back to you to fix;
  vote items that cannot be fixed are struck from the list.
- Exception: a ref into a textual card (company_news or
  world_news) points at an item's summary sentence — cite the item's
  text field (like "company_news.news_coverage.items.3.text" or
  "world_news.news_coverage.items.1.text") and you do NOT copy that
  sentence into your own; the ref itself is the anchor.
- Use only the evidence above; never invent facts or numbers."""

_VOTE_RULES = """Vote rules (checked mechanically by code):
- Every vote: "validity" is "valid" or "invalid", plus a short plain
  "reason" — REQUIRED either way; a vote without a reason is rejected.
- Every vote also carries "score": your own importance rating of the
  vote item for the trade decision, 1 to 5 — 1 (very minor), 2 (minor),
  3 (normal evidence), 4 (important), 5 (very important — could change
  the whole thesis alone). Rate it regardless of your validity call; code
  takes the median of all voters' scores.
- Every vote also carries "score_reason": ONE short plain sentence
  saying why you rated it that important. Plain words only — report
  numbers belong in the vote reason with links, never here.
- If your reason states a number from the reports, cite it with a link
  {"ref": the leaf field, "value": the value copied EXACTLY as the
  report displays it} and write that exact value in your reason.
- The reason is a plain sentence for a human reader — never paste refs
  or link JSON into it; refs belong in "links" only.
- Code verifies every link and sends failures back to you to fix; votes
  that cannot be fixed are discarded."""

_GRADE_RULES = """Grade-sheet rules (all checked mechanically by code):
- Reply with EXACTLY one grade per field key listed above — code
  rejects a reply that skips a field, invents a field key, or grades a
  field twice.
- Fields shown blank/null in the report are NOT on the sheet — do not
  grade them (code ignores any grade on a blank field).
- Each grade: "item_outlook" is "bullish", "bearish" or "neutral" for
  this swing trade. Neutral = the field carries no lean either way
  (metadata like dates and bar counts, or a genuinely mixed reading);
  a neutral grade needs no other keys and produces no evidence.
- A bullish/bearish grade carries "claim": ONE plain sentence stating
  the evidence, containing the field's value copied EXACTLY as the
  report above displays it. Code attaches the graded field's citation
  itself; only if the sentence ALSO states another field's value, cite
  that other field in "links" (link rules below).
- A bullish/bearish grade carries "score": your importance rating of
  the evidence for the trade decision, 1 to 5 — 1 (very minor),
  2 (minor), 3 (normal evidence), 4 (important), 5 (very important —
  could change the whole thesis alone). Most are a 3; reserve 5 for
  evidence that would change the whole thesis on its own, and 1 for
  footnotes. Code weighs the score by these ratings.
- A bullish/bearish grade carries "score_reason": ONE short plain
  sentence saying why you rated it that important. Plain words only —
  report numbers belong in the claim sentence, never here.
- If fundamentals.quarterly_report.next_earnings_date shows a report
  within roughly a week of the report's as-of date, grade that field
  bearish — an imminent earnings report can gap the price past any
  plan level, which argues for waiting.
- company_news and world_news rows are NEWS EVENTS, not numbers:
  each ref points at one news summary in the report. Grade the event's
  likely effect on THIS stock over the hold time — bullish, bearish, or
  neutral when it has no clear lean (routine coverage, already-priced-in
  noise). world_news items are market-wide backdrop news: judge what
  the event means for this particular stock (a rate story hits a bank
  and a miner differently); when it has no read-through to this name,
  grade it neutral. The claim states the event and why it leans that
  way IN YOUR OWN WORDS — the value-copy rule does not apply to news
  rows (code attaches the event citation itself); any NUMBER your claim
  quotes from the news text still appears exactly as the report shows
  it.
- Code computes the outlook score from the item_outlook tags and each
  item's score; you never write an outlook score."""

# Substituted into the templates as a VALUE (never format()ed itself),
# so the braces are literal.
_GRADE_SHAPE = """{"grades": {
  "technicals.daily.rsi_14": {"item_outlook": "bullish",
    "claim": "The 14-day RSI (56.28) is above 50, showing bullish momentum.",
    "links": [],
    "score": 3, "score_reason": "Momentum backs the trend but rarely drives it alone."},
  "technicals.meta.as_of": {"item_outlook": "neutral"},
  "company_news.news_coverage.items.0.text": {"item_outlook": "bearish",
    "claim": "The new antitrust lawsuit adds legal risk that could weigh on the stock during the hold.",
    "links": [],
    "score": 4, "score_reason": "Litigation news can move the price on its own."},
  ...one entry for EVERY field key listed above...}}"""

_GRADER1_TEMPLATE = """{context}
You are LISTER 1. Lister 2 is grading the same sheet
separately; neither of you sees the other's work. Take no side: grade
EVERY field on the sheet below — bullish, bearish or neutral — walking
it top to bottom so nothing is skipped. You give no outlook score; code
computes it from your grades' item_outlook tags and scores.

The grade sheet (one grade per field key, exactly these keys):
{field_rows}

{grade_rules}

{link_rules}

Reply with JSON only:
{shape}"""

_GRADER2_TEMPLATE = """{context}
You are LISTER 2. Lister 1 is grading the same sheet
separately; you have NOT seen their work. Take no side: grade EVERY
field on the sheet below — bullish, bearish or neutral. Think theme by
theme — momentum, trend, profitability, valuation, balance sheet,
macro pressures — then make sure every field key has exactly one
grade. You give no outlook score; code
computes it from your grades' item_outlook tags and scores.

The grade sheet (one grade per field key, exactly these keys):
{field_rows}

{grade_rules}

{link_rules}

Reply with JSON only:
{shape}"""

_CITATION_FIX_TEMPLATE = """Collected evidence (the ONLY facts you may use — no outside knowledge):
{evidence}

Some of your vote items failed the code's citation check. Fix each
vote item listed below: point the ref at the right leaf field, copy the
value exactly as the report above displays it, and make sure the claim
sentence contains that exact value. Keep each vote item's "id" and
"data_report" unchanged; you may rewrite the claim, the links, and the
item_outlook tag.

{link_rules}

{language_rule}

The vote items to fix:
{items}

The code's error list:
{errors}

Reply with JSON only:
{{"items": [ ...every vote item above, corrected, same ids... ]}}"""

_VOTE_FIX_TEMPLATE = """Collected evidence (the ONLY facts you may use — no outside knowledge):
{evidence}

Some of your votes failed the code's citation check. Fix each vote
listed below: cite every number your reason states, copying the value
exactly as the report above displays it. Keep the same keys; you may
rewrite the reason and links, and reconsider the validity with the
correct numbers in hand.

{vote_rules}

{language_rule}

The votes to fix:
{votes}

The code's error list:
{errors}

Reply with JSON only:
{{"votes": {{ ...every vote above, corrected, same keys... }}}}"""

_CHECK_TEMPLATE = """{context}
The merged evidence list (every vote item's numbers already code-verified):
{tree}

Each vote item named below was listed by only ONE of the two listers, so
it has one vote so far (its lister's). You cast the second vote on each:
- "valid" — the sentence says something TRUE about the verified values
  AND the bullish/bearish tag actually follows from the fact.
- "invalid" — the statement is wrong about the values, or the tag does
  not follow. Say why.
Vote on the vote item in front of you, not on the stock.

{vote_rules}

Reply with JSON only:
{{"votes": {{"T2": {{"validity": "invalid", "reason": "why it is flawed", "links": [{{"ref": "technicals.price.close", "value": "100"}}], "score": 3, "score_reason": "why it matters this much"}}}}}}
"votes" must cover exactly these vote item ids: {check_ids}."""

_DECIDER_TEMPLATE = """{context}
The merged evidence list (every vote item's numbers already code-verified):
{tree}

The vote items below are TIED — one lister listed each, and the check
vote went against it. You cast the deciding vote. For each vote item you
see the claim and the objection; weigh both and rule:
- "valid" — the vote item stands and counts in the score.
- "invalid" — the objection is right and the vote item is out.

{disputes}

{vote_rules}

Reply with JSON only:
{{"votes": {{"T2": {{"validity": "valid", "reason": "why the vote item stands", "links": [], "score": 3, "score_reason": "why it matters this much"}}}}}}
"votes" must cover exactly these vote item ids: {tied_ids}."""

_SUMMARY_TEMPLATE = """{context}
The voted evidence list:
{tree}

Computed result (fixed formula, already decided by code — the score is
10 × the total importance score of the bullish vote items / the total
score of all vote items, over the pool the votes left standing; each
vote item's score is the median of its voters' 1-5 ratings):
- final score {final} ({final_bullish} bullish vs {final_bearish}
  bearish of {final_total} vote items; bullish score {final_bullish_score_sum}
  of {final_total_score_sum} total)
- outlook: {outlook} (below 4 bearish, 4-6 neutral, above 6 bullish)

Write the user-facing report as a fixed bullet outline. Reply with JSON
only. Never write the words "outlook", "buy", "hold" or "sell" — say
bullish, neutral or bearish:
{{"summary": [{{"text": "one short plain sentence", "links": [], "children": []}}],
 "technicals": [{{"text": "The 14-day RSI (56.28) is above 50.",
   "links": [{{"ref": "technicals.daily.rsi_14", "value": "56.28"}}],
   "children": [{{"text": "optional supporting detail", "links": []}}]}}],
 "fundamentals": [], "positioning": [], "macro_economy": [],
 "company_news": [], "world_news": []}}

Rules:
- "summary": 2-4 bullets stating the outlook and the decisive reasons.
- Fill exactly these data_report groups (the others stay []): {fill_groups}.
  Each filled group: 1-4 bullets on what its surviving evidence says.
- "children" holds supporting detail one level deep; keep it [] when a
  bullet needs none.
- Every "text" and every child is one short plain sentence.
- If a sentence states a number from the reports, write the value copied
  EXACTLY as the report above displays it and cite it in that bullet's
  "links" as {{"ref": the leaf field, "value": that exact value}} — the
  same link rules as the evidence list, checked mechanically by code.
  Code sends failures back to you to fix; links that cannot be fixed
  are dropped from the report.
- "company_news" and "world_news" bullets talk about the news
  events; cite each event by its ref
  ("company_news.news_coverage.items.3.text",
  "world_news.news_coverage.items.1.text") — for these refs there
  is no value to copy into the sentence.
- Support the computed outlook; if little evidence survived, say plainly
  that the case is weak.
- Use only the evidence above; do not invent facts."""

#: Flat-text group titles for the legacy summary rendering.
_SUMMARY_GROUP_TITLES = {
    "summary": "Summary",
    "technicals": "Technicals",
    "fundamentals": "Fundamentals",
    "positioning": "Positioning",
    "macro_economy": "Macro economy",
    "company_news": "Company news",
    "world_news": "World news",
}


def _flatten_summary(model: StructuredSummaryModel) -> str:
    """The outline as plain text, one line per non-empty group — what the
    legacy summary consumers (main page, stored summaries) keep."""
    lines: List[str] = []
    for group in ("summary",) + DATA_REPORTS:
        bullets = getattr(model, group)
        if not bullets:
            continue
        sentences: List[str] = []
        for bullet in bullets:
            sentences.append(bullet.text.strip())
            sentences.extend(child.text.strip() for child in bullet.children)
        lines.append(f"{_SUMMARY_GROUP_TITLES[group]}: " + " ".join(sentences))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_StageParse = Callable[[dict], Any]

#: One lister sheet after conversion + citation fixes: (vote items, still
#: broken vote item id → errors, vote item id → the field ref it grades).
_SheetResult = Tuple[List[EvidenceItemModel], Dict[str, List[str]], Dict[str, str]]


def _sheet_texts(sheet: GradeSheetModel) -> List[Optional[str]]:
    """What a reader sees of a grade sheet: the claims and score reasons."""
    texts: List[Optional[str]] = []
    for grade in sheet.grades.values():
        texts.append(getattr(grade, "claim", None))
        texts.append(getattr(grade, "score_reason", None))
    return texts


def _fix_item_texts(reply: Any) -> List[Optional[str]]:
    """What a reader sees of a citation-fix reply: the corrected claims
    and score reasons (``CitationFixModel`` or a subclass's item form)."""
    texts: List[Optional[str]] = []
    for item in reply.items:
        texts.append(getattr(item, "claim", None))
        texts.append(getattr(item, "score_reason", None))
    return texts


def _vote_texts(votes: Any) -> List[Optional[str]]:
    """What a reader sees of a vote round (or a vote citation-fix reply):
    the reasons and score reasons."""
    texts: List[Optional[str]] = []
    for vote in votes.votes.values():
        texts.append(vote.reason)
        texts.append(vote.score_reason)
    return texts


def _summary_texts(model: StructuredSummaryModel) -> List[Optional[str]]:
    """Every sentence of the report outline, children included."""
    texts: List[Optional[str]] = []
    for group in ("summary",) + DATA_REPORTS:
        for bullet in getattr(model, group):
            texts.append(bullet.text)
            texts.extend(child.text for child in bullet.children)
    return texts


class DeepAnalysisEngine:
    """Runs the v8 evidence vote. Never raises out of run()."""

    # The fix loops are shared with the tier-3 risk engine (a subclass);
    # these hooks let it swap in its own item form and prompt wording
    # while the loop mechanics stay identical.
    FIX_ITEMS_MODEL: Any = CitationFixModel
    CITATION_FIX_TEMPLATE = _CITATION_FIX_TEMPLATE
    LINK_RULES = _LINK_RULES
    VOTE_FIX_TEMPLATE = _VOTE_FIX_TEMPLATE
    VOTE_RULES = _VOTE_RULES

    def __init__(self, summarizer: Optional[Callable[[str], str]] = None) -> None:
        # Temperature 0 by default: the same evidence rules the same way.
        self._summarize = summarizer or deterministic_summarizer

    # -- public entry ------------------------------------------------------

    def run(
        self,
        ticker: str,
        tier1: TierReport,
        data_reports: Sequence[DataReport],
        max_hold_weeks: int = DEFAULT_MAX_HOLD_WEEKS,
    ) -> DeepAnalysisResult:
        context = _CONTEXT_TEMPLATE.format(
            ticker=ticker,
            hold_text=max_hold_weeks_text(max_hold_weeks),
            # The plan levels are deliberately NOT in the context (owner
            # decision 2026-09-16): the deep analysis judges the outlook from
            # citable evidence, and the levels are neither.
            # Display-formatted numbers: the model must cite what the
            # report pages show, so it only ever sees those strings.
            evidence_block=evidence_block(data_reports, display=True),
            language_rule=language_rule(),
        )
        data_report_names = [
            d.name
            for d in data_reports
            if d.name in DATA_REPORTS
            and (d.payload or d.summary or d.citations)
        ]
        warnings: List[str] = []
        items: List[Dict[str, Any]] = []
        try:
            return self._run_stages(
                context, data_reports, data_report_names, warnings, items
            )
        except Exception as exc:  # fail-loud as a structured result
            return DeepAnalysisResult(
                items=items, warnings=warnings + [f"deep analysis LLM call failed: {exc}"]
            )

    # -- the steps ---------------------------------------------------------

    def _run_stages(
        self,
        context: str,
        data_reports: Sequence[DataReport],
        data_report_names: List[str],
        warnings: List[str],
        items: List[Dict[str, Any]],
    ) -> DeepAnalysisResult:
        refs = gradable_field_refs(data_reports)
        if not refs:
            warnings.append(
                "no gradable report fields collected — tier-2 outlook voided"
            )
            return DeepAnalysisResult(items=items, warnings=warnings)

        # Step 1 — the two lister grade sheets, in parallel (blind),
        # each converted to vote items with its own citation-fix loop.
        first, second = self._listers(context, data_reports, refs, warnings)
        # These degrade notes say what happened to the run, not why: the
        # cause is already its own warning just before (invalid after
        # retry, or an LLM call that failed — 2026-10-12).
        if first is None and second is None:
            warnings.append(
                "both lister grade sheets unusable — deep-analysis outlook voided"
            )
            return DeepAnalysisResult(items=items, warnings=warnings)
        if first is None or second is None:
            which = "1" if first is None else "2"
            warnings.append(
                f"lister {which} grade sheet unusable — "
                "proceeding with the other sheet only"
            )

        # Step 2 — code merge by graded field. Same field + same
        # item outlook = listed independently by both (2-0 confirmed);
        # everything else on the second sheet joins the list.
        items.extend(self._assemble(first, second))
        for item in items:
            if item["struck"]:
                warnings.append(
                    f"vote item {item['id']}: citations unfixable after "
                    f"{MAX_FIX_ROUNDS} fix attempts — struck from the list"
                )

        # Step 3 — the check round: the second vote on single-lister
        # vote items. Vote items both listers listed are already 2-0.
        check_ids = [
            item["id"] for item in items if not item["struck"] and item["lister_count"] < 2
        ]
        if check_ids:
            votes = self._vote_round(
                _CHECK_TEMPLATE.format(
                    context=context,
                    tree=_tree_text(items),
                    vote_rules=_VOTE_RULES,
                    check_ids=", ".join(check_ids),
                ),
                check_ids,
                data_reports,
                "check round",
                warnings,
            )
            if votes is None:
                warnings.append(
                    "check round unusable — vote items counted on "
                    "their lister's vote alone"
                )
            else:
                self._attach_votes(items, votes, "checker")
        else:
            warnings.append(
                "every vote item was listed by both listers — check round skipped"
            )

        # Step 4 — the deciding round, only for 1-1 ties.
        tied_ids = [item["id"] for item in items if self._is_tied(item)]
        if tied_ids:
            by_id = {item["id"]: item for item in items}
            votes = self._vote_round(
                _DECIDER_TEMPLATE.format(
                    context=context,
                    tree=_tree_text(items),
                    disputes=_disputes_text([by_id[i] for i in tied_ids]),
                    vote_rules=_VOTE_RULES,
                    tied_ids=", ".join(tied_ids),
                ),
                tied_ids,
                data_reports,
                "deciding round",
                warnings,
            )
            if votes is None:
                warnings.append(
                    "deciding round unusable — tied vote items "
                    "excluded as unresolved"
                )
            else:
                self._attach_votes(items, votes, "decider")

        # Outcomes — pure counting of the votes — then each surviving
        # vote item's final score: the median of every voter's 1-5 rating.
        self._apply_outcomes(items, warnings)
        for item in items:
            if not item["struck"]:
                item["score"] = _median_score(
                    item["lister_scores"]
                    + [vote["score"] for vote in item["votes"]]
                )

        pools = {
            # The initial pool is the merged list BEFORE voting, so it is
            # weighted by the lister_count' own ratings alone.
            "initial": _pool_detail(
                (i for i in items if not i["struck"]),
                lambda item: _median_score(item["lister_scores"]),
            ),
            "final": _pool_detail(
                (i for i in items if i["final_status"] == "counted"),
                lambda item: item["score"],
            ),
        }
        initial_score = pools["initial"]["score"] if pools["initial"]["total"] else 5.0
        if pools["final"]["total"]:
            final = pools["final"]["score"]
        else:
            final = 5.0
            warnings.append(
                "no surviving evidence to weigh — final score is neutral 5 by default"
            )
        merged = [i for i in items if not i["struck"]]
        survivors = sum(1 for i in merged if i["final_status"] == "counted")
        if merged and survivors * 2 < len(merged):
            warnings.append(
                "most of the merged evidence did not survive the votes — "
                "the final score rests on a thin base"
            )
        outlook = outlook_from_final(final)

        # Step 5 — the user-facing report; its failure never voids anything.
        summary, summary_structure = self._summary(
            context, items, final, pools, outlook, data_report_names,
            data_reports, warnings,
        )

        outlook = DeepAnalysisOutlook(
            outlook=outlook,
            final_score=final,
            summary=summary,
            initial_score=initial_score,
            pools=pools,
            summary_structure=summary_structure,
        )
        return DeepAnalysisResult(items=items, outlook=outlook, warnings=warnings)

    # -- step 1: the two lists ---------------------------------------------

    def _listers(
        self,
        context: str,
        data_reports: Sequence[DataReport],
        refs: Dict[str, List[str]],
        warnings: List[str],
    ) -> Tuple[Optional["_SheetResult"], Optional["_SheetResult"]]:
        """Each entry: (vote items with fixes applied, still-broken map,
        vote item id → graded field ref), or None when the sheet never
        validated."""
        all_refs = [ref for data_report in refs for ref in refs[data_report]]
        blank_refs = blank_field_refs(data_reports)
        field_rows = "\n".join(f"- {ref}" for ref in all_refs)
        prompts = [
            template.format(
                context=context,
                field_rows=field_rows,
                grade_rules=_GRADE_RULES,
                link_rules=_LINK_RULES,
                shape=_GRADE_SHAPE,
            )
            for template in (_GRADER1_TEMPLATE, _GRADER2_TEMPLATE)
        ]

        def parse(parsed: dict) -> GradeSheetModel:
            model = GradeSheetModel.model_validate(parsed)
            # Grades on blank-but-real report fields are dropped, not
            # failed (see blank_field_refs); truly invented keys still
            # fail the exact-coverage check below.
            grades = {
                ref: grade
                for ref, grade in model.grades.items()
                if ref not in blank_refs
            }
            check_grade_sheet(grades, all_refs)
            return model.model_copy(update={"grades": grades})

        # The usage tracker is thread-local; hand it to the workers so
        # their calls still count toward the run's AI-calls number.
        tracker = active_tracker()

        def run_stage(prompt: str, stage: str):
            def job():
                stage_warnings: List[str] = []

                def ask(attempt_prompt: str) -> Optional[GradeSheetModel]:
                    model, call_warnings = self._call_validated(attempt_prompt, parse, stage)
                    stage_warnings.extend(call_warnings)
                    return model

                try:
                    model = in_language(ask, prompt, _sheet_texts, stage, stage_warnings)
                    if model is None:
                        return None, stage_warnings
                    sheet_items, ref_by_id = self._sheet_items(
                        model, refs, data_reports
                    )
                    fixed_items, broken = self._fix_citations(
                        sheet_items, data_reports, stage, stage_warnings,
                        ref_by_id=ref_by_id,
                    )
                    return (fixed_items, broken, ref_by_id), stage_warnings
                except LlmConfigError:
                    raise  # no key: nothing would work — fail the whole run
                except Exception as exc:
                    # A failed CALL (timeout, 5xx) degrades like an
                    # invalid sheet: this lister drops out and the other
                    # one's finished, paid work stays (review 2026-10-10
                    # — before, the error escaped the worker thread and
                    # voided the whole deep analysis).
                    stage_warnings.append(f"{stage} LLM call failed: {exc}")
                    return None, stage_warnings

            if tracker is None:
                return job()
            with tracker.activate():
                return job()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(run_stage, prompts[0], "lister 1 grade sheet"),
                pool.submit(run_stage, prompts[1], "lister 2 grade sheet"),
            ]
            (first, first_warnings), (second, second_warnings) = (
                futures[0].result(),
                futures[1].result(),
            )
        warnings.extend(first_warnings)
        warnings.extend(second_warnings)
        return first, second

    @staticmethod
    def _sheet_items(
        sheet: GradeSheetModel,
        refs: Dict[str, List[str]],
        data_reports: Sequence[DataReport],
    ) -> Tuple[List[EvidenceItemModel], Dict[str, str]]:
        """Non-neutral grades as vote items. Ids are assigned by
        code in field order; the graded field's own citation is injected
        by code with the exact display value (the AI cannot misquote its
        own field), so the fix loop only polices the claim wording and
        any extra cross-field links."""
        items: List[EvidenceItemModel] = []
        ref_by_id: Dict[str, str] = {}
        counters: Dict[str, int] = {}
        for data_report, report_refs in refs.items():
            prefix = DATA_REPORT_PREFIX[data_report]
            for ref in report_refs:
                grade = sheet.grades[ref]
                if grade.item_outlook == "neutral":
                    continue
                counters[prefix] = counters.get(prefix, 0) + 1
                item_id = f"{prefix}{counters[prefix]}"
                items.append(
                    EvidenceItemModel(
                        id=item_id,
                        data_report=data_report,
                        item_outlook=grade.item_outlook,
                        claim=(grade.claim or "").strip(),
                        links=_links_with_own(ref, grade.links, data_reports),
                        score=grade.score,
                        score_reason=grade.score_reason,
                    )
                )
                ref_by_id[item_id] = ref
        return items, ref_by_id

    # -- step 2: the code merge --------------------------------------------

    def _assemble(
        self,
        first: Optional["_SheetResult"],
        second: Optional["_SheetResult"],
    ) -> List[Dict[str, Any]]:
        """The merged vote item list, matched by graded field in pure code:
        the first sheet's vote items (lister_count=2 where the second lister
        graded the same field the same way), the second sheet's
        unmatched vote items renumbered in (a different field, or the same
        field graded the OPPOSITE way — a genuine dispute the
        votes settle), and both sheets' struck vote items kept for the
        audit trail."""
        lead_lister = 1
        if first is None:
            first, second = second, None  # the surviving sheet leads
            lead_lister = 2
        first_items, first_broken, first_refs = first

        # covered: first-sheet id → the SECOND lister's vote item for the
        # same field (how their rating and its reason ride in).
        covered: Dict[str, EvidenceItemModel] = {}
        extra_models: List[EvidenceItemModel] = []
        extra_refs: Dict[str, str] = {}
        extra_broken: Dict[str, List[str]] = {}
        if second is not None:
            second_items, second_broken, second_refs = second
            first_id_by_key = {
                (first_refs[m.id], m.item_outlook): m.id
                for m in first_items
                if m.id not in first_broken
            }
            for model in second_items:
                if model.id in second_broken:
                    extra_models.append(model)
                    extra_refs[model.id] = second_refs[model.id]
                    extra_broken[model.id] = second_broken[model.id]
                    continue
                target = first_id_by_key.get(
                    (second_refs[model.id], model.item_outlook)
                )
                if target is not None:
                    covered[target] = model
                else:
                    extra_models.append(model)
                    extra_refs[model.id] = second_refs[model.id]

        # Renumber second-sheet vote items to continue the first sheet's ids.
        next_number: Dict[str, int] = {}
        for model in first_items:
            prefix = DATA_REPORT_PREFIX[model.data_report]
            next_number[prefix] = max(
                next_number.get(prefix, 0), int(model.id[len(prefix):])
            )
        items: List[Dict[str, Any]] = []
        for model in first_items:
            second_model = covered.get(model.id)
            items.append(
                self._base_item(
                    model,
                    first_broken.get(model.id),
                    lister_count=2 if second_model is not None else 1,
                    lister_no=lead_lister,
                    second_model=second_model,
                    field=first_refs.get(model.id),
                )
            )
        for model in extra_models:
            prefix = DATA_REPORT_PREFIX[model.data_report]
            next_number[prefix] = next_number.get(prefix, 0) + 1
            renumbered = model.model_copy(update={"id": f"{prefix}{next_number[prefix]}"})
            items.append(
                self._base_item(
                    renumbered,
                    extra_broken.get(model.id),
                    lister_count=1,
                    lister_no=2,
                    field=extra_refs.get(model.id),
                )
            )
        return items

    # -- citation verification + the fix loops -----------------------------

    def _text_link_errors(
        self,
        links: Sequence[Any],
        sentence: str,
        where_prefix: str,
        data_reports: Sequence[DataReport],
    ) -> List[str]:
        """Everything code checks about one sentence's links, phrased for
        the fix prompt. Empty list → the citations are good."""
        errors: List[str] = []
        for link in links:
            ref = link.ref.strip()
            where = f"{where_prefix} link {ref!r}"
            resolves, actual = _payload_value(ref, data_reports)
            if not resolves:
                errors.append(f"{where}: does not resolve to a single report value")
                continue
            if _is_textual_ref(ref, data_reports):
                continue  # a news-event anchor; no display value to copy
            expected = display_value(actual)
            claimed = _link_value_text(link.value)
            if not _values_equal(claimed, expected):
                errors.append(
                    f"{where}: claimed value {claimed!r} must be copied exactly "
                    f"as the report displays it: {expected!r}"
                )
                continue
            if not _value_in_text(expected, sentence):
                errors.append(
                    f"{where}: the value {expected!r} must appear in the "
                    "sentence exactly as the report displays it"
                )
        return errors

    def _link_errors(
        self, item: EvidenceItemModel, data_reports: Sequence[DataReport]
    ) -> List[str]:
        return self._text_link_errors(
            item.links, item.claim, f"item {item.id}", data_reports
        )

    def _vote_errors(
        self, key: str, vote: VoteModel, data_reports: Sequence[DataReport]
    ) -> List[str]:
        reason = vote.reason or ""
        errors = self._text_link_errors(
            vote.links, reason, f"vote {key}", data_reports
        )
        if _NUMERIC_REASON_RE.search(reason) and not vote.links:
            errors.append(
                f"vote {key}: the reason states a number — cite it with a link"
            )
        return errors

    def _fix_citations(
        self,
        items: Sequence[EvidenceItemModel],
        data_reports: Sequence[DataReport],
        stage: str,
        warnings: List[str],
        ref_by_id: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[EvidenceItemModel], Dict[str, List[str]]]:
        """Run the code citation check, send broken vote items back to the
        same AI (only the broken ones), splice fixes in, repeat up to
        MAX_FIX_ROUNDS. Returns (items with fixes applied, still-broken
        id → errors). Successful fixes leave no trace — the UI shows only
        the end state.

        ``ref_by_id`` (vote item id → the field it grades) keeps the
        graded field's own link code's through the fix rounds: a fix
        reply may drop or repoint it, and the item still verified on its
        remaining links, so the stored vote item named field X with no
        link to X (review 2026-10-10)."""
        fixed = list(items)
        index_by_id = {item.id: index for index, item in enumerate(fixed)}
        broken: Dict[str, List[str]] = {}
        for item in fixed:
            errors = self._link_errors(item, data_reports)
            if errors:
                broken[item.id] = errors
        rounds = 0
        while broken and rounds < MAX_FIX_ROUNDS:
            rounds += 1
            prompt = self.CITATION_FIX_TEMPLATE.format(
                evidence=evidence_block(data_reports, display=True),
                link_rules=self.LINK_RULES,
                language_rule=language_rule(),
                items=_items_json([fixed[index_by_id[i]] for i in broken]),
                errors="\n".join(
                    f"- {item_id}: {'; '.join(errors)}"
                    for item_id, errors in broken.items()
                ),
            )
            reply = self._fix_round(
                prompt, self.FIX_ITEMS_MODEL.model_validate, self.FIX_ITEMS_MODEL,
                _fix_item_texts, stage, warnings,
            )
            if reply is None:
                continue
            for candidate in reply.items:
                if candidate.id not in broken:
                    continue  # untouched vote items must not be churned
                original = fixed[index_by_id[candidate.id]]
                if candidate.data_report != original.data_report:
                    continue  # id and data_report are frozen
                # The lister's importance rating is frozen too — a fix
                # round is about citations, and a reply that omits
                # "score" must not silently reset a 5 to the default.
                candidate = candidate.model_copy(
                    update={
                        "score": original.score,
                        "score_reason": original.score_reason,
                    }
                )
                field = (ref_by_id or {}).get(candidate.id)
                if field is not None:
                    candidate = candidate.model_copy(
                        update={
                            "links": _links_with_own(
                                field, candidate.links, data_reports
                            ),
                        }
                    )
                fixed[index_by_id[candidate.id]] = candidate
                errors = self._link_errors(candidate, data_reports)
                if errors:
                    broken[candidate.id] = errors
                else:
                    del broken[candidate.id]
        return fixed, broken

    def _fix_votes(
        self,
        votes: Dict[str, VoteModel],
        data_reports: Sequence[DataReport],
        stage: str,
        warnings: List[str],
    ) -> Dict[str, VoteModel]:
        """The same fix loop for vote reasons. Votes still broken after
        the rounds are DISCARDED (with a warning) — an objection that
        cannot back its numbers carries no score."""
        fixed = dict(votes)
        broken: Dict[str, List[str]] = {}
        for key, vote in fixed.items():
            errors = self._vote_errors(key, vote, data_reports)
            if errors:
                broken[key] = errors
        rounds = 0
        while broken and rounds < MAX_FIX_ROUNDS:
            rounds += 1
            prompt = self.VOTE_FIX_TEMPLATE.format(
                evidence=evidence_block(data_reports, display=True),
                vote_rules=self.VOTE_RULES,
                language_rule=language_rule(),
                votes=json.dumps(
                    {key: fixed[key].model_dump(exclude_none=True) for key in broken},
                    ensure_ascii=False,
                    indent=1,
                ),
                errors="\n".join(
                    f"- {key}: {'; '.join(errors)}" for key, errors in broken.items()
                ),
            )
            # Votes key on run-time vote item ids — JSON mode, not schema.
            reply = self._fix_round(
                prompt, VoteFixModel.model_validate, JSON_REPLY,
                _vote_texts, stage, warnings,
            )
            if reply is None:
                continue
            for key, candidate in reply.votes.items():
                if key not in broken:
                    continue
                # The voter's importance rating is frozen through fixes
                # (same reason as vote item scores: no silent resets).
                fixed[key] = candidate.model_copy(
                    update={
                        "score": fixed[key].score,
                        "score_reason": fixed[key].score_reason,
                    }
                )
                errors = self._vote_errors(key, candidate, data_reports)
                if errors:
                    broken[key] = errors
                else:
                    del broken[key]
        for key in broken:
            warnings.append(
                f"vote on {key} discarded — citations unfixable after "
                f"{MAX_FIX_ROUNDS} fix attempts"
            )
            del fixed[key]
        return fixed

    # -- steps 3-4: the vote rounds ----------------------------------------

    def _vote_round(
        self,
        prompt: str,
        required_ids: List[str],
        data_reports: Sequence[DataReport],
        stage: str,
        warnings: List[str],
    ) -> Optional[Dict[str, VoteModel]]:
        def parse(parsed: dict) -> VoteRoundModel:
            model = VoteRoundModel.model_validate(parsed)
            check_exact_keys(list(model.votes), required_ids, "votes")
            return model

        def ask(attempt_prompt: str) -> Optional[VoteRoundModel]:
            model, stage_warnings = self._call_validated(attempt_prompt, parse, stage)
            warnings.extend(stage_warnings)
            return model

        try:
            model = in_language(ask, prompt, _vote_texts, stage, warnings)
            if model is None:
                return None
            return self._fix_votes(model.votes, data_reports, stage, warnings)
        except LlmConfigError:
            raise  # no key: nothing would work — fail the whole run
        except Exception as exc:
            # A failed call degrades like an invalid round: the callers'
            # "round invalid" branches apply (vote items counted on the
            # lister alone / ties excluded) instead of voiding everything
            # (review 2026-10-10).
            warnings.append(f"{stage} LLM call failed: {exc}")
            return None

    @staticmethod
    def _attach_votes(
        items: List[Dict[str, Any]], votes: Dict[str, VoteModel], role: str
    ) -> None:
        by_id = {item["id"]: item for item in items}
        for key, vote in votes.items():
            reason = (vote.reason or "").strip()
            by_id[key]["votes"].append(
                {
                    "role": role,
                    "validity": vote.validity,
                    "reason": reason or None,
                    "score": vote.score,
                    "score_reason": vote.score_reason,
                    "links": [
                        _link_detail(link) for link in vote.links
                    ],
                }
            )

    @staticmethod
    def _vote_by_role(item: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
        return next((v for v in item["votes"] if v["role"] == role), None)

    def _is_tied(self, item: Dict[str, Any]) -> bool:
        """1-1: the lister's implicit valid vote vs an invalid check vote."""
        if item["struck"] or item["lister_count"] >= 2:
            return False
        checker = self._vote_by_role(item, "checker")
        return checker is not None and checker["validity"] == "invalid"

    def _apply_outcomes(
        self, items: List[Dict[str, Any]], warnings: List[str]
    ) -> None:
        """Majority of votes decides; the lister is always a valid vote."""
        for item in items:
            if item["struck"]:
                continue  # excluded by code before any voting
            if item["lister_count"] >= 2:
                item["final_status"] = "counted"  # 2-0 at birth
                continue
            checker = self._vote_by_role(item, "checker")
            if checker is None or checker["validity"] == "valid":
                # No second vote cast (degraded/discarded) → the lister's
                # vote stands unopposed; a valid check vote → 2-0.
                item["final_status"] = "counted"
                continue
            decider = self._vote_by_role(item, "decider")
            if decider is None:
                item["final_status"] = "excluded"
                item["exclusion_reason"] = "unresolved"
                warnings.append(
                    f"no deciding vote for {item['id']} — excluded as unresolved"
                )
            elif decider["validity"] == "valid":
                item["final_status"] = "counted"  # 2-1
            else:
                item["final_status"] = "excluded"  # 1-2
                item["exclusion_reason"] = "outvoted"

    # -- step 5 ------------------------------------------------------------

    def _summary_link_errors(
        self,
        model: StructuredSummaryModel,
        data_reports: Sequence[DataReport],
    ) -> Dict[str, List[str]]:
        """The evidence-list citation contract, applied to every report
        sentence: links verify mechanically, and a sentence that states a
        report-style number must carry one."""
        errors: Dict[str, List[str]] = {}

        def check(where: str, text: str, links: Sequence[LinkModel]) -> None:
            sentence_errors = self._text_link_errors(links, text, where, data_reports)
            if _NUMERIC_REASON_RE.search(text) and not links:
                sentence_errors.append(
                    f"{where}: the sentence states a number — cite it with a link"
                )
            if sentence_errors:
                errors[where] = sentence_errors

        for group in ("summary",) + DATA_REPORTS:
            for index, bullet in enumerate(getattr(model, group)):
                where = f"{group}[{index}]"
                check(where, bullet.text, bullet.links)
                for child_index, child in enumerate(bullet.children):
                    check(f"{where}.child[{child_index}]", child.text, child.links)
        return errors

    @staticmethod
    def _prune_summary_links(
        model: StructuredSummaryModel,
        keep: Callable[[str, Sequence[LinkModel]], List[LinkModel]],
    ) -> StructuredSummaryModel:
        """A copy with each sentence's links filtered through ``keep``."""
        update: Dict[str, Any] = {}
        for group in ("summary",) + DATA_REPORTS:
            bullets = []
            for bullet in getattr(model, group):
                bullets.append(
                    bullet.model_copy(
                        update={
                            "links": keep(bullet.text, bullet.links),
                            "children": [
                                child.model_copy(
                                    update={"links": keep(child.text, child.links)}
                                )
                                for child in bullet.children
                            ],
                        }
                    )
                )
            update[group] = bullets
        return model.model_copy(update=update)

    def _summary(
        self,
        context: str,
        items: Sequence[Dict[str, Any]],
        final: float,
        pools: Dict[str, Any],
        outlook: Outlook,
        data_report_names: Sequence[str],
        data_reports: Sequence[DataReport],
        warnings: List[str],
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """(flat text for legacy consumers, fixed-outline dump) — both
        empty/None when the stage failed; the computed outlook stands."""
        prompt = _SUMMARY_TEMPLATE.format(
            context=context,
            tree=_tree_text(items),
            final=f"{final:.2f}",
            final_bullish=pools["final"]["bullish"],
            final_bearish=pools["final"]["bearish"],
            final_total=pools["final"]["total"],
            final_bullish_score_sum=pools["final"]["bullish_score_sum"],
            final_total_score_sum=pools["final"]["total_score_sum"],
            outlook=outlook.value,
            fill_groups=", ".join(
                dim for dim in DATA_REPORTS if dim in data_report_names
            ) or "none",
        )

        def parse(parsed: dict) -> StructuredSummaryModel:
            # A group the model left out counts as empty; whether it was
            # allowed to be empty is check_summary_groups' call.
            filled = {**{group: [] for group in DATA_REPORTS}, **parsed}
            model = StructuredSummaryModel.model_validate(filled)
            check_summary_groups(model, data_report_names)
            return model

        try:
            stage_warnings: List[str] = []

            def ask(attempt_prompt: str) -> Optional[StructuredSummaryModel]:
                model, call_warnings = self._call_validated(
                    attempt_prompt, parse, "report outline",
                    schema=StructuredSummaryModel,  # fixed outline: enforceable
                )
                stage_warnings.extend(call_warnings)
                return model

            model = in_language(ask, prompt, _summary_texts, "report outline", stage_warnings)
            if model is None:
                # Keep the long-standing wording (and its friendly gloss)
                # instead of the stage's voided-sounding warnings — a
                # summary failure never voids the computed outlook.
                warnings.append("judge summary unparseable — computed outlook stands")
                return "", None
            warnings.extend(stage_warnings)

            # The citation fix loop, same mechanics as vote items and votes:
            # broken links go back to the AI; links still broken after
            # the rounds are dropped (the sentence stays, unlinked).
            errors = self._summary_link_errors(model, data_reports)
            rounds = 0
            while errors and rounds < MAX_FIX_ROUNDS:
                rounds += 1
                fix_prompt = (
                    f"{prompt}\n\nYour previous summary failed the code's "
                    "citation check:\n"
                    + "\n".join(
                        f"- {where}: {'; '.join(sentence_errors)}"
                        for where, sentence_errors in errors.items()
                    )
                    + "\nReply again with the FULL corrected JSON, same shape. "
                    "JSON only."
                )
                fixed_model = self._fix_round(
                    fix_prompt, parse, StructuredSummaryModel,
                    _summary_texts, "summary", warnings,
                )
                if fixed_model is None:
                    continue
                model = fixed_model
                errors = self._summary_link_errors(model, data_reports)
            if errors:
                model = self._prune_summary_links(
                    model,
                    lambda text, links: [
                        link
                        for link in links
                        if not self._text_link_errors([link], text, "x", data_reports)
                    ],
                )
                warnings.append(
                    "summary citations unfixable — those values are shown "
                    "without links"
                )
        except Exception as exc:
            warnings.append(f"summary LLM call failed: {exc} — computed outlook stands")
            return "", None
        return _flatten_summary(model), model.model_dump()

    # -- shared plumbing ---------------------------------------------------

    def _fix_round(
        self,
        prompt: str,
        parse: _StageParse,
        schema: Any,
        texts_of: Callable[[Any], Iterable[Optional[str]]],
        stage: str,
        warnings: List[str],
    ) -> Optional[Any]:
        """One citation-fix call: the reply parsed with ``parse`` and,
        like every stage that writes reader-facing text, checked for the
        run's language — a fix written in the wrong language goes back
        with a correction (``in_language``, up to LANGUAGE_RETRY_LIMIT
        times) before its sentences are spliced into the report. None,
        with the "fix round lost" warning, when no reply parsed."""

        def ask(attempt_prompt: str) -> Optional[Any]:
            parsed = parse_llm_json(
                summarize_with_schema(self._summarize, attempt_prompt, schema)
            )
            if parsed is None:
                return None
            try:
                return parse(parsed)
            except (ValidationError, ValueError):
                return None

        reply = in_language(ask, prompt, texts_of, f"{stage} citation fix", warnings)
        if reply is None:
            warnings.append(f"{stage} citation-fix reply invalid — fix round lost")
        return reply

    def _call_validated(
        self, prompt: str, parse: _StageParse, stage: str,
        schema: Any = JSON_REPLY,
    ) -> Tuple[Optional[Any], List[str]]:
        """One LLM call against a Pydantic form, with ONE retry that shows
        the model its validation errors. Returns (model|None, warnings).

        ``schema`` is handed to the provider for decode-time enforcement
        (2026-08-25): the default ``JSON_REPLY`` guarantees valid JSON —
        most deep analysis forms key on run-time ids (one grade per field ref,
        one vote per vote item id), which no decode-time schema can name —
        and fixed-shape stages pass their pydantic form for full
        enforcement."""
        error = None
        raw = summarize_with_schema(self._summarize, prompt, schema)
        parsed = parse_llm_json(raw)
        if parsed is None:
            error = "the reply was not a JSON object"
        else:
            try:
                return parse(parsed), []
            except (ValidationError, ValueError) as exc:
                error = _validation_text(exc)

        retry_prompt = (
            f"{prompt}\n\nYour previous reply was invalid: {error}\n"
            "Reply again, following the JSON shape exactly. JSON only."
        )
        raw = summarize_with_schema(self._summarize, retry_prompt, schema)
        parsed = parse_llm_json(raw)
        if parsed is None:
            return None, [f"{stage} was not JSON even after a retry"]
        try:
            return (
                parse(parsed),
                [f"{stage} needed a retry — first reply was invalid"],
            )
        except (ValidationError, ValueError) as exc:
            return None, [f"{stage} invalid after retry: {_validation_text(exc)}"]

    @staticmethod
    def _base_item(
        model: EvidenceItemModel,
        problems: Optional[List[str]],
        lister_count: int,
        lister_no: int = 1,
        second_model: Optional[EvidenceItemModel] = None,
        field: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One list vote item. ``problems`` non-empty → the vote item is struck:
        code could not fix its citations, so it renders crossed out and
        never enters a pool. ``lister_count`` = how many listers listed it
        independently (2 = confirmed at birth); ``lister_no`` = which
        lister wrote it (1 or 2); ``second_model`` is the second lister's
        own vote item for the same evidence when both listed it; ``field``
        is the report field ref the vote item grades (v12)."""
        struck = bool(problems)
        lister_votes = [
            {
                "lister": lister_no,
                "score": model.score,
                "score_reason": model.score_reason,
            }
        ]
        if second_model is not None:
            lister_votes.append(
                {
                    "lister": 2,
                    "score": second_model.score,
                    "score_reason": second_model.score_reason,
                }
            )
        lister_scores = [vote["score"] for vote in lister_votes]
        return {
            "id": model.id,
            "data_report": model.data_report,
            "field": field,
            "item_outlook": model.item_outlook,
            "claim": model.claim.strip(),
            "links": [_link_detail(link) for link in model.links],
            "struck": struck,
            "problems": list(problems or []),
            "lister_count": lister_count,
            # Per-lister rating detail (v11) and the bare score list the
            # pools consume (kept alongside, same order).
            "lister_votes": lister_votes,
            "lister_scores": lister_scores,
            # The final median of every voter's rating — filled once all
            # the votes are in (None while struck: no pool, no score).
            "score": None,
            "votes": [],
            "final_status": "excluded" if struck else None,
            "exclusion_reason": "citation_failed" if struck else None,
        }


# ---------------------------------------------------------------------------
# Pool counting
# ---------------------------------------------------------------------------


def _median_score(scores: Sequence[float]) -> Optional[float]:
    """The median of the voters' 1-5 ratings; an even count takes the
    mean of the middle two, so halves (2.5) happen. Whole results come
    back as ints so the stored JSON stays clean."""
    if not scores:
        return None
    ordered = sorted(scores)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        value = float(ordered[middle])
    else:
        value = (ordered[middle - 1] + ordered[middle]) / 2.0
    return int(value) if value.is_integer() else value


def _pool_detail(items, score_of) -> Dict[str, Any]:
    """Weighted counting: 10 × Σweight(bullish) / Σweight(all) over the
    whole pool, ``score_of`` supplying each vote item's score. The
    per-data_report counts and score sums feed the section headers
    (`Technicals: ↑3 ↓4`)."""
    per_data_report: Dict[str, Dict[str, Any]] = {}
    for item in items:
        stats = per_data_report.setdefault(
            item["data_report"],
            {"bullish": 0, "bearish": 0, "total": 0,
             "bullish_score_sum": 0, "bearish_score_sum": 0, "total_score_sum": 0},
        )
        side = "bullish" if item["item_outlook"] == "bullish" else "bearish"
        score = score_of(item)
        stats["total"] += 1
        stats[side] += 1
        stats["total_score_sum"] += score
        stats[f"{side}_score_sum"] += score
    bullish = bearish = total = 0
    bullish_score_sum = bearish_score_sum = total_score_sum = 0
    for data_report in DATA_REPORTS:
        stats = per_data_report.get(data_report)
        if not stats:
            continue
        for key in ("total_score_sum", "bullish_score_sum", "bearish_score_sum"):
            stats[key] = _int_when_whole(stats[key])
        bullish += stats["bullish"]
        bearish += stats["bearish"]
        total += stats["total"]
        bullish_score_sum += stats["bullish_score_sum"]
        bearish_score_sum += stats["bearish_score_sum"]
        total_score_sum += stats["total_score_sum"]
    return {
        "data_reports": per_data_report,
        "bullish": bullish,
        "bearish": bearish,
        "total": total,
        "bullish_score_sum": _int_when_whole(bullish_score_sum),
        "bearish_score_sum": _int_when_whole(bearish_score_sum),
        "total_score_sum": _int_when_whole(total_score_sum),
        "score": round(10 * bullish_score_sum / total_score_sum, 2)
        if total_score_sum
        else None,
    }


def _int_when_whole(value: float) -> float:
    return int(value) if float(value).is_integer() else value


# ---------------------------------------------------------------------------
# Prompt-side rendering helpers
# ---------------------------------------------------------------------------


def _validation_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        return "; ".join(parts) or str(exc)
    return str(exc)


def _links_with_own(
    field: str,
    links: Sequence[LinkModel],
    data_reports: Sequence[DataReport],
) -> List[LinkModel]:
    """A vote item's links with the graded field's own citation first,
    injected by code with the exact display value (the AI cannot
    misquote its own field); any link the AI wrote for that same field
    is replaced, cross-field links stay."""
    _resolves, value = _payload_value(field, data_reports)
    own_link = LinkModel(ref=field, value=display_value(value))
    return [own_link, *[link for link in links if link.ref.strip() != field]]


def _link_detail(link) -> Dict[str, Any]:
    """The stored link shape: the ref plus its display-string value."""
    return {"ref": link.ref.strip(), "value": _link_value_text(link.value)}


def _items_json(items: Sequence[EvidenceItemModel]) -> str:
    return json.dumps(
        [item.model_dump(exclude_none=True) for item in items],
        ensure_ascii=False,
        indent=1,
    )


def _links_text(links: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for link in links:
        if link.get("value") is not None:
            parts.append(f"{link['ref']} = {link['value']}")
        else:
            parts.append(link["ref"])
    return "; ".join(parts)


def _vote_text(vote: Dict[str, Any]) -> str:
    text = vote["validity"]
    if vote["reason"]:
        text += f" — {vote['reason']}"
    if vote["links"]:
        text += f" [{_links_text(vote['links'])}]"
    return text


def _tree_text(items: Sequence[Dict[str, Any]]) -> str:
    """The merged list as indented text for the vote/summary prompts.
    Struck vote items sit out and are omitted."""
    lines: List[str] = []
    for data_report in DATA_REPORTS:
        group = [
            i for i in items if i["data_report"] == data_report and not i["struck"]
        ]
        if not group:
            continue
        lines.append(f"- {data_report}")
        for item in group:
            source = (
                "listed by BOTH listers" if item["lister_count"] >= 2 else "one lister"
            )
            lines.append(
                f"  - [{item['id']}] ({item['item_outlook']}, {source}) {item['claim']}"
            )
            if item["links"]:
                lines.append(f"    links: {_links_text(item['links'])}")
            for vote in item["votes"]:
                lines.append(f"    - {vote['role']} vote: {_vote_text(vote)}")
    return "\n".join(lines) if lines else "(no evidence was listed)"


def _disputes_text(tied_items: Sequence[Dict[str, Any]]) -> str:
    """Claim + objection for every tied vote item, for the deciding prompt."""
    lines: List[str] = []
    for item in tied_items:
        checker = next(v for v in item["votes"] if v["role"] == "checker")
        lines.append(
            f"- [{item['id']}] claim ({item['item_outlook']}): {item['claim']}\n"
            f"  objection: {checker['reason'] or '(no reason given)'}"
        )
    return "\n".join(lines) if lines else "(none)"
