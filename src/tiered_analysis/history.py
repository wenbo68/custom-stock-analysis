# -*- coding: utf-8 -*-
"""Persistent history of tiered-analysis runs (tiered_runs table).

The web tiered page shows these as a clickable run list: a run starts as
``queued`` (waiting for a free slot in the global run queue,
src/tiered_analysis/run_queue.py), becomes ``running``, then flips to
``succeeded`` (with the full serialized report) or ``failed`` (with the
error), and stays in the list as history across page navigation and
server restarts. Queued rows outlive the process: the queue resumes them
at startup, whereas running rows die with their thread and are failed.

The list is served one page at a time, filtered and sorted in SQL
(2026-09-21): the facts a row shows — capital, risk %, reward ratio, max
hold, tier, outlook, shares — are real columns (see run_digest.py), so the endpoint
never ships the whole table for the browser to sift.

Storage is the product's database via DatabaseManager (sqlite by
default, Postgres when DATABASE_URL is set) — one small table, no
separate infrastructure.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Collection, Dict, Iterable, List, Optional, Sequence

from .llm_support import TRANSCRIPT_MAX_AGE_DAYS
from .report_sections import (
    ALL_SECTIONS,
    DEFAULT_ITEM_PAGE_SIZE,
    deep_analysis_record,
    page_count,
    page_vote_items,
    select_sections,
)
from .run_digest import DUPLICATE_KEYS, digest_from_inputs, digest_from_result

logger = logging.getLogger(__name__)

#: Page size when the caller names none, and the most rows one page may hold.
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 200

#: The error stored on runs that were still "running" when the server
#: came back up: the background thread died with the old process, so the
#: run can never finish. Worded for the history list.
STALE_RUN_ERROR = "server restarted while this run was in progress"

#: Run statuses. A run is "active" (queued or running) until it settles
#: as succeeded or failed — the duplicate check only looks at active runs.
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)
ALL_STATUSES = (STATUS_QUEUED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED)

#: The outlooks that count as an opinion. A finished run whose analysis
#: produced nothing stores "no_outlook" (the page's "No outlook"), which
#: the list treats like no outlook at all (the dash), as does any
#: unfinished or failed run.
OUTLOOK_WORDS = ("bullish", "neutral", "bearish")
#: The outlook filter value meaning "rows with no outlook" (the dash):
#: the same word the stored no-outlook value uses, so one word covers
#: "the analysis produced none" and "there is none yet".
NO_OUTLOOK = "no_outlook"
FILTERABLE_OUTLOOKS = OUTLOOK_WORDS + (NO_OUTLOOK,)


class RunInProgressError(RuntimeError):
    """The run is executing. Its thread cannot be stopped from outside,
    so the row stays until the run finishes or fails."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id} is in progress")
        self.run_id = run_id


def _session():
    from src.storage import DatabaseManager

    return DatabaseManager.get_instance().get_session()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def create_run(
    run_id: str,
    ticker: str,
    inputs: Optional[Dict[str, Any]] = None,
    status: str = STATUS_RUNNING,
) -> None:
    """``inputs`` are the run's effective settings in the form's words
    (capital, risk_pct, reward_ratio, max_hold_weeks, tier; see
    ``run_digest.INPUT_KEYS``) — recorded at creation so the history row
    shows them while the run is still in flight, and handed to the
    engine when the queue starts the run. The web endpoint creates runs
    ``queued``; the default keeps direct callers (tests) that start
    their own thread on ``running``."""
    from src.storage import TieredRunRecord

    with _session() as session:
        session.add(TieredRunRecord(
            run_id=run_id,
            ticker=ticker,
            status=status,
            inputs_json=json.dumps(inputs) if inputs else None,
            **digest_from_inputs(inputs),
        ))
        session.commit()


def _update_run(run_id: str, **fields: Any) -> None:
    from src.storage import TieredRunRecord

    with _session() as session:
        row = (
            session.query(TieredRunRecord)
            .filter_by(run_id=run_id)
            .one_or_none()
        )
        if row is None:
            logger.warning("tiered run %s vanished before update", run_id)
            return
        for key, value in fields.items():
            setattr(row, key, value)
        session.commit()


