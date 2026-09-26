# -*- coding: utf-8 -*-
"""Tier-1 preliminary analysis: one LLM call over the collected evidence.

Until 2026-08-10 the preliminary tier delegated to the legacy DSA one-blob
analysis, which gathered its own inputs and never saw the user's max
hold time. The owner is separating the tiered (alt) pipeline from the
legacy app, so the preliminary tier now runs the tiered package's own judge:
a single call that reads the SAME data_reports the deep analysis
reads, judges them against the SAME hold horizon, and scores on the
SAME 0-10 scale with the same outlook cut-points (``deep_analysis.BEARISH_BELOW``
/ ``deep_analysis.NEUTRAL_MAX``).

That makes preliminary vs deep a clean experiment: same evidence, same
horizon, same scale — one judge in one call versus the multi-persona
deep analysis. The outlook travels on ``TierReport.detail`` in a
distinct ``preliminary-1`` format so the signal logger picks up the score
(and score band) through the exact same door as the deep analysis's.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel

from .deep_analysis import outlook_from_final
from .llm_support import (
    LlmConfigError,
    deterministic_summarizer,
    evidence_block,
    in_language,
    language_rule,
    parse_llm_json,
    summarize_with_schema,
)
from .providers.base import DataReport
from .schema import (
    Outlook,
    coerce_price,
    max_hold_weeks_text,
)

logger = logging.getLogger(__name__)

#: Stored-detail format marker (``report.detail.format``). A
#: string, deliberately outside the deep analysis's numeric format lineage —
#: the web's vote-tree renderers key on numeric formats and must
#: never try to render a preliminary outlook as a deep analysis.
PRELIMINARY_DETAIL_FORMAT = "preliminary-1"

#: One honest retry: the judge runs at temperature 0, so a bare re-ask
#: would reproduce the same broken reply — the retry appends the
#: rejection reason to break the loop.
MAX_ATTEMPTS = 2

_PROMPT_TEMPLATE = """You are the sole analyst judging a swing trade on {ticker}.
The position would be held for up to {hold_text} (the user's chosen max
hold time) — judge every piece of evidence against that horizon.

Collected evidence (the ONLY facts you may use — no outside knowledge):
{evidence}

Weigh the bullish and bearish evidence for this horizon and reply with
JSON only:
{{"score": <number 0-10, up to 2 decimals>, "summary": "<3-6 plain sentences>"}}

Rules:
- "score" is your overall outlook for holding up to {hold_text}: below
  4 = bearish (exit region), 4-6 = neutral (wait region), above 6 =
  bullish (buy region). Use the full scale; reserve scores under 2 or
  over 8 for strong, well-supported cases.
- "summary" states the outlook and the strongest evidence both for and
  against it, in plain language a non-finance reader can follow.
- Any number you state in the summary must appear in the evidence
  above EXACTLY as displayed there; never invent or recompute numbers.
  Write values as plain numbers in the sentences — do not wrap them in
  quotation marks.
- No text outside the JSON object.
{language_rule}
"""

_RETRY_TEMPLATE = """{prompt}
Your previous reply was rejected: {problem}
Reply again with ONLY the required JSON object.
"""


class _PreliminaryReplyForm(BaseModel):
    """The judge's wire shape, handed to the provider for decode-time
    enforcement (structured output mode, 2026-08-25). The range and
    non-empty checks in ``_parse_outlook`` stay the validator behind
    the existing show-the-problem retry."""

    score: float
    summary: str


@dataclass(frozen=True)
class PreliminaryOutlook:
    """The one-call judge's decision on the deep analysis's 0-10 scale."""

    outlook: Outlook
    final_score: float
    summary: str


@dataclass(frozen=True)
class PreliminaryResult:
    """Outcome of one preliminary-analysis run — failures are warnings, never
    exceptions (the pipeline's fail-loud contract)."""

    outlook: Optional[PreliminaryOutlook] = None
    warnings: List[str] = field(default_factory=list)

    def to_detail(self) -> Dict[str, Any]:
        """JSON-ready outlook for ``report.detail`` — the same
        ``outlook.final_score`` shape the signal logger reads from deep
        runs, under the preliminary format marker."""
        detail: Dict[str, Any] = {"format": PRELIMINARY_DETAIL_FORMAT}
        if self.outlook is not None:
            detail["outlook"] = {
                "outlook": self.outlook.outlook.value,
                "final_score": self.outlook.final_score,
            }
        return detail


def _parse_outlook(raw: str) -> Tuple[Optional[PreliminaryOutlook], Optional[str]]:
    """Validate one reply; returns ``(outlook, None)`` or ``(None, why)``."""
    parsed = parse_llm_json(raw)
    if parsed is None:
        return None, "reply is not a JSON object"
    score = coerce_price(parsed.get("score"))
    if score is None or not 0.0 <= score <= 10.0:
        return None, f"score must be a number 0-10, got {parsed.get('score')!r}"
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None, "summary must be a non-empty string"
    score = round(score, 2)
    return (
        PreliminaryOutlook(
            outlook=outlook_from_final(score),
            final_score=score,
            summary=summary.strip(),
        ),
        None,
    )


class PreliminaryAnalysis:
    """One LLM call, one outlook; the summarizer is a test seam."""

    def __init__(
        self,
        summarizer: Callable[[str], str] = deterministic_summarizer,
    ) -> None:
        self._summarize = summarizer

    def run(
        self,
        ticker: str,
        data_reports: Sequence[DataReport],
        max_hold_weeks: int,
    ) -> PreliminaryResult:
        # The judge sees the hold horizon and the evidence only. The
        # formula plan levels used to ride along (owner decision
        # 2026-09-16: removed — the judge is asked for an outlook, not a
        # plan, and the levels are not citable evidence).
        prompt = _PROMPT_TEMPLATE.format(
            ticker=ticker,
            hold_text=max_hold_weeks_text(max_hold_weeks),
            evidence=evidence_block(data_reports, display=True),
            language_rule=language_rule(),
        )
        warnings: List[str] = []
        try:
            # The summary is read by the chat bot, so it must be in the
            # run's language too: a wrong-language reply goes back with a
            # correction, the same way a malformed one does.
            outlook = in_language(
                lambda attempt_prompt: self._ask(ticker, attempt_prompt, warnings),
                prompt, lambda found: [found.summary], "preliminary analysis", warnings,
            )
        except LlmConfigError as exc:
            return PreliminaryResult(warnings=warnings + [str(exc)])
        if outlook is not None:
            return PreliminaryResult(outlook=outlook, warnings=warnings)
        return PreliminaryResult(
            warnings=warnings + ["preliminary analysis produced no outlook (re-run)"]
        )

    def _ask(
        self, ticker: str, prompt: str, warnings: List[str]
    ) -> Optional[PreliminaryOutlook]:
        """The judge's call with its show-the-problem retry
        (``MAX_ATTEMPTS`` in all): the outlook, or None when no attempt
        parsed. A missing model configuration propagates."""
        attempt_prompt = prompt
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw = summarize_with_schema(
                    self._summarize, attempt_prompt, _PreliminaryReplyForm
                )
            except LlmConfigError:
                raise
            except Exception as exc:
                logger.warning("preliminary analysis LLM call failed for %s: %s", ticker, exc)
                warnings.append(f"preliminary analysis LLM call failed: {exc}")
                continue
            outlook, problem = _parse_outlook(raw)
            if outlook is not None:
                return outlook
            warnings.append(f"preliminary analysis reply rejected: {problem}")
            attempt_prompt = _RETRY_TEMPLATE.format(prompt=prompt, problem=problem)
        return None
