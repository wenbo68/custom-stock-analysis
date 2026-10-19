# -*- coding: utf-8 -*-
"""Offline tests for stopping a run part-way (2026-10-19).

A stop is a flag the run checks at its checkpoints: the entry of every
stage, and the top of every LLM call. The step in flight finishes
(token totals must match the bill), the rest is skipped, and the run
keeps what finished before the stop: a section is either complete or
absent, never half-built.
"""
from __future__ import annotations

import threading
import unittest

from src.tiered_analysis.integration import (
    _collect_data_reports,
    run_stages,
    run_tiered_analysis,
)
from src.tiered_analysis.llm_support import (
    LlmTranscript,
    LlmUsageTracker,
    active_tracker,
    default_summarizer,
)
from src.tiered_analysis.preliminary_analysis import PreliminaryAnalysis
from src.tiered_analysis.providers.base import (
    DataReport,
    DataReportProvider,
    Market,
    SourceKind,
)
from src.tiered_analysis.run_control import RunStopped, StopFlag, RunProgress
from src.tiered_analysis.schema import Outlook
from src.tiered_analysis.tiers import Tier2Stage

from tests.test_tiered_integration import (
    _FakeDebateEngine,
    _FakeQuickJudge,
    _debate_outlook,
    _dim,
    _no_earnings,
    _technicals_dim_with_levels,
)


class _Provider(DataReportProvider):
    """A stub provider; ``on_collect`` runs inside ``collect`` so a test
    can raise the stop flag while this card is being fetched."""

    kind = SourceKind.NUMERIC

    def __init__(self, name, on_collect=None):
        self.name = name
        self._on_collect = on_collect

    def supports(self, market):
        return True

    def collect(self, ticker):
        if self._on_collect is not None:
            self._on_collect()
        return _dim(self.name)


class TestRunStopped(unittest.TestCase):
    def test_is_not_an_ordinary_exception(self):
        # The stages degrade ordinary failures into warnings with
        # ``except Exception``; a stop must pass through them untouched.
        self.assertTrue(issubclass(RunStopped, BaseException))
        self.assertFalse(issubclass(RunStopped, Exception))
        stopped = RunStopped("positioning")
        self.assertEqual(stopped.stage, "positioning")
        self.assertIsNone(stopped.partial)


class TestStopFlag(unittest.TestCase):
    def test_remembers_the_stage_it_was_raised_in(self):
        flag = StopFlag()
        tracker = LlmUsageTracker(stop=flag)  # attaches its stage reader
        with tracker.stage("company_news"):
            flag.set()
        self.assertTrue(flag.is_set())
        self.assertEqual(flag.stage, "company_news")
        # The first press is the one that counts (a second press lands
        # between stages here, which would otherwise read as unknown).
        flag.set()
        self.assertEqual(flag.stage, "company_news")

    def test_raised_before_any_stage_remembers_none(self):
        flag = StopFlag()
        flag.set()
        self.assertIsNone(flag.stage)
        LlmUsageTracker(stop=flag)
        self.assertIsNone(flag.stage)

    def test_the_run_reports_the_pressed_stage_beside_the_landing_stage(self):
        flag = StopFlag()
        providers = [
            _Provider("technicals", on_collect=flag.set),
            _Provider("fundamentals"),
        ]
        with self.assertRaises(RunStopped) as caught:
            run_tiered_analysis(
                "AAPL", market=Market.US, providers=providers,
                preliminary_analysis=_FakeQuickJudge(), earnings_lookup=_no_earnings,
                stop=flag,
            )
        # Pressed during technicals (which finished); landed at fundamentals.
        self.assertEqual(caught.exception.stage, "fundamentals")
        self.assertEqual(caught.exception.partial.pressed_stage, "technicals")
        self.assertEqual([d.name for d in caught.exception.partial.data_reports], ["technicals"])


class TestTrackerCheckpoints(unittest.TestCase):
    def test_no_flag_means_no_checkpoint(self):
        tracker = LlmUsageTracker()
        tracker.checkpoint("x")
        with tracker.stage("technicals"):
            pass

    def test_a_raised_flag_stops_at_the_next_checkpoint(self):
        stop = threading.Event()
        tracker = LlmUsageTracker(stop=stop)
        with tracker.stage("technicals"):
            tracker.checkpoint()
            stop.set()
        with self.assertRaises(RunStopped) as caught:
            tracker.checkpoint("fundamentals")
        self.assertEqual(caught.exception.stage, "fundamentals")
        # A stage never begins once the flag is up.
        with self.assertRaises(RunStopped) as caught:
            with tracker.stage("positioning"):
                self.fail("the stage body must not run")
        self.assertEqual(caught.exception.stage, "positioning")

    def test_an_llm_call_is_refused_before_it_is_made_and_leaves_no_trace(self):
        stop = threading.Event()
        transcript = LlmTranscript.discard()
        tracker = LlmUsageTracker(transcript=transcript, stop=stop)
        with tracker.activate():
            with tracker.stage("deep_analysis"):
                # The stop lands mid-stage, before the next call.
                stop.set()
                with self.assertRaises(RunStopped) as caught:
                    default_summarizer("grade this evidence")
        self.assertEqual(caught.exception.stage, "deep_analysis")
        # Nothing was called, so nothing is billed or transcribed.
        self.assertEqual(tracker.to_detail()["total"]["calls"], 0)
        self.assertEqual(transcript.entries, 0)


