# -*- coding: utf-8 -*-
"""Production wiring for tiered analysis.

This module makes the real connections the slices deliberately left
open, always as a CLIENT of existing DSA layers (boundary rule: never
import into or modify the decision path itself):

- ``dsa_bars_loader``: daily OHLCV bars for the technicals provider via
  ``DataFetcherManager`` (the existing multi-source failover layer).
- ``run_tiered_analysis``: the one-call orchestrator — collect the
  data_reports (four numeric + the textual company-events card), compute
  formula levels, run the chosen judge (tier 1 =
  the tiered package's own one-call preliminary analysis since 2026-08-10; tier
  2 = the evidence-vote deep analysis), compute the position size when the
  user's sizing settings are present, and track the run's own LLM
  call/token usage. (The legacy tier-1 delegate to DSA's
  ``StockAnalysisPipeline`` is retired — the preliminary analysis reads the same
  four data_reports the deep analysis reads and sees the max hold time.)

Everything is injectable so tests stay offline; the defaults are the real
DSA layers.
"""
from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .cross_fields import enrich_cross_fields
from .earnings import EarningsInfo, earnings_from_data_reports
from .levels import (
    apply_adjustments,
    bases_from_data_reports,
    decisions_to_detail,
    decisions_to_levels,
)
from src.languages import DEFAULT_LANGUAGE, require_supported

from .llm_support import LlmTranscript, LlmUsageTracker, active_tracker
from .plan_review import review_plan, sizing_detail_dict
from .preliminary_analysis import PreliminaryAnalysis
from .providers.base import (
    DataReportProvider,
    DataReport,
    Market,
)
from .providers.registry import detect_market, get_providers
from .providers.technicals import Bar, read_metric, technicals_as_of
from .run_gate import (
    StaleDataError,
    expected_bar_date,
    market_for_symbol,
    stale_data_message,
    staleness_stop_reason,
    trim_incomplete_bars,
)
from .schema import (
    DEFAULT_MAX_HOLD_WEEKS,
    MAX_HOLD_WEEKS_CHOICES,
    Action,
    Outlook,
    REWARD_GOAL_EPS,
    SizingSlots,
    TierReport,
    derive_action,
    calculate_reward_ratio,
)
from . import settings as settings_module
from .settings import SizingSettings, merge_overrides
from .sizing import SizingInputs, size_position
from .tiers import Tier2Stage, TierState

logger = logging.getLogger(__name__)

#: Calendar days of daily bars to request — comfortably covers the ~250
#: trading bars the 52-week high/low needs (weekends/holidays included).
BARS_CALENDAR_DAYS = 400


def dsa_bars_loader(ticker: str, manager: Any = None) -> List[Bar]:
    """Daily bars via DSA's multi-source data layer, oldest first.

    Every load shares the process's one manager (2026-10-10): a run
    loads bars three or four times, and a manager per load would give
    each load its own rate-limit clocks and vendor locks."""
    if manager is None:
        from data_provider.base import default_manager

        manager = default_manager()

    # The last completed session: the manager tops up a lagging vendor
    # toward it, and the bars are trimmed to it below.
    expected = expected_bar_date(market_for_symbol(ticker))
    df, _source = manager.get_daily_data(ticker, days=BARS_CALENDAR_DAYS, fresh_through=expected)
    if df is None or df.empty:
        return []

    frame = df.dropna(subset=["open", "high", "low", "close"])
    frame = frame.sort_values("date")
    bars = [
        Bar(
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            open=float(row["open"]),
            volume=float(row["volume"]) if row.get("volume") is not None else None,
            date=str(row["date"]),
        )
        for row in frame.to_dict("records")
    ]
    # Some vendors include today's half-finished bar during the trading
    # day; the analysis must only ever see completed sessions (run-gate
    # design, 2026-08-08). Unknown markets are left untrimmed.
    return trim_incomplete_bars(bars, expected)


#: The tiers a run can be asked for: 1 = the preliminary analysis (one
#: LLM call over the data reports), 2 = the deep analysis (the vote).
#: Tier 3 is retired (outlook redesign, 2026-07-20).
SUPPORTED_TIERS = settings_module.SUPPORTED_TIERS