def mark_succeeded(run_id: str, result: Dict[str, Any]) -> None:
    """Store the finished report, and lay its own facts (outlook, shares,
    the sizing it actually used) over the creation-time columns."""
    _update_run(
        run_id,
        status=STATUS_SUCCEEDED,
        result_json=json.dumps(result),
        **digest_from_result(result),
    )


def mark_failed(run_id: str, error: str) -> None:
    _update_run(run_id, status=STATUS_FAILED, error=str(error))


def mark_running(run_id: str) -> None:
    """A queued run took a slot (the queue calls this as it starts the
    thread)."""
    _update_run(run_id, status=STATUS_RUNNING)


def delete_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Delete a run and its transcript rows. A queued run is simply taken
    out of the line (that is how one is cancelled); a finished or failed
    run is removed from the history. Returns the deleted row's summary,
    or None for an unknown run id. Raises ``RunInProgressError`` for a
    running row. Go through ``RunQueue.remove`` rather than calling this
    directly, so a queued row cannot be promoted to running between the
    check and the delete."""
    from src.storage import TieredRunRecord, TieredRunTranscriptRecord

    with _session() as session:
        row = (
            session.query(TieredRunRecord)
            .filter_by(run_id=run_id)
            .one_or_none()
        )
        if row is None:
            return None
        if row.status == STATUS_RUNNING:
            raise RunInProgressError(run_id)
        summary = _row_summary(row)
        (
            session.query(TieredRunTranscriptRecord)
            .filter_by(run_id=run_id)
            .delete(synchronize_session=False)
        )
        session.delete(row)
        session.commit()
        return summary


def fail_stale_running_runs(error: str = STALE_RUN_ERROR) -> int:
    """Startup housekeeping: every run still marked ``running`` belongs
    to a process that no longer exists (runs execute in-process threads),
    so mark them failed rather than leave a spinner forever. Returns the
    number of rows changed."""
    from src.storage import TieredRunRecord

    with _session() as session:
        changed = (
            session.query(TieredRunRecord)
            .filter_by(status=STATUS_RUNNING)
            .update({"status": STATUS_FAILED, "error": error},
                    synchronize_session=False)
        )
        session.commit()
        return int(changed or 0)


#: The word a finished run carried before 2026-10-12, when the status
#: was renamed ``succeeded`` on the page and so everywhere else.
LEGACY_STATUS_DONE = "done"


def rename_legacy_done_runs() -> int:
    """Startup housekeeping: rows still carrying the pre-2026-10-12
    ``done`` status become ``succeeded``. Returns the number of rows
    changed; 0 once every database has been through it."""
    from src.storage import TieredRunRecord

    with _session() as session:
        changed = (
            session.query(TieredRunRecord)
            .filter_by(status=LEGACY_STATUS_DONE)
            .update({"status": STATUS_SUCCEEDED}, synchronize_session=False)
        )
        session.commit()
        return int(changed or 0)


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------


def next_queued_run(exclude: Collection[str] = ()) -> Optional[Dict[str, Any]]:
    """The oldest queued run not in ``exclude`` (run_id, ticker,
    inputs), or None when nothing is waiting. First come, first served:
    ordered by creation time, then id."""
    from src.storage import TieredRunRecord

    with _session() as session:
        query = (
            session.query(TieredRunRecord)
            .filter_by(status=STATUS_QUEUED)
            .order_by(TieredRunRecord.created_at.asc(), TieredRunRecord.id.asc())
        )
        skipped = [str(run_id) for run_id in exclude]
        if skipped:
            query = query.filter(TieredRunRecord.run_id.notin_(skipped))
        row = query.first()
        if row is None:
            return None
        return {
            "run_id": row.run_id,
            "ticker": row.ticker,
            "inputs": _inputs_of(row),
        }


def find_active_duplicate(
    ticker: str, inputs: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """A queued or running run for the same ticker with the same
    effective inputs (``INPUT_KEYS``), as {run_id, status}, or None.
    Ticker comparison ignores case. A finished or failed run is never a
    duplicate — re-running yesterday's analysis is legitimate."""
    from sqlalchemy import func

    from src.storage import TieredRunRecord

    wanted = _digest_inputs(inputs or {})
    with _session() as session:
        rows = (
            session.query(TieredRunRecord)
            .filter(TieredRunRecord.status.in_(ACTIVE_STATUSES))
            .filter(func.upper(TieredRunRecord.ticker) == ticker.strip().upper())
            .order_by(TieredRunRecord.created_at.asc(), TieredRunRecord.id.asc())
            .all()
        )
        for row in rows:
            if _digest_inputs(_inputs_of(row)) == wanted:
                return {"run_id": row.run_id, "status": row.status}
    return None