class TestCollectDataReports(unittest.TestCase):
    def test_a_stop_passes_the_crash_net_and_the_finished_cards_stay(self):
        stop = threading.Event()
        tracker = LlmUsageTracker(stop=stop)
        providers = [
            _Provider("technicals"),
            _Provider("fundamentals", on_collect=stop.set),
            _Provider("positioning"),
        ]
        collected = []
        with tracker.activate():
            with self.assertRaises(RunStopped) as caught:
                _collect_data_reports(providers, "AAPL", sink=collected)
        # The stop landed during fundamentals, which had no LLM call to
        # refuse, so that card finished; positioning never began.
        self.assertEqual(caught.exception.stage, "positioning")
        self.assertEqual([d.name for d in collected], ["technicals", "fundamentals"])


class TestRunTieredAnalysisStopped(unittest.TestCase):
    def _run(self, providers, stop, tier=1, judge=None, debate_outlook=None):
        return run_tiered_analysis(
            "AAPL",
            market=Market.US,
            providers=providers,
            preliminary_analysis=judge or _FakeQuickJudge(),
            tier=tier,
            tier2_stage=Tier2Stage(engine=_FakeDebateEngine(outlook=debate_outlook)),
            earnings_lookup=_no_earnings,
            stop=stop,
        )

    def test_stopped_during_the_data_reports_keeps_the_finished_cards_only(self):
        stop = threading.Event()
        providers = [
            _Provider("technicals"),
            _Provider("fundamentals", on_collect=stop.set),
            _Provider("positioning"),
        ]
        with self.assertRaises(RunStopped) as caught:
            self._run(providers, stop)
        stopped = caught.exception
        self.assertEqual(stopped.stage, "positioning")
        partial = stopped.partial
        self.assertIsInstance(partial, RunProgress)
        self.assertEqual(partial.ticker, "AAPL")
        self.assertEqual(partial.market, Market.US)
        self.assertEqual(partial.tier, 1)
        self.assertEqual([d.name for d in partial.data_reports], ["technicals", "fundamentals"])
        # No analysis, no plan: the stages after the cards never ran.
        self.assertIsNone(partial.levels)
        self.assertIsNone(partial.preliminary)
        self.assertIsNone(partial.deep)
        self.assertEqual(partial.llm_usage["total"]["calls"], 0)

    def test_stopped_inside_the_preliminary_analysis_discards_it(self):
        stop = threading.Event()

        class _StoppedJudge:
            def run(self, ticker, data_reports, max_hold_weeks):
                # The stop lands while the judge is working: its next
                # LLM call is refused, as the real summarizer would be.
                stop.set()
                active_tracker().checkpoint()
                raise AssertionError("unreachable")

        providers = [_Provider("technicals"), _Provider("fundamentals")]
        with self.assertRaises(RunStopped) as caught:
            self._run(providers, stop, judge=_StoppedJudge())
        stopped = caught.exception
        self.assertEqual(stopped.stage, "preliminary_analysis")
        partial = stopped.partial
        self.assertEqual([d.name for d in partial.data_reports], ["technicals", "fundamentals"])
        self.assertIsNone(partial.preliminary)
        self.assertIsNone(partial.deep)

    def test_stopped_at_the_trade_plan_keeps_the_finished_analysis(self):
        stop = threading.Event()

        def judge_then_stop():
            stop.set()

        # A bullish preliminary analysis over levels the plan can be
        # computed from, so the trade-plan stage is next — and the stop
        # raised during the analysis (after its last call) lands there.
        class _JudgeThatSeesTheStop(_FakeQuickJudge):
            def run(self, ticker, data_reports, max_hold_weeks):
                judge_then_stop()
                return super().run(ticker, data_reports, max_hold_weeks)

        technicals = _technicals_dim_with_levels()

        class _Tech(_Provider):
            def collect(self, ticker):
                return technicals

        providers = [_Tech("technicals"), _Provider("fundamentals")]
        with self.assertRaises(RunStopped) as caught:
            self._run(providers, stop, judge=_JudgeThatSeesTheStop(score=8.0))
        stopped = caught.exception
        self.assertEqual(stopped.stage, "trade_plan")
        partial = stopped.partial
        self.assertEqual([d.name for d in partial.data_reports], ["technicals", "fundamentals"])
        self.assertIsNotNone(partial.levels)
        self.assertEqual(partial.levels.entry, 96)
        self.assertIsNotNone(partial.preliminary)
        self.assertIs(partial.preliminary.outlook, Outlook.BULLISH)
        self.assertIsNone(partial.deep)

    def test_stopped_at_the_trade_plan_of_a_deep_run_keeps_the_vote(self):
        stop = threading.Event()
        technicals = _technicals_dim_with_levels()

        class _Tech(_Provider):
            def collect(self, ticker):
                return technicals

        class _Engine(_FakeDebateEngine):
            def run(self, *args, **kwargs):
                stop.set()
                return super().run(*args, **kwargs)

        providers = [_Tech("technicals")]
        with self.assertRaises(RunStopped) as caught:
            run_tiered_analysis(
                "AAPL", market=Market.US, providers=providers, tier=2,
                tier2_stage=Tier2Stage(engine=_Engine(outlook=_debate_outlook())),
                earnings_lookup=_no_earnings, stop=stop,
            )
        partial = caught.exception.partial
        self.assertEqual(caught.exception.stage, "trade_plan")
        self.assertEqual(partial.tier, 2)
        self.assertIsNone(partial.preliminary)
        self.assertIsNotNone(partial.deep)
        self.assertIs(partial.deep.outlook, Outlook.BULLISH)

    def test_a_stop_with_nothing_left_to_skip_finishes_the_run(self):
        stop = threading.Event()

        class _JudgeThenStop(_FakeQuickJudge):
            def run(self, ticker, data_reports, max_hold_weeks):
                stop.set()
                return super().run(ticker, data_reports, max_hold_weeks)

        # A neutral outlook has no trade-plan stage, so after the
        # analysis there is no checkpoint left: the run simply succeeds.
        outcome = self._run(
            [_Provider("technicals")], stop, judge=_JudgeThenStop(score=5.0),
        )
        self.assertIs(outcome.outlook, Outlook.NEUTRAL)

    def test_no_stop_flag_runs_as_before(self):
        outcome = self._run([_Provider("technicals")], stop=None)
        self.assertIs(outcome.outlook, Outlook.BULLISH)