@dataclass(frozen=True)
class TieredRunOutcome:
    """Everything one tiered run produced.

    ``report`` stays the tier-1/foundation report (it carries the
    data_report results the web cards render from); ``final_report`` is the
    deepest tier that ran — the same object at tier 1.
    """

    report: TierReport
    state: TierState
    tier: int = 1
    final_report: Optional[TierReport] = None
    #: Sizing block (v2 slice 6): share count or explicit refusal reason.
    sizing: Optional[Dict[str, Any]] = None
    #: This run's own LLM call/token counts per stage (since 2026-08-10
    #: this includes the tier-1 preliminary analysis; on older runs the tier-1
    #: blob ran inside the DSA pipeline and was billed there).
    llm_usage: Optional[Dict[str, Any]] = None
    #: Outlook redesign: the impersonal judgment + the personal action
    #: (code table over the outlook and the plan's reward-to-risk).
    outlook: Outlook = Outlook.NO_OUTLOOK
    action: Action = Action.UNKNOWN
    #: Next earnings date, read from the fundamentals payload (display
    #: lives on the fundamentals card; the deep analysis weighs the event risk).
    earnings: Optional[EarningsInfo] = None
    #: Plan review (2026-07-22): structured per-column warnings for the
    #: trade-plan card — {"entry"|"stop_loss"|"target"|"shares":
    #: [{"id", "values"}]}. None when the run produced no buy plan.
    plan_warnings: Optional[Dict[str, Any]] = None
    #: Max hold time in weeks (per-run input, 2026-08-08) — echoed back so
    #: the report can display the horizon the AI was judged against.
    max_hold_weeks: int = DEFAULT_MAX_HOLD_WEEKS

    def __post_init__(self) -> None:
        if self.final_report is None:
            object.__setattr__(self, "final_report", self.report)


def _collect_data_reports(
    providers: Sequence[DataReportProvider], ticker: str
) -> List[DataReport]:
    # Stage-label each provider's collection so its LLM calls (the news
    # screens) show under the data_report's name in llm_usage and the run
    # transcript instead of pooling as "unknown".
    tracker = active_tracker()
    results: List[DataReport] = []
    for provider in providers:
        stage = (
            tracker.stage(provider.name) if tracker else nullcontext()
        )
        try:
            with stage:
                results.append(provider.collect(ticker))
        except Exception as exc:  # providers are fail-loud, but belt+braces
            results.append(
                DataReport(
                    name=provider.name,
                    kind=provider.kind,
                    warnings=[f"{provider.name} provider crashed: {exc}"],
                )
            )
    return results


def collect_data_reports_once(
    ticker: str, market: Optional[Market] = None
) -> List[DataReport]:
    """Collect + cross-enrich the data_reports with production wiring.

    For callers that run the same ticker several times back-to-back
    (the forward-test grid): fetch the data layer here once, then hand
    every run ``providers=precollected_providers(...)`` so each variant
    judges the exact same snapshot. Those runs must pass
    ``staleness_gate=True`` explicitly (injected providers switch the
    gate off by default) and no ``cross_bars_loader`` (enrichment
    already happened here; the canned results must pass through
    untouched).
    """
    if market is None:
        market = detect_market(ticker)
    providers = get_providers(market, bars_loader=dsa_bars_loader)
    data_reports = _collect_data_reports(providers, ticker)
    return enrich_cross_fields(data_reports, dsa_bars_loader)


class PrecollectedProvider(DataReportProvider):
    """Serves one already-collected DataReport unchanged."""

    def __init__(self, result: DataReport) -> None:
        self.name = result.name
        self.kind = result.kind
        self._result = result

    def supports(self, market: Market) -> bool:
        return True  # the data is fixed; market choice already happened

    def collect(self, ticker: str) -> DataReport:
        return self._result


def precollected_providers(
    data_reports: Sequence[DataReport],
) -> List[DataReportProvider]:
    """Wrap a collected snapshot for ``run_tiered_analysis(providers=...)``."""
    return [PrecollectedProvider(dim) for dim in data_reports]


