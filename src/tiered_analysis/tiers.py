# -*- coding: utf-8 -*-
"""Tier stages.

Deterministic orchestration: every failure surfaces as an explicit
UNKNOWN-outlook report with warnings (fail-loud), never an exception
swallowed mid-pipeline.

Tier 1 (the one-call preliminary analysis) lives in ``preliminary_analysis.py`` since
2026-08-10 — the legacy stage that delegated to the DSA single-shot
analysis is retired, so this package no longer touches the DSA decision
path at all.

Tier 2 (the evidence vote) runs the tiered package's own LLM engine.
Outlook redesign (2026-07-20): tier 3 is retired — the deterministic
risk card replaced it — and a failed deep analysis no longer falls back
to a weaker judge; the run fails honestly instead.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .providers.base import DataReport, Market
from .schema import Outlook, TradePlanLevels, TierReport


@dataclass
class TierState:
    """Shared state threaded through the tier stages for one ticker."""

    ticker: str
    market: Market
    reports: Dict[int, TierReport] = field(default_factory=dict)
    #: Collected data_report results, set by the orchestration layer so
    #: higher tiers can vote over the evidence (falls back to the
    #: data_reports attached to the tier-1 report when unset).
    data_reports: List[DataReport] = field(default_factory=list)
    #: Max hold time in weeks (per-run input, 2026-08-08): the deep analysis
    #: judges evidence against this horizon and the grader scores at it.
    max_hold_weeks: int = 2


class TierStage(ABC):
    tier: int

    @abstractmethod
    def run(self, state: TierState) -> TierReport:
        """Produce this tier's report; failures return UNKNOWN-outlook
        reports with explicit warnings."""


class Tier2Stage(TierStage):
    """The evidence vote over the collected data_reports (v2 slice 4).

    The engine is injected for tests; the default is a lazy DeepAnalysisEngine
    (the tiered package's own LLM calls). Any failure — no foundation
    report, no evidence, LLM down — is a report with an UNKNOWN
    outlook and explicit warnings. There is deliberately no
    fallback to the tier-1 one-blob outlook: substituting the weakest
    judge when the best one fails would present a downgrade as a result.
    """

    tier = 2

    def __init__(self, engine: Optional[Any] = None) -> None:
        self._engine = engine

    def _failed(self, state: TierState, levels: TradePlanLevels,
                warnings: List[str], detail: Optional[Dict[str, Any]] = None
                ) -> TierReport:
        return TierReport(
            tier=self.tier,
            ticker=state.ticker,
            market=state.market,
            outlook=Outlook.NO_OUTLOOK,
            levels=levels,
            warnings=warnings,
            detail=detail,
        )

    def run(self, state: TierState) -> TierReport:
        foundation = state.reports.get(1)
        if foundation is None:
            return self._failed(
                state, TradePlanLevels(),
                ["tier 2 requires the data-layer foundation report"],
            )

        data_reports = state.data_reports or foundation.data_reports
        if not data_reports:
            return self._failed(
                state, foundation.levels,
                ["no collected evidence to vote on — no outlook (re-run)"],
            )

        engine = self._engine
        if engine is None:
            from .deep_analysis import DeepAnalysisEngine

            engine = DeepAnalysisEngine()
        result = engine.run(
            state.ticker, foundation, data_reports, max_hold_weeks=state.max_hold_weeks
        )

        if result.outlook is None:
            return self._failed(
                state, foundation.levels,
                list(result.warnings)
                + ["deep analysis produced no outlook (re-run)"],
                detail=result.to_detail(),
            )

        outlook = result.outlook
        return TierReport(
            tier=self.tier,
            ticker=state.ticker,
            market=state.market,
            outlook=outlook.outlook,
            # The outlook is computed by formula from the vote outcomes,
            # so there is no judge confidence — the score lives in
            # detail.outlook.final_score.
            confidence=None,
            score=foundation.score,
            levels=foundation.levels,
            summary=outlook.summary or None,
            warnings=list(result.warnings),
            detail=result.to_detail(),
        )