class TestRunProgress(unittest.TestCase):
    """A running run reports what it has finished at the start of every
    step (2026-10-19), so a watcher sees each card as it lands."""

    def _run(self, providers, progress, tier=1, stop=None):
        return run_tiered_analysis(
            "AAPL", market=Market.US, providers=providers,
            preliminary_analysis=_FakeQuickJudge(), tier=tier,
            tier2_stage=Tier2Stage(engine=_FakeDebateEngine(outlook=None)),
            earnings_lookup=_no_earnings, progress=progress, stop=stop,
        )

    def test_reports_at_the_start_of_every_step_with_what_finished(self):
        seen = []
        providers = [_Provider("technicals"), _Provider("fundamentals"), _Provider("positioning")]
        outcome = self._run(providers, seen.append)

        # One snapshot per data report, then one for the analysis; the
        # plan runs on a bullish outlook only, and the fake judge is not.
        self.assertEqual(
            [p.stage for p in seen],
            ["technicals", "fundamentals", "positioning", "preliminary_analysis"],
        )
        self.assertEqual(
            [[d.name for d in p.data_reports] for p in seen],
            [[], ["technicals"], ["technicals", "fundamentals"],
             ["technicals", "fundamentals", "positioning"]],
        )
        for snapshot in seen:
            self.assertIsInstance(snapshot, RunProgress)
            self.assertEqual(snapshot.ticker, "AAPL")
            self.assertEqual(snapshot.tier, 1)
            self.assertEqual(
                snapshot.stages,
                ["technicals", "fundamentals", "positioning", "preliminary_analysis", "trade_plan"],
            )
            self.assertIsNone(snapshot.pressed_stage)
        # Before the analysis: the levels are there, the analysis is not.
        self.assertIsNone(seen[2].levels)
        self.assertIsNotNone(seen[3].levels)
        self.assertIsNone(seen[3].preliminary)
        self.assertIsNone(seen[3].deep)
        # The run itself is unchanged by being watched.
        self.assertEqual([d.name for d in outcome.report.data_reports],
                         ["technicals", "fundamentals", "positioning"])

    def test_a_watcher_that_fails_does_not_touch_the_run(self):
        calls = []

        def broken(snapshot):
            calls.append(snapshot.stage)
            raise RuntimeError("storage down")

        outcome = self._run([_Provider("technicals")], broken)
        self.assertEqual(calls, ["technicals", "preliminary_analysis"])
        self.assertEqual(outcome.tier, 1)

    def test_no_watcher_means_no_reports(self):
        outcome = self._run([_Provider("technicals")], None)
        self.assertEqual(outcome.tier, 1)

    def test_a_stop_keeps_the_step_list_too(self):
        stop = threading.Event()
        providers = [_Provider("technicals", on_collect=stop.set), _Provider("fundamentals")]
        with self.assertRaises(RunStopped) as caught:
            self._run(providers, None, stop=stop)
        self.assertEqual(caught.exception.partial.stages,
                         ["technicals", "fundamentals", "preliminary_analysis", "trade_plan"])

    def test_the_step_list_names_the_tiers_analysis(self):
        providers = [_Provider("technicals"), _Provider("company_news")]
        self.assertEqual(run_stages(providers, 1),
                         ["technicals", "company_news", "preliminary_analysis", "trade_plan"])
        self.assertEqual(run_stages(providers, 2),
                         ["technicals", "company_news", "deep_analysis", "trade_plan"])