def _technicals_atr(data_reports: Sequence[DataReport]) -> Optional[float]:
    for dim in data_reports:
        if dim.name == "technicals" and dim.payload:
            return read_metric(dim.payload, "volatility", "atr_14")
    return None


#: The run-detail earnings block reads the same shared helper the plan
#: review's earnings gate uses (moved to earnings.py, 2026-07-27).
_earnings_from_dimensions = earnings_from_data_reports


def _sizing_block(
    final: TierReport,
    market: Market,
    settings: SizingSettings,
) -> Tuple[Dict[str, Any], SizingSlots]:
    """Deterministic sizing of the deepest tier's call (v2 slices 1+6).

    The engine runs even when settings are absent so the UI gets an
    explicit ``sizing_off`` refusal instead of a missing section.
    Outlook redesign: the tier-3 multiplier is gone — the buy size
    comes from the formula + caps alone.
    """
    inputs = SizingInputs(
        capital=settings.capital,
        risk_pct=settings.risk_pct,
        entry=final.levels.entry,
        stop_loss=final.levels.stop_loss,
        outlook=final.outlook,
        market=market,
    )
    result = size_position(inputs)
    detail = sizing_detail_dict(settings, result, final.levels)

    if not result.is_sized:
        return detail, SizingSlots()
    return detail, SizingSlots(
        capital=settings.capital,
        risk_pct=settings.risk_pct,
        shares=float(result.shares),
    )


