# -*- coding: utf-8 -*-
"""Global run queue: at most N tiered runs execute at once (owner decision
2026-09-15); the rest wait their turn, first come, first served.

Why: every run holds price history, news and LLM replies in memory while
fanning out parallel LLM calls. A few runs at once are fine; a burst of
them can exhaust the machine and take every run down with it. The cap
is ``MAX_CONCURRENT_RUNS`` (default ``DEFAULT_MAX_CONCURRENT_RUNS``),
read on every dispatch so a changed setting applies without a restart.
``remove`` takes a run out of the line (or out of the history) under the
same lock, so a cancel and a dispatch can never cross. ``stop`` raises
the stop flag of an executing run (run_control.py, 2026-10-19): the run
ends at its next checkpoint, keeping the sections that finished.

How: the line itself lives in the database — a run is created ``queued``
(src/tiered_analysis/history.py) and ``dispatch`` promotes the oldest
queued rows to ``running`` while slots are free, one daemon thread each.
When a thread finishes it dispatches again. Because the line is rows,
not memory, ``resume`` at startup picks up whatever the previous process
left waiting, whereas a run that was mid-flight is failed by startup
housekeeping as before.

The queue knows nothing about the analysis: the endpoint hands it a
``runner`` that executes one ``QueuedRun`` and records its outcome.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .run_control import StopFlag

logger = logging.getLogger(__name__)

MAX_CONCURRENT_RUNS_ENV = "MAX_CONCURRENT_RUNS"
DEFAULT_MAX_CONCURRENT_RUNS = 4


def max_concurrent_runs() -> int:
    """The concurrency cap from the environment; the default when unset
    or not a whole number of at least 1 (logged, never fatal)."""
    raw = (os.getenv(MAX_CONCURRENT_RUNS_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENT_RUNS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        logger.warning(
            "%s=%r is not a whole number >= 1; using %d",
            MAX_CONCURRENT_RUNS_ENV, raw, DEFAULT_MAX_CONCURRENT_RUNS,
        )
        return DEFAULT_MAX_CONCURRENT_RUNS
    return value


@dataclass(frozen=True)
class QueuedRun:
    """One run as the queue hands it to the runner."""

    run_id: str
    ticker: str
    #: The stored creation-time inputs (capital, risk_pct, reward_ratio,
    #: max_hold_weeks, tier).
    inputs: Dict[str, Any]
    #: The run's stop flag: ``RunQueue.stop`` raises it, the runner hands
    #: it to the engine, which ends the run at its next checkpoint.
    stop: StopFlag = field(default_factory=StopFlag, compare=False)


Runner = Callable[[QueuedRun], None]


class RunQueue:
    """Promotes queued runs to running threads, ``max_concurrent_runs()``
    at a time. Safe to call from any thread."""

    def __init__(self, runner: Runner) -> None:
        self._runner = runner
        self._lock = threading.Lock()
        #: The executing runs' stop flags, by run id.
        self._active: Dict[str, StopFlag] = {}

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def submit(self, run_id: str) -> str:
        """Try to start the just-created queued run ``run_id`` (and any
        other waiting run a free slot allows). Returns the status the
        caller should report: ``running`` if it got a slot now, else
        ``queued``. A dispatch failure leaves the row queued for the next
        dispatch rather than failing the request."""
        try:
            started = self.dispatch()
        except Exception as exc:
            logger.warning("run queue dispatch failed for %s: %s", run_id, exc)
            return "queued"
        return "running" if run_id in started else "queued"

    def resume(self) -> List[str]:
        """Startup: start the runs the previous process left queued.
        Returns the run id started now."""
        started = self.dispatch()
        if started:
            logger.info("run queue resumed %d queued run(s)", len(started))
        return started

    def dispatch(self) -> List[str]:
        """Fill free slots from the front of the line. Returns the task
        ids started by this call."""
        from . import history

        started: List[str] = []
        with self._lock:
            limit = max_concurrent_runs()
            while len(self._active) < limit:
                row = history.next_queued_run(exclude=self._active)
                if row is None:
                    break
                run = QueuedRun(
                    run_id=row["run_id"],
                    ticker=row["ticker"],
                    inputs=dict(row["inputs"] or {}),
                )
                history.mark_running(run.run_id)
                self._active[run.run_id] = run.stop
                thread = threading.Thread(
                    target=self._work,
                    args=(run,),
                    name=f"tiered-analysis-{run.ticker}",
                    daemon=True,
                )
                try:
                    thread.start()
                except Exception as exc:
                    # The row is already "running" and the slot taken:
                    # undo both, or the run shows running forever and the
                    # slot stays lost until a restart (2026-10-10). The
                    # line then moves on to the next waiting run.
                    self._active.pop(run.run_id, None)
                    reason = f"the run's worker thread could not be started: {exc}"
                    logger.exception("run %s failed to start: %s", run.run_id, reason)
                    history.mark_failed(run.run_id, reason)
                    continue
                started.append(run.run_id)
        return started

    def remove(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Delete a run that is not executing: a queued run leaves the
        line (that is how one is cancelled), a finished or failed run is
        removed from the history. Holds the queue lock so a queued row
        cannot be promoted to running between the check and the delete.
        Returns the deleted row's summary, None for an unknown run id;
        raises ``history.RunInProgressError`` when the run is executing
        (``stop`` it first, then delete the stopped run)."""
        from . import history

        with self._lock:
            if run_id in self._active:
                raise history.RunInProgressError(run_id)
            return history.delete_run(run_id)

    def stop(self, run_id: str) -> bool:
        """Ask an executing run to stop: its flag goes up and the run
        ends at its next checkpoint (the entry of a stage or the top of
        an LLM call), keeping the sections that finished. True when the
        run was executing; False when it was not — queued (cancel it
        with ``remove``), already over, or unknown."""
        with self._lock:
            flag = self._active.get(run_id)
            if flag is None:
                return False
            flag.set()
            return True

    def _work(self, run: QueuedRun) -> None:
        try:
            self._runner(run)
        except Exception:  # the runner records its own failures; this is the net
            logger.exception("run %s escaped its runner", run.run_id)
        finally:
            with self._lock:
                self._active.pop(run.run_id, None)
            try:
                self.dispatch()
            except Exception as exc:
                logger.warning("run queue dispatch failed after %s: %s",
                               run.run_id, exc)
