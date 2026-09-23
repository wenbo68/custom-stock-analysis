# -*- coding: utf-8 -*-
"""Tiered-analysis API: run tier 1 for a symbol from the web UI.

A full run takes minutes (data fetch + LLM), so POST /analyze returns a
task id immediately; the run executes in a background thread. Runs
persist in the tiered_runs table (src/tiered_analysis/history.py), so
GET /runs serves a clickable history that survives page navigation and
server restarts — one page at a time, filtered in SQL — and
GET /runs/{task_id} returns the stored report, whole or by section.
A run's LLM transcript is served as an index (GET .../transcript) plus
one call at a time (GET .../transcript/{seq}), since the text of every
call together runs to half a megabyte; the deep-analysis vote items are
paged the same way (GET .../debate/items). DELETE /runs/{task_id}
removes a run — a queued one is thereby cancelled — and GET /status says
what the server can do right now (2026-09-21, for the chatbot: the
model, the data sources, the run slots, the defaults, each market's
clock), so a client can explain a refusal before it happens.

Request and response shapes live in tiered_schemas.py so /docs shows
both sides of every route.

Self-host: one person, one machine. There is no sign-in; the model and
its API key come from the environment (``MAIN_LLM`` and ``LLM_API_KEY``,
see .env.example), and every run is visible in the history.

Run queue (2026-09-15): a new run is stored ``queued`` and the global
queue (src/tiered_analysis/run_queue.py) starts it when one of the
``MAX_CONCURRENT_RUNS`` slots is free. An exact duplicate of an
unfinished run (same ticker and inputs) is refused with a 409 naming
that run, so a double click never pays twice.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.endpoints.tiered_schemas import (
    AnalyzeAccepted,
    DebateItemPage,
    DebateItemStatus,
    OutlookFilter,
    RunDeleted,
    RunDetail,
    RunPage,
    RunStatus,
    Section,
    ServerStatus,
    TickerList,
    TieredAnalyzeRequest,
    TranscriptCall,
    TranscriptIndex,
)
from src.tiered_analysis import history, report_sections
from src.tiered_analysis.llm_support import LlmTranscript
from src.tiered_analysis.run_context import llm_model
from src.tiered_analysis.run_queue import QueuedRun, RunQueue

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_analysis(stock_code: str, depth: int = 1,
                  sizing_overrides: Optional[Dict[str, float]] = None,
                  hold_weeks: int = 2,
                  transcript: Optional[LlmTranscript] = None):
    """Indirection so tests can patch the multi-minute production run."""
    from src.tiered_analysis.integration import run_tiered_analysis

    return run_tiered_analysis(
        stock_code, depth=depth, sizing_overrides=sizing_overrides,
        hold_weeks=hold_weeks, transcript=transcript,
    )


def _serialize_levels(levels: Any) -> Dict[str, Any]:
    return {
        "entry": levels.entry,
        "stop_loss": levels.stop_loss,
        "take_profit": levels.take_profit,
    }


def _serialize_tier_section(report: Any) -> Optional[Dict[str, Any]]:
    """Tier 2 section: outlook + audit trail, no dimension duplication."""
    if report is None:
        return None
    section: Dict[str, Any] = {
        "tier": report.tier,
        "outlook": report.outlook.value,
        "confidence": report.confidence,
        "score": report.score,
        "levels": _serialize_levels(report.levels),
        "narrative": report.narrative,
        "warnings": list(report.warnings),
    }
    if report.debate_detail is not None:
        section["debate_detail"] = report.debate_detail
    return section


def _serialize_outcome(outcome: Any) -> Dict[str, Any]:
    report = outcome.report
    dimensions = []
    for dim in report.dimensions:
        dimensions.append({
            "dimension": dim.dimension,
            "kind": dim.kind.value,
            "is_actionable": dim.is_actionable,
            "payload": dim.payload,
            # UI formula receipts for derived metrics (technicals v2);
            # None on other dimensions and old runs.
            "formulas": dim.formulas,
            "narrative": dim.narrative,
            "warnings": list(dim.warnings),
            # The same notes keyed by the payload field ("group.key")
            # each is about; None on old stored runs.
            "field_notes": dim.field_notes,
            "citations": [
                {
                    "source_name": c.source_name,
                    "url": c.url,
                    "title": c.title,
                    "snippet": c.snippet,
                }
                for c in (dim.citations or [])
            ],
        })

    state_reports = getattr(outcome.state, "reports", {}) or {}
    final = outcome.final_report or report
    return {
        "symbol": report.symbol,
        "market": report.market.value,
        "tier": report.tier,
        "score": report.score,
        "confidence": report.confidence,
        "levels": _serialize_levels(report.levels),
        "levels_detail": report.levels_detail,
        "narrative": report.narrative,
        "warnings": list(report.warnings),
        # The quick judge's 0-10 outlook (depth 1); None at depth 2, whose
        # judge detail sits under ``tier2``.
        "debate_detail": report.debate_detail,
        "dimensions": dimensions,
        # v2 slice 6 (additive): depth, deeper-tier sections, sizing, cost.
        "depth": outcome.depth,
        "final": {
            "tier": final.tier,
            "outlook": final.outlook.value,
            "action": outcome.action.value,
            "confidence": final.confidence,
            "levels": _serialize_levels(final.levels),
        },
        "tier2": _serialize_tier_section(state_reports.get(2)),
        "sizing": outcome.sizing,
        "llm_usage": outcome.llm_usage,
        # Outlook redesign (additive): the impersonal judgment, the
        # personal action, and the earnings date (displayed on the
        # fundamentals card; kept here for old consumers).
        "outlook": outcome.outlook.value,
        "action": outcome.action.value,
        "earnings": outcome.earnings.to_detail() if outcome.earnings else None,
        # Plan review (additive): structured per-column trade-plan
        # warnings — numbers only, the frontend words them.
        "plan_warnings": outcome.plan_warnings,
        # Max hold time (additive, 2026-08-08): the horizon in weeks the
        # AI was judged against; absent on old stored runs.
        "hold_weeks": getattr(outcome, "hold_weeks", None),
    }


def _execute_run(run: QueuedRun) -> None:
    """The queue's runner: execute one run and record its outcome. Never
    raises — a failure lands on the run row."""
    try:
        inputs = run.inputs
        outcome = _run_analysis(
            run.stock_code,
            depth=int(inputs.get("tier") or 1),
            sizing_overrides=inputs.get("sizing_overrides") or None,
            hold_weeks=int(inputs.get("hold_weeks") or 2),
            transcript=LlmTranscript.for_run(run.task_id),
        )
        history.mark_done(run.task_id, _serialize_outcome(outcome))
    except Exception as exc:
        logger.error("tiered analysis task failed for %s: %s",
                     run.stock_code, exc, exc_info=True)
        history.mark_failed(run.task_id, str(exc))


#: The one queue this process runs; app startup calls ``resume`` on it.
run_queue = RunQueue(_execute_run)

#: Serializes the duplicate check with the row insert so two clicks that
#: arrive together cannot both pass the check.
_submit_lock = threading.Lock()


def _effective_run_inputs(request: TieredAnalyzeRequest) -> Dict[str, Any]:
    """The settings the run will actually use — request overrides on top
    of the form defaults (the same resolution run_tiered_analysis
    performs) — recorded on the run row so history shows them while the
    run is still in flight."""
    from src.tiered_analysis.settings import SizingSettings, merge_overrides

    sizing = request.sizing
    settings = merge_overrides(
        SizingSettings(),
        capital=sizing.capital if sizing else None,
        risk_fraction=sizing.risk_fraction if sizing else None,
        reward_risk=sizing.reward_risk if sizing else None,
    )
    return {
        "tier": request.depth,
        "capital": settings.capital,
        "risk_fraction": settings.risk_fraction,
        "reward_risk": settings.reward_risk,
        "hold_weeks": request.hold_weeks,
    }


class RunRefused(Exception):
    """A run request the server will not take: the HTTP status and the
    structured detail the route answers with. Raised by ``submit_run`` so
    the second client (the chatbot, which calls it directly rather than
    over HTTP) gets the same refusals as readable results."""

    def __init__(self, status_code: int, detail: Dict[str, Any]) -> None:
        super().__init__(detail.get("message") or detail.get("code") or str(detail))
        self.status_code = status_code
        self.detail = detail


def _require_llm_configured() -> None:
    """Refuse (400) when no model is configured — the run would only
    fail minutes later otherwise. The key (``LLM_API_KEY``) is only
    checked at call time, since litellm can also read the provider's
    own variable."""
    if llm_model() is None:
        raise RunRefused(400, {
            "error": "llm_not_configured",
            "message": "set MAIN_LLM and LLM_API_KEY in .env first",
        })


def submit_run(request: TieredAnalyzeRequest) -> Dict[str, Any]:
    """Store a run and hand it to the queue — the whole of what
    ``POST /analyze`` does, as a function, so every client (the web
    page over HTTP, the chatbot in-process) starts runs through one
    path: the model check, the market clock gate, the duplicate refusal
    and the queue. Returns the accepted document (task_id, stock_code,
    depth, status); raises ``RunRefused`` with the route's status and
    detail for every refusal."""
    from src.tiered_analysis.run_gate import clock_gate

    _require_llm_configured()
    gate = clock_gate(request.stock_code, override=request.run_anyway)
    if gate.blocked:
        logger.info(
            "tiered run blocked by clock gate for %s (%s)",
            request.stock_code, gate.detail,
        )
        # Session bounds ride along (ISO, market-local offset embedded) so
        # the popup can word the hours in market time AND the user's time.
        detail: Dict[str, Any] = {"code": "market_open", "market": gate.market}
        if gate.session_open is not None and gate.session_close is not None:
            detail["session_open"] = gate.session_open.isoformat()
            detail["session_close"] = gate.session_close.isoformat()
        raise RunRefused(409, detail)

    inputs = _effective_run_inputs(request)
    if request.sizing is not None:
        overrides = request.sizing.model_dump(exclude_none=True)
        if overrides:
            inputs["sizing_overrides"] = overrides

    with _submit_lock:
        duplicate = history.find_active_duplicate(request.stock_code, inputs)
        if duplicate is not None:
            logger.info("tiered run refused as a duplicate of %s for %s",
                        duplicate["task_id"], request.stock_code)
            raise RunRefused(409, {
                "code": "duplicate_run",
                "task_id": duplicate["task_id"],
                "status": duplicate["status"],
            })
        task_id = uuid.uuid4().hex
        history.create_run(task_id, request.stock_code, inputs=inputs,
                           status=history.STATUS_QUEUED)
    status = run_queue.submit(task_id)
    return {"task_id": task_id, "stock_code": request.stock_code,
            "depth": request.depth, "status": status}


@router.post("/analyze", status_code=202, response_model=AnalyzeAccepted)
def start_tiered_analysis(request: TieredAnalyzeRequest) -> Dict[str, Any]:
    """Start a run.

    The run is stored and executes in the background; poll
    `GET /runs/{task_id}` (or the list) for its status.

    - 400 `llm_not_configured`: no model set in .env.
    - 409 `market_open`: the ticker's market is inside its trading day
      (runs analyze completed sessions only). The body carries the market
      and today's session bounds; send `run_anyway: true` to analyze the
      previous completed session instead.
    - 409 `duplicate_run`: a queued or running run has the same ticker
      and inputs; the body names it (`task_id`, `status`).
    """
    try:
        return submit_run(request)
    except RunRefused as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/status", response_model=ServerStatus)
def get_server_status() -> Dict[str, Any]:
    """What this server can do right now.

    The model that will answer (and whether a key is set; the key itself
    is never reported), which data sources are configured, how many run
    slots exist and how many runs hold or wait for one, what a run uses
    when the request leaves a field out, how long transcripts are kept,
    and where each market's clock stands — runs are refused during the
    trading day, so this says when they are accepted again. Also the
    server's own time, UTC.
    """
    from src.tiered_analysis.server_status import server_status

    return server_status()


@router.get("/runs", response_model=RunPage)
def list_tiered_runs(
    ticker: Optional[List[str]] = Query(
        default=None, description="Keep these tickers (any of; case-insensitive).",
    ),
    status: Optional[List[RunStatus]] = Query(default=None, description="Any of."),
    outlook: Optional[List[OutlookFilter]] = Query(
        default=None,
        description="Any of. `none` = rows with no opinion (unfinished, failed, or unknown).",
    ),
    tier: Optional[List[int]] = Query(default=None, description="Any of 1, 2."),
    hold_weeks: Optional[List[int]] = Query(default=None, description="Any of 1-4."),
    capital_min: Optional[float] = Query(default=None, ge=0),
    capital_max: Optional[float] = Query(default=None, ge=0),
    risk_min: Optional[float] = Query(
        default=None, ge=0, le=1, description="Fraction: 0.01 = 1%.",
    ),
    risk_max: Optional[float] = Query(default=None, ge=0, le=1),
    reward_min: Optional[float] = Query(default=None, ge=0),
    reward_max: Optional[float] = Query(default=None, ge=0),
    created_after: Optional[datetime] = Query(
        default=None, description="ISO 8601; inclusive. Naive values are UTC.",
    ),
    created_before: Optional[datetime] = Query(
        default=None, description="ISO 8601; exclusive. Naive values are UTC.",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=history.DEFAULT_PAGE_SIZE, ge=1, le=history.MAX_PAGE_SIZE,
    ),
) -> Dict[str, Any]:
    """One page of the run history, newest first, filtered in the database.

    Every filter is optional and they combine with AND; a multi-value
    filter matches any of its values (repeat the parameter:
    `?status=queued&status=running`). Ranges are inclusive. Rows carry
    the list facts only — fetch a report with `GET /runs/{task_id}`.
    """
    filters = history.RunFilters(
        tickers=tuple(ticker or ()),
        statuses=tuple(status or ()),
        outlooks=tuple(outlook or ()),
        tiers=tuple(tier or ()),
        hold_weeks=tuple(hold_weeks or ()),
        capital_min=capital_min,
        capital_max=capital_max,
        risk_min=risk_min,
        risk_max=risk_max,
        reward_min=reward_min,
        reward_max=reward_max,
        created_after=created_after,
        created_before=created_before,
    )
    return history.list_runs(filters, page=page, page_size=page_size)


@router.get("/runs/tickers", response_model=TickerList)
def list_tiered_tickers() -> Dict[str, List[str]]:
    """Every ticker that has ever been run, A-Z (the ticker filter's choices)."""
    return {"items": history.list_tickers()}


@router.get("/runs/{task_id}", response_model=RunDetail)
def get_tiered_run(
    task_id: str,
    section: Optional[List[Section]] = Query(
        default=None,
        description=(
            "Which parts of the report to include (repeat to combine). "
            "Omit for everything. `core` (headline facts, a few KB) is always "
            "included; `dimensions` is the data reports (~60 KB), `debate` the "
            "deep-analysis overview (~10 KB: outlook, summary outline, pools, "
            "item count — the vote items themselves are paged at "
            "`GET /runs/{task_id}/debate/items`), `plan` the trade-plan receipt."
        ),
    ),
    dimension: Optional[List[str]] = Query(
        default=None,
        description=(
            "With the dimensions section: keep only these data reports, e.g. "
            "technicals, fundamentals, positioning, macro_economy, opinion, "
            "company_news, world_news."
        ),
    ),
) -> Dict[str, Any]:
    """One run with its stored report, whole or by section.

    `result` is null while the run is queued or running and after a
    failure (see `status` and `error`). Whatever the sections, `result`
    carries `dimension_index`: one light row per data report (name, kind,
    whether it counted, warnings). 404 for an unknown task id.
    """
    from src.tiered_analysis.report_sections import normalize_sections

    run = history.get_run(
        task_id, sections=normalize_sections(section), dimensions=dimension,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.delete("/runs/{task_id}", response_model=RunDeleted)
def delete_tiered_run(task_id: str) -> Dict[str, Any]:
    """Delete a run and its transcript.

    A queued run is taken out of the line — this is how a run is
    cancelled. A finished or failed run is removed from the history.

    - 404: unknown task id.
    - 409 `run_in_progress`: the run is executing and cannot be stopped;
      wait for it to finish or fail, then delete it.
    """
    try:
        deleted = run_queue.remove(task_id)
    except history.RunInProgressError:
        raise HTTPException(status_code=409, detail={
            "code": "run_in_progress", "task_id": task_id,
        })
    if deleted is None:
        raise HTTPException(status_code=404, detail="run not found")
    logger.info("tiered run %s (%s, %s) deleted",
                task_id, deleted["stock_code"], deleted["status"])
    return {
        "task_id": deleted["task_id"],
        "stock_code": deleted["stock_code"],
        "status": deleted["status"],
    }


@router.get("/runs/{task_id}/debate/items", response_model=DebateItemPage)
def list_tiered_debate_items(
    task_id: str,
    dimension: Optional[List[str]] = Query(
        default=None,
        description="Keep items about these data reports (any of), e.g. technicals, company_news.",
    ),
    status: Optional[List[DebateItemStatus]] = Query(
        default=None, description="Any of: counted, excluded.",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=report_sections.DEFAULT_ITEM_PAGE_SIZE,
        ge=1, le=report_sections.MAX_ITEM_PAGE_SIZE,
    ),
) -> Dict[str, Any]:
    """One page of a deep-analysis run's vote items.

    Each item is one piece of evidence the listers raised and the
    checkers voted on; `final_status` says whether it counted toward the
    score. Filters combine with AND. A run without a deep-analysis record
    (tier 1, unfinished, failed) has an empty page; 404 for an unknown
    task id.
    """
    items = history.get_debate_items(
        task_id, dimensions=dimension, statuses=status,
        page=page, page_size=page_size,
    )
    if items is None:
        raise HTTPException(status_code=404, detail="run not found")
    return items


@router.get("/runs/{task_id}/transcript", response_model=TranscriptIndex)
def get_tiered_run_transcript(task_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """The run's LLM calls in call order, without their text.

    Each row carries the call's facts (step, model, time, tokens, error)
    and the size of its prompt and reply in characters; fetch the text
    of one call with `GET /runs/{task_id}/transcript/{seq}`. Empty when
    the run made no call or its rows expired (kept 14 days). 404 for an
    unknown task id.
    """
    if not history.run_exists(task_id):
        raise HTTPException(status_code=404, detail="run not found")
    return {"items": history.list_transcript(task_id)}


@router.get("/runs/{task_id}/transcript/{seq}", response_model=TranscriptCall)
def get_tiered_run_transcript_call(task_id: str, seq: int) -> Dict[str, Any]:
    """One LLM call of a run with its full prompt and raw reply.

    404 when the run is unknown or has no call numbered `seq`.
    """
    call = history.get_transcript_call(task_id, seq)
    if call is None:
        raise HTTPException(status_code=404, detail="transcript call not found")
    return call