def status_counts() -> Dict[str, int]:
    """How many runs sit in each status, every status present (0 when
    none) — the server-status route's queue figures."""
    from sqlalchemy import func

    from src.storage import TieredRunRecord

    counts = {status: 0 for status in ALL_STATUSES}
    with _session() as session:
        rows = (
            session.query(TieredRunRecord.status, func.count(TieredRunRecord.id))
            .group_by(TieredRunRecord.status)
            .all()
        )
    for status, count in rows:
        if status in counts:
            counts[status] = int(count or 0)
    return counts


def _queue_positions(session: Any) -> Dict[str, int]:
    """run_id -> the run's place in the line, from 1 (the page's
    "Queued (2nd)" wording)."""
    from src.storage import TieredRunRecord

    waiting = (
        session.query(TieredRunRecord.run_id)
        .filter_by(status=STATUS_QUEUED)
        .order_by(TieredRunRecord.created_at.asc(), TieredRunRecord.id.asc())
        .all()
    )
    return {run_id: position for position, (run_id,) in enumerate(waiting, start=1)}


# ---------------------------------------------------------------------------
# The run list: filters + one page at a time
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunFilters:
    """What the list endpoint can narrow the history by. Every field is
    optional; an empty list or None means "don't filter on this".
    Multi-value fields match any of their values. Ranges are inclusive
    and named after the row's fields; risk is a percent (1 = 1%), like
    the column. Datetimes are compared in UTC (aware values are converted, naive
    values are taken as UTC already)."""

    tickers: Sequence[str] = field(default_factory=tuple)
    statuses: Sequence[str] = field(default_factory=tuple)
    outlooks: Sequence[str] = field(default_factory=tuple)
    tiers: Sequence[int] = field(default_factory=tuple)
    max_hold_weeks: Sequence[int] = field(default_factory=tuple)
    capital_min: Optional[float] = None
    capital_max: Optional[float] = None
    risk_pct_min: Optional[float] = None
    risk_pct_max: Optional[float] = None
    reward_ratio_min: Optional[float] = None
    reward_ratio_max: Optional[float] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


def _apply_filters(query: Any, filters: RunFilters) -> Any:
    from sqlalchemy import and_, func, or_

    from src.storage import TieredRunRecord as R, to_utc_naive_datetime

    if filters.tickers:
        wanted = {ticker.strip().upper() for ticker in filters.tickers if ticker.strip()}
        query = query.filter(func.upper(R.ticker).in_(sorted(wanted)))
    if filters.statuses:
        query = query.filter(R.status.in_(list(filters.statuses)))
    if filters.outlooks:
        words = [word for word in filters.outlooks if word in OUTLOOK_WORDS]
        clauses = []
        if words:
            clauses.append(and_(R.status == STATUS_SUCCEEDED, R.outlook.in_(words)))
        if NO_OUTLOOK in filters.outlooks:
            clauses.append(or_(
                R.status != STATUS_SUCCEEDED,
                R.outlook.is_(None),
                R.outlook.notin_(list(OUTLOOK_WORDS)),
            ))
        query = query.filter(or_(*clauses))
    if filters.tiers:
        query = query.filter(R.tier.in_(list(filters.tiers)))
    if filters.max_hold_weeks:
        query = query.filter(R.max_hold_weeks.in_(list(filters.max_hold_weeks)))
    for column, low, high in (
        (R.capital, filters.capital_min, filters.capital_max),
        (R.risk_pct, filters.risk_pct_min, filters.risk_pct_max),
        (R.reward_ratio, filters.reward_ratio_min, filters.reward_ratio_max),
    ):
        if low is not None:
            query = query.filter(column >= low)
        if high is not None:
            query = query.filter(column <= high)
    if filters.created_after is not None:
        query = query.filter(R.created_at >= to_utc_naive_datetime(filters.created_after))
    if filters.created_before is not None:
        query = query.filter(R.created_at < to_utc_naive_datetime(filters.created_before))
    return query


