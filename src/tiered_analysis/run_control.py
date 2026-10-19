# -*- coding: utf-8 -*-
"""Stopping a run part-way (2026-10-19), and watching it progress.

A run is minutes of data fetches and model calls, and a user who
started one by mistake should not have to pay for the rest of it. The
stop is a flag (a ``threading.Event`` the queue hands the run) that the
run checks at its checkpoints:

- the entry of every stage (each data report, the preliminary or deep
  analysis, the trade plan — ``LlmUsageTracker.stage``), and
- the top of every LLM call (``llm_support._summarize``), before the
  provider is contacted.

Between checkpoints nothing is interrupted: the call in flight finishes
and is recorded, so the token totals match the bill (the chat's rule,
2026-10-12). The stage the stop lands in is discarded whole — a section
is either complete or absent, never half-built — and the run ends as
``stopped`` with what finished before it (``RunProgress``).

The same record is what a running run shows as it goes (2026-10-19):
at the start of every step the run hands a ``RunProgress`` to its
``progress`` callback, and the run service stores it on the run's row,
so the page's poll sees each card the moment it is complete rather
than the whole report at the end. A section is still either complete
or absent: a snapshot never holds a half-built card.

``RunStopped`` is a ``BaseException`` on purpose. The stages degrade
ordinary failures into warnings with ``except Exception`` (a failed
lister drops out, a failed news batch is warned), and a stop must not
be degraded into a warning: it has to end the run.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .providers.base import DataReport, Market
from .schema import TierReport, TradePlanLevels


class StopFlag:
    """The run's stop flag: a ``threading.Event`` that also remembers
    which stage was running when it was raised (``stage``), so the
    report can say "you stopped during X" — the stage the user saw —
    rather than where the stop happened to take effect. The run's
    tracker ``attach``es its stage reader on activation; a flag raised
    before that, or between stages, remembers no stage."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._read_stage: Optional[Callable[[], str]] = None
        self.stage: Optional[str] = None

    def attach(self, read_stage: Callable[[], str]) -> None:
        self._read_stage = read_stage

    def set(self) -> None:
        if self.stage is None and self._read_stage is not None:
            self.stage = self._read_stage()
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class RunProgress:
    """What a run has finished so far. ``stage`` names the step now in
    progress — the one whose work is absent: on a running run the step
    being worked on, on a stopped run the step the stop landed in.
    ``stages`` is the run's steps in order (each data report, the
    analysis, the trade plan), so a reader can tell what is still to
    come. ``pressed_stage`` (stopped runs) is the step that was running
    when the user pressed stop (None when unknown), which may be an
    earlier step that then finished, since a stop only takes effect at
    the next checkpoint."""

    stage: str
    ticker: str
    market: Market
    tier: int
    max_hold_weeks: int
    #: The data reports that finished, in collection order.
    data_reports: List[DataReport] = field(default_factory=list)
    #: The formula levels, once the data stage was through; None before.
    levels: Optional[TradePlanLevels] = None
    levels_detail: Optional[Dict[str, Any]] = None
    level_warnings: List[str] = field(default_factory=list)
    #: The tier-1 report, when the preliminary analysis finished.
    preliminary: Optional[TierReport] = None
    #: The tier-2 report, when the deep analysis finished.
    deep: Optional[TierReport] = None
    earnings: Optional[Any] = None
    #: The run's LLM usage up to the stop — what it cost.
    llm_usage: Optional[Dict[str, Any]] = None
    pressed_stage: Optional[str] = None
    #: The run's steps in order; empty on a record built without them.
    stages: List[str] = field(default_factory=list)


#: What a run calls with its progress at the start of every step.
ProgressSink = Callable[[RunProgress], None]


class RunStopped(BaseException):
    """Raised at a checkpoint once the run's stop flag is up. ``stage``
    is the step the stop landed in; ``partial`` is attached by the
    orchestrator on its way out (None when raised below it)."""

    def __init__(self, stage: str, partial: Optional[RunProgress] = None) -> None:
        super().__init__(f"run stopped during {stage}")
        self.stage = stage
        self.partial = partial