def run_tiered_analysis(
    ticker: str,
    market: Optional[Market] = None,
    providers: Optional[Sequence[DataReportProvider]] = None,
    preliminary_analysis: Optional[PreliminaryAnalysis] = None,
    tier: int = 1,
    sizing_settings: Optional[SizingSettings] = None,
    sizing_overrides: Optional[Mapping[str, Any]] = None,
    tier2_stage: Optional[Tier2Stage] = None,
    earnings_lookup: Optional[Callable[[str, Market], EarningsInfo]] = None,
    plan_summarizer: Optional[Callable[[str], str]] = None,
    cross_bars_loader: Optional[Callable[[str], List[Bar]]] = None,
    max_hold_weeks: int = DEFAULT_MAX_HOLD_WEEKS,
    staleness_gate: Optional[bool] = None,
    transcript: Optional[LlmTranscript] = None,
    language: str = DEFAULT_LANGUAGE,
) -> TieredRunOutcome:
    """Run one ticker at ``tier`` with full production wiring.

    Pipeline (plan-review redesign, 2026-07-22): data layer (four
    data_reports; fundamentals carries the next earnings date) → formula
    levels → the chosen judge (tier 1 = the tiered package's one-call
    preliminary analysis; tier 2 = the evidence vote) → on a BUY
    outlook, the AI plan review (deterministic checks may trim shares /
    move stop / move target, with cited reasons, and produce the
    trade-plan card's structured warnings) → outlook + action (code
    table over the outlook and the plan's reward-to-risk) → sizing.

    ``sizing_overrides`` may carry per-run ``capital`` / ``risk_pct``
    / ``reward_ratio`` values (the API's per-run override) on top of the
    form defaults. ``earnings_lookup`` is a test seam; production reads
    the date the fundamentals provider already fetched.
    ``cross_bars_loader`` is a test/demo seam: injected providers skip
    the cross-provider enrichment unless a loader is passed explicitly.
    ``transcript`` receives every LLM exchange of the run (the API passes
    the run's stored transcript); None counts calls and stores nothing.
    """
    if tier not in SUPPORTED_TIERS:
        raise ValueError(f"tier must be one of {SUPPORTED_TIERS}, got {tier}")
    if max_hold_weeks not in MAX_HOLD_WEEKS_CHOICES:
        raise ValueError(
            f"max_hold_weeks must be one of {MAX_HOLD_WEEKS_CHOICES}, got {max_hold_weeks}"
        )
    if market is None:
        market = detect_market(ticker)
    # The staleness gate runs with production wiring only (injected
    # providers mean a test harness with canned as-of dates), unless the
    # caller opts in/out explicitly — same convention as cross-field
    # enrichment below.
    if staleness_gate is None:
        staleness_gate = providers is None
    # Cross-provider enrichment (sector comparison, implied/realized
    # ratio) runs only with production wiring: injected providers mean
    # a test harness whose canned payloads must pass through untouched
    # — unless the harness opts in with its own ``cross_bars_loader``.
    if providers is None:
        providers = get_providers(market, bars_loader=dsa_bars_loader)
        if cross_bars_loader is None:
            cross_bars_loader = dsa_bars_loader
    # Every run sizes (owner decision 2026-07-24): the defaults are the
    # web form's own; per-run overrides from the request go on top.
    if sizing_settings is None:
        sizing_settings = SizingSettings()
    if sizing_overrides:
        sizing_settings = merge_overrides(
            sizing_settings,
            capital=sizing_overrides.get("capital"),
            risk_pct=sizing_overrides.get("risk_pct"),
            reward_ratio=sizing_overrides.get("reward_ratio"),
        )
    # Every run keeps a transcript of its LLM exchanges (prompt, raw
    # reply, error) so a "no usable JSON" warning is diagnosable later —
    # llm_usage.transcript_entries on the stored run says how many.
    # The run's language (owner decision 2026-09-26): every sentence a
    # reader sees — summaries, claims, reasons, news cards — is written in
    # the language the user chose for the app. It rides on the tracker.
    tracker = LlmUsageTracker(
        transcript=transcript if transcript is not None else LlmTranscript.discard(),
        language=require_supported(language),
    )
    with tracker.activate():
        data_reports = _collect_data_reports(providers, ticker)
        data_reports = enrich_cross_fields(data_reports, cross_bars_loader)

        # STALENESS GATE (2026-08-08): stop BEFORE any LLM stage when the
        # newest completed bar predates the most recent completed trading
        # session — no analysis money is spent on yesterday's leftovers.
        # A clock-gate "run anyway" during the trading day expects the
        # PREVIOUS session's bar and passes here; only a lagging vendor
        # stops a run, and there is deliberately no override for that.
        # Stale bars FAIL the run (owner decision 2026-09-17; it used to
        # finish with a "stopped" outlook) — the user asked for an
        # analysis and gets none, so the row says so, with the dates.
        if staleness_gate:
            bars_up_to = technicals_as_of(data_reports)
            stop_reason = staleness_stop_reason(bars_up_to, market_for_symbol(ticker))
            if stop_reason is not None:
                logger.warning(
                    "tiered run stopped for %s before LLM stages: %s",
                    ticker,
                    stop_reason,
                )
                raise StaleDataError(
                    stale_data_message(bars_up_to, market_for_symbol(ticker)),
                    stop_reason,
                )

        # Formula-only levels: deterministic bases from the technicals
        # payload; the adjustment machinery runs with zero proposals so
        # the audit-trail shape (base/formula/inputs per level) stays.
        bases = bases_from_data_reports(
            data_reports, reward_ratio=sizing_settings.reward_ratio
        )
        decisions, adjust_warnings = apply_adjustments(
            bases, [], atr=_technicals_atr(data_reports)
        )
        level_warnings = list(bases.warnings) + adjust_warnings
        levels = decisions_to_levels(decisions)
        levels_detail = decisions_to_detail(decisions, level_warnings)

        # The next earnings date rides in the fundamentals payload (the
        # provider fetched it); the injectable lookup is a test seam.
        earnings = (
            earnings_lookup(ticker, market)
            if earnings_lookup is not None
            else _earnings_from_dimensions(data_reports, market=market)
        )
        extra_warnings = level_warnings

        state = TierState(ticker=ticker, market=market, max_hold_weeks=max_hold_weeks)
        if tier == 1:
            # The preliminary analysis (2026-08-10): the tiered package's own
            # one-call outlook over the same data_reports the deep analysis
            # reads (all six since 2026-08-16, both news cards included),
            # judged against the same max hold time. No outlook
            # (LLM down, bad replies) → UNKNOWN outlook, fail-loud
            # warnings, no fallback — same contract as the deep analysis.
            with tracker.stage("preliminary_analysis"):
                preliminary = (preliminary_analysis or PreliminaryAnalysis()).run(
                    ticker, data_reports, max_hold_weeks=max_hold_weeks
                )
            outlook = preliminary.outlook
            report = TierReport(
                tier=1,
                ticker=ticker,
                market=market,
                outlook=outlook.outlook if outlook else Outlook.NO_OUTLOOK,
                # The outlook is the 0-10 score in detail; the
                # legacy sentiment-score/confidence columns stay empty
                # (same shape as tier-2 reports).
                confidence=None,
                score=None,
                summary=outlook.summary if outlook else None,
                levels=levels,
                levels_detail=levels_detail,
                data_reports=data_reports,
                warnings=list(preliminary.warnings) + extra_warnings,
                detail=preliminary.to_detail(),
            )
        else:
            # Depth 2 skips the one-blob call entirely: the deep analysis is the
            # judge, so the foundation report is the data layer + levels
            # with no outlook of its own. That is the documented tier-2
            # contract, not a data problem — so no warning for it.
            report = TierReport(
                tier=1,
                ticker=ticker,
                market=market,
                outlook=Outlook.NO_OUTLOOK,
                levels=levels,
                levels_detail=levels_detail,
                data_reports=data_reports,
                warnings=extra_warnings,
            )
        state.reports[1] = report
        state.data_reports = list(data_reports)

        final = report
        if tier >= 2:
            with tracker.stage("deep_analysis"):
                final = (tier2_stage or Tier2Stage()).run(state)
            state.reports[2] = final

        # AI plan review (bullish outlooks only): the deterministic checks
        # may trim the share count or move stop/target with cited
        # reasons, and produce the plan card's structured warnings.
        review = None
        if final.outlook is Outlook.BULLISH and bases.get("entry") is not None:
            with tracker.stage("trade_plan"):
                review = review_plan(
                    ticker, data_reports, bases, final.outlook, market,
                    sizing_settings,
                    summarizer=plan_summarizer, max_hold_weeks=max_hold_weeks,
                )

    plan_warnings: Optional[Dict[str, Any]] = None
    if review is not None:
        tier1_same = final is report
        # Review warnings land on the foundation report only (the plan
        # card's warnings); the tier-2 card keeps its own warnings.
        report = replace(
            report,
            levels=review.levels,
            levels_detail=review.levels_detail,
            warnings=list(report.warnings) + list(review.warnings),
        )
        final = report if tier1_same else replace(
            final, levels=review.levels, levels_detail=review.levels_detail
        )
        state.reports[1] = report
        sizing_detail, sizing_slots = review.sizing_detail, review.sizing_slots
        plan_warnings = review.plan_warnings
    else:
        sizing_detail, sizing_slots = _sizing_block(final, market, sizing_settings)
    final = replace(final, sizing=sizing_slots, max_hold_weeks=max_hold_weeks)
    if not final.data_reports:
        # Tier-2 reports are built lean; the deepest report carries the
        # evidence so consumers see it.
        final = replace(final, data_reports=list(data_reports))
    state.reports[final.tier] = final
    if final.tier == 1:
        report = final

    outlook = final.outlook
    # Buy now vs buy later (owner decision 2026-08-23): the final plan's
    # actual reward-to-risk against the user's goal — the same comparison
    # the plan card's reward-below-goal warning makes.
    ratio = calculate_reward_ratio(final.levels)
    plan_meets_goal = (
        ratio is None or ratio >= sizing_settings.reward_ratio - REWARD_GOAL_EPS
    )
    action = derive_action(outlook, plan_meets_goal=plan_meets_goal)

    return TieredRunOutcome(
        report=report,
        state=state,
        tier=tier,
        final_report=final,
        sizing=sizing_detail,
        llm_usage=tracker.to_detail(),
        outlook=outlook,
        action=action,
        earnings=earnings,
        plan_warnings=plan_warnings,
        max_hold_weeks=max_hold_weeks,
    )