def list_runs(
    filters: Optional[RunFilters] = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    """One page of run summaries, newest first, matching ``filters``:
    {items, page, page_size, total, page_count}. ``total`` counts every
    match, not just this page, so the caller can draw a page selector.
    A page past the end is empty, not an error. Summaries carry no
    report payload — that is ``get_run``."""
    from src.storage import TieredRunRecord

    safe_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    safe_page = max(1, int(page))
    with _session() as session:
        query = _apply_filters(session.query(TieredRunRecord), filters or RunFilters())
        total = int(query.order_by(None).count())
        rows = (
            query
            .order_by(TieredRunRecord.created_at.desc(), TieredRunRecord.id.desc())
            .offset((safe_page - 1) * safe_size)
            .limit(safe_size)
            .all()
        )
        positions = (
            _queue_positions(session)
            if any(row.status == STATUS_QUEUED for row in rows)
            else {}
        )
        items = [
            {**_row_summary(row), "queue_position": positions.get(row.run_id)}
            for row in rows
        ]
    return {
        "items": items,
        "page": safe_page,
        "page_size": safe_size,
        "total": total,
        "page_count": page_count(total, safe_size),
    }


def list_tickers() -> List[str]:
    """Every ticker that has ever been run, A-Z, for the ticker filter's
    dropdown (and for a caller asking "what have I analyzed?")."""
    from src.storage import TieredRunRecord

    with _session() as session:
        rows = session.query(TieredRunRecord.ticker).distinct().all()
    return sorted({code for (code,) in rows if code})


def _row_summary(row: Any) -> Dict[str, Any]:
    """The history row as clients see it: identity, status, timestamps,
    the run's inputs in the form's own words and order (ticker, capital,
    risk %, reward ratio, max hold weeks, tier), then the outlook and
    shares. The columns carry these same names, so nothing translates."""
    from src.storage import utc_iso

    return {
        "run_id": row.run_id,
        "ticker": row.ticker,
        "status": row.status,
        "error": row.error,
        "created_at": utc_iso(row.created_at),
        "updated_at": utc_iso(row.updated_at),
        "capital": row.capital,
        "risk_pct": row.risk_pct,
        "reward_ratio": row.reward_ratio,
        "max_hold_weeks": row.max_hold_weeks,
        "tier": row.tier,
        "outlook": row.outlook,
        "shares": row.shares,
    }


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def get_run(
    run_id: str,
    sections: Sequence[str] = ALL_SECTIONS,
    data_reports: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, Any]]:
    """One run: its summary row plus ``result``, the stored report cut
    down to ``sections`` (see report_sections.py; None while the run is
    unfinished or failed), and ``sections`` naming what ``result`` holds.
    None for an unknown run id."""
    from src.storage import TieredRunRecord

    with _session() as session:
        row = (
            session.query(TieredRunRecord)
            .filter_by(run_id=run_id)
            .one_or_none()
        )
        if row is None:
            return None
        summary = _row_summary(row)
        summary["queue_position"] = (
            _queue_positions(session).get(run_id)
            if row.status == STATUS_QUEUED
            else None
        )
        summary["sections"] = list(sections)
        summary["result"] = None
        if row.result_json:
            try:
                result = json.loads(row.result_json)
            except ValueError:
                summary["error"] = (
                    (summary["error"] or "")
                    + " stored result unreadable (corrupt JSON)"
                ).strip()
            else:
                summary["result"] = (
                    select_sections(result, sections, data_reports)
                    if isinstance(result, dict) else result
                )
        return summary


def get_vote_items(
    run_id: str,
    data_reports: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
    page: int = 1,
    page_size: int = DEFAULT_ITEM_PAGE_SIZE,
) -> Optional[Dict[str, Any]]:
    """One page of the run's deep-analysis vote items (see
    ``report_sections.page_vote_items``), or None for an unknown run
    id. A run without a deep-analysis record — tier 1, unfinished, failed, or
    its stored report unreadable — has an empty page, not an error."""
    from src.storage import TieredRunRecord

    with _session() as session:
        row = (
            session.query(TieredRunRecord.result_json)
            .filter_by(run_id=run_id)
            .one_or_none()
        )
        if row is None:
            return None
        result = _parse_result(row.result_json)
    return page_vote_items(
        deep_analysis_record(result), data_reports, statuses, page=page, page_size=page_size,
    )


def _parse_result(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """The stored report as a dict, None when absent or unreadable."""
    if not raw:
        return None
    try:
        result = json.loads(raw)
    except ValueError:
        return None
    return result if isinstance(result, dict) else None


def run_exists(run_id: str) -> bool:
    from src.storage import TieredRunRecord

    with _session() as session:
        return session.query(
            session.query(TieredRunRecord.id).filter_by(run_id=run_id).exists()
        ).scalar()


def get_run_summary(run_id: str) -> Optional[Dict[str, Any]]:
    """The run's history row alone (no report, no queue position) — what
    a client needs to name a run before acting on it. None for an
    unknown run id."""
    from src.storage import TieredRunRecord

    with _session() as session:
        row = (
            session.query(TieredRunRecord)
            .filter_by(run_id=run_id)
            .one_or_none()
        )
        return _row_summary(row) if row is not None else None


def _inputs_of(row: Any) -> Dict[str, Any]:
    """The row's stored inputs as a dict, {} when absent/unreadable — old
    rows never break the queue."""
    raw = getattr(row, "inputs_json", None)
    if not raw:
        return {}
    try:
        inputs = json.loads(raw)
    except ValueError:
        return {}
    return inputs if isinstance(inputs, dict) else {}


def _digest_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Just the ``DUPLICATE_KEYS`` that are set — what the duplicate
    check compares."""
    return {key: inputs[key] for key in DUPLICATE_KEYS if inputs.get(key) is not None}


# ---------------------------------------------------------------------------
# Transcripts: an index of calls, then one call at a time
# ---------------------------------------------------------------------------

#: The transcript columns every index row carries (everything but the
#: input and output text, which is what makes a transcript big).
_TRANSCRIPT_FACTS = (
    "call_number", "created_at", "stage", "llm", "temperature", "time_ms",
    "input_tokens", "output_tokens", "structured", "error",
)


def _transcript_facts(row: Any) -> Dict[str, Any]:
    from src.storage import utc_iso

    facts = {name: getattr(row, name) for name in _TRANSCRIPT_FACTS}
    facts["created_at"] = utc_iso(facts["created_at"])
    return facts


def list_transcript(run_id: str) -> List[Dict[str, Any]]:
    """The run's LLM calls in call order, as an index: every fact about
    each call plus the size of its input and output in characters
    (``input_chars``/``output_chars``), but not the text itself — see
    ``get_transcript_call``. Empty for unknown runs and runs that made no
    LLM call. The text columns are never loaded here."""
    from sqlalchemy import func

    from src.storage import TieredRunTranscriptRecord as T

    with _session() as session:
        rows = (
            session.query(
                *(getattr(T, name) for name in _TRANSCRIPT_FACTS),
                func.length(T.input).label("input_chars"),
                func.length(T.output).label("output_chars"),
            )
            .filter(T.run_id == run_id)
            .order_by(T.call_number.asc())
            .all()
        )
        return [
            {
                **_transcript_facts(row),
                "input_chars": int(row.input_chars or 0),
                "output_chars": int(row.output_chars or 0),
            }
            for row in rows
        ]


def get_transcript_call(run_id: str, call_number: int) -> Optional[Dict[str, Any]]:
    """One LLM call of a run, with its full input and raw output, or None
    when the run has no call numbered ``call_number``."""
    from src.storage import TieredRunTranscriptRecord

    with _session() as session:
        row = (
            session.query(TieredRunTranscriptRecord)
            .filter_by(run_id=run_id, call_number=call_number)
            .one_or_none()
        )
        if row is None:
            return None
        return {**_transcript_facts(row), "input": row.input, "output": row.output}


def prune_transcripts(max_age_days: int = TRANSCRIPT_MAX_AGE_DAYS) -> int:
    """Delete transcript rows older than ``max_age_days``; returns the count."""
    from src.storage import TieredRunTranscriptRecord, utc_naive_now

    cutoff = utc_naive_now() - timedelta(days=max_age_days)
    with _session() as session:
        deleted = (
            session.query(TieredRunTranscriptRecord)
            .filter(TieredRunTranscriptRecord.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        session.commit()
        return int(deleted or 0)
