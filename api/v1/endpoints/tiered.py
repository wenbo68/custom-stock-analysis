# -*- coding: utf-8 -*-
"""Tiered-analysis API: start a run from the analysis page or the chat.

A full run takes minutes (data fetch + LLM), so POST /analyze returns a
run id immediately; the run executes in a background thread. Runs
persist in the tiered_runs table (src/tiered_analysis/history.py), so
GET /runs serves a clickable history that survives page navigation and
server restarts — one page at a time, filtered in SQL — and
GET /runs/{run_id} returns the stored report, whole or by section.
A run's LLM transcript is served as an index (GET .../transcript) plus
one call at a time (GET .../transcript/{call_number}), since the text of
every call together runs to half a megabyte; the deep-analysis vote
items are paged the same way (GET .../vote_items). DELETE /runs/{run_id}
removes a run — a queued one is thereby cancelled — and GET /status says
what the server can do right now (2026-09-21, for the chat bot: the
model, the data sources, the run slots, the defaults, each market's
clock), so a client can explain a refusal before it happens.

Request and response shapes live in tiered_schemas.py so /docs shows
both sides of every route. Every name a client sends or reads is the
analysis page's own word for the thing (owner request 2026-09-24), and
the engine and the database use the same words, so nothing translates.
A query parameter the route does not know is refused with a 422 rather
than silently ignored (owner request 2026-09-24).

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

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.v1.endpoints.tiered_schemas import (
    AnalyzeAccepted,
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
    VoteItemPage,
    VoteItemStatus,
)
from src.languages import DEFAULT_LANGUAGE
from src.tiered_analysis import history, report_sections
from src.tiered_analysis.llm_support import LlmTranscript
from src.tiered_analysis.run_context import llm_model
from src.tiered_analysis.run_queue import QueuedRun, RunQueue
from src.tiered_analysis.settings import SizingSettings, merge_overrides

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_analysis(ticker: str, tier: int = 1,
                  sizing: Optional[SizingSettings] = None,
                  max_hold_weeks: int = 2,
                  transcript: Optional[LlmTranscript] = None,
                  language: str = DEFAULT_LANGUAGE):
    """Indirection so tests can patch the multi-minute production run."""
    from src.tiered_analysis.integration import run_tiered_analysis

    return run_tiered_analysis(
        ticker, tier=tier, sizing_settings=sizing,
        max_hold_weeks=max_hold_weeks, transcript=transcript,
        language=language,
    )


def _serialize_levels(levels: Any) -> Dict[str, Any]:
    return {
        "entry": levels.entry,
        "stop_loss": levels.stop_loss,
        "target": levels.target,
    }


def _serialize_tier_section(report: Any) -> Optional[Dict[str, Any]]:
    """The deep-analysis section: outlook + its record, no data-report
    duplication."""
    if report is None:
        return None
    section: Dict[str, Any] = {
        "tier": report.tier,
        "outlook": report.outlook.value,
        "confidence": report.confidence,
        "score": report.score,
        "levels": _serialize_levels(report.levels),
        "summary": report.summary,
        "warnings": list(report.warnings),
    }
    if report.detail is not None:
        section["detail"] = report.detail
    return section


def _serialize_outcome(outcome: Any) -> Dict[str, Any]:
    report = outcome.report
    data_reports = []
    for dim in report.data_reports:
        data_reports.append({
            "name": dim.name,
            "kind": dim.kind.value,
            "counted": dim.counted,
            "payload": dim.payload,
            # UI formula receipts for derived metrics (technicals v2);
            # None on other data reports and old runs.
            "formulas": dim.formulas,
            "summary": dim.summary,
            "warnings": list(dim.warnings),
            # The same warnings keyed by the payload field ("group.key")
            # each is about; None on old stored runs.
            "field_warnings": dim.field_warnings,
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
        "ticker": report.ticker,
        "market": report.market.value,
        # The tier the run was asked for (1 or 2), as the form names it.
        "tier": outcome.tier,
        "score": report.score,
        "confidence": report.confidence,
        "levels": _serialize_levels(report.levels),
        "levels_detail": report.levels_detail,
        "summary": report.summary,
        "warnings": list(report.warnings),
        # The preliminary analysis's 0-10 outlook (tier 1); None on a
        # tier-2 run, whose record sits under ``deep_analysis``.
        "preliminary_analysis": report.detail,
        "data_reports": data_reports,
        "final": {
            "tier": final.tier,
            "outlook": final.outlook.value,
            "action": outcome.action.value,
            "confidence": final.confidence,
            "levels": _serialize_levels(final.levels),
        },
        "deep_analysis": _serialize_tier_section(state_reports.get(2)),
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
        # Max hold time (2026-08-08): the horizon in weeks the AI was
        # judged against.
        "max_hold_weeks": outcome.max_hold_weeks,
    }


def _execute_run(run: QueuedRun) -> None:
    """The queue's runner: execute one run and record its outcome. Never
    raises — a failure lands on the run row."""
    try:
        inputs = run.inputs
        outcome = _run_analysis(
            run.ticker,
            tier=int(inputs.get("tier") or 1),
            sizing=_sizing_of(inputs),
            max_hold_weeks=int(inputs.get("max_hold_weeks") or 2),
            transcript=LlmTranscript.for_run(run.run_id),
            language=str(inputs.get("language") or DEFAULT_LANGUAGE),
        )
        history.mark_done(run.run_id, _serialize_outcome(outcome))
    except Exception as exc:
        logger.error("tiered analysis task failed for %s: %s",
                     run.ticker, exc, exc_info=True)
        history.mark_failed(run.run_id, str(exc))


#: The one queue this process runs; app startup calls ``resume`` on it.
run_queue = RunQueue(_execute_run)

#: Serializes the duplicate check with the row insert so two clicks that
#: arrive together cannot both pass the check.
_submit_lock = threading.Lock()


def _sizing_of(inputs: Dict[str, Any]) -> SizingSettings:
    """The sizing settings a stored run row asks for (its capital, risk %
    and reward ratio), for ``run_tiered_analysis``."""
    return merge_overrides(
        SizingSettings(),
        capital=inputs.get("capital"),
        risk_pct=inputs.get("risk_pct"),
        reward_ratio=inputs.get("reward_ratio"),
    )


def _effective_run_inputs(request: TieredAnalyzeRequest) -> Dict[str, Any]:
    """The settings the run will actually use — the request's values on
    top of the form defaults — in the form's words and order, recorded
    on the run row so history shows them while the run is still in
    flight and the queue hands them to the engine."""
    sizing = merge_overrides(
        SizingSettings(),
        capital=request.capital,
        risk_pct=request.risk_pct,
        reward_ratio=request.reward_ratio,
    )
    return {
        "capital": sizing.capital,
        "risk_pct": sizing.risk_pct,
        "reward_ratio": sizing.reward_ratio,
        "max_hold_weeks": request.max_hold_weeks,
        "tier": request.tier,
        "language": request.language,
    }


def effective_inputs(request: TieredAnalyzeRequest) -> Dict[str, Any]:
    """The run's inputs as the user words them — every default filled
    in, in the form's order — so a client (the chat's confirmation) can
    show exactly what the run will use."""
    return {
        "ticker": request.ticker,
        **_effective_run_inputs(request),
        "run_anyway": request.run_anyway,
    }


class RunRefused(Exception):
    """A run request the server will not take: the HTTP status and the
    structured detail the route answers with. Raised by ``submit_run`` so
    the second client (the chat bot, which calls it directly rather than
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
    page over HTTP, the chat bot in-process) starts runs through one
    path: the model check, the market-open check, the duplicate refusal
    and the queue. Returns the accepted document (run_id, ticker, tier,
    status); raises ``RunRefused`` with the route's status and detail
    for every refusal."""
    from src.tiered_analysis.run_gate import market_open_check

    _require_llm_configured()
    gate = market_open_check(request.ticker, run_anyway=request.run_anyway)
    if gate.blocked:
        logger.info(
            "tiered run blocked by the market-open check for %s (%s)",
            request.ticker, gate.detail,
        )
        # Session bounds ride along (ISO, market-local offset embedded) so
        # the popup can word the hours in market time AND the user's time.
        detail: Dict[str, Any] = {"code": "market_open", "market": gate.market}
        if gate.session_open is not None and gate.session_close is not None:
            detail["session_open"] = gate.session_open.isoformat()
            detail["session_close"] = gate.session_close.isoformat()
        raise RunRefused(409, detail)

    inputs = _effective_run_inputs(request)

    with _submit_lock:
        duplicate = history.find_active_duplicate(request.ticker, inputs)
        if duplicate is not None:
            logger.info("tiered run refused as a duplicate of %s for %s",
                        duplicate["run_id"], request.ticker)
            raise RunRefused(409, {
                "code": "duplicate_run",
                "run_id": duplicate["run_id"],
                "status": duplicate["status"],
            })
        run_id = uuid.uuid4().hex
        history.create_run(run_id, request.ticker, inputs=inputs,
                           status=history.STATUS_QUEUED)
    status = run_queue.submit(run_id)
    return {"run_id": run_id, "ticker": request.ticker,
            "tier": request.tier, "status": status}


@router.post("/analyze", status_code=202, response_model=AnalyzeAccepted)
def start_tiered_analysis(request: TieredAnalyzeRequest) -> Dict[str, Any]:
    """Start a run.

    The run is stored and executes in the background; poll
    `GET /runs/{run_id}` (or the list) for its status.

    - 400 `llm_not_configured`: no model set in .env.
    - 409 `market_open`: the ticker's market is inside its trading day
      (runs analyze completed sessions only). The body carries the market
      and today's session bounds; send `run_anyway: true` to analyze the
      previous completed session instead.
    - 409 `duplicate_run`: a queued or running run has the same ticker
      and inputs; the body names it (`run_id`, `status`).
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


def _known_query_params(route: Any) -> set:
    """The query parameter names a route declares."""
    return {param.alias for param in route.dependant.query_params}


def reject_unknown_query_params(request: Request) -> None:
    """Refuse (422) a query parameter the route does not declare, naming
    it — an old or misspelled filter must never silently return an
    unfiltered list (owner request 2026-09-24)."""
    route = request.scope.get("route")
    if route is None:
        return
    known = _known_query_params(route)
    unknown = sorted(name for name in request.query_params if name not in known)
    if unknown:
        raise HTTPException(status_code=422, detail={
            "code": "unknown_query_params",
            "unknown": unknown,
            "known": sorted(known),
            "message": (
                f"unknown query parameter(s): {', '.join(unknown)}; "
                f"this route takes: {', '.join(sorted(known))}"
            ),
        })


@router.get("/runs", response_model=RunPage, dependencies=[Depends(reject_unknown_query_params)])
def list_tiered_runs(
    ticker: Optional[List[str]] = Query(
        default=None, description="Keep these tickers (any of; case-insensitive).",
    ),
    status: Optional[List[RunStatus]] = Query(default=None, description="Any of."),
    outlook: Optional[List[OutlookFilter]] = Query(
        default=None,
        description="Any of. `no_outlook` = rows with no outlook (unfinished, failed, or the analysis produced none).",
    ),
    capital_min: Optional[float] = Query(default=None, ge=0),
    capital_max: Optional[float] = Query(default=None, ge=0),
    risk_pct_min: Optional[float] = Query(
        default=None, ge=0, le=100, description="Percent: 1 = 1%.",
    ),
    risk_pct_max: Optional[float] = Query(default=None, ge=0, le=100),
    reward_ratio_min: Optional[float] = Query(default=None, ge=0),
    reward_ratio_max: Optional[float] = Query(default=None, ge=0),
    max_hold_weeks: Optional[List[int]] = Query(default=None, description="Any of 1-4."),
    tier: Optional[List[int]] = Query(default=None, description="Any of 1, 2."),
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
    the list facts only — fetch a report with `GET /runs/{run_id}`.
    An unknown query parameter is a 422 `unknown_query_params`.
    """
    filters = history.RunFilters(
        tickers=tuple(ticker or ()),
        statuses=tuple(status or ()),
        outlooks=tuple(outlook or ()),
        tiers=tuple(tier or ()),
        max_hold_weeks=tuple(max_hold_weeks or ()),
        capital_min=capital_min,
        capital_max=capital_max,
        risk_pct_min=risk_pct_min,
        risk_pct_max=risk_pct_max,
        reward_ratio_min=reward_ratio_min,
        reward_ratio_max=reward_ratio_max,
        created_after=created_after,
        created_before=created_before,
    )
    return history.list_runs(filters, page=page, page_size=page_size)


@router.get("/runs/tickers", response_model=TickerList)
def list_tiered_tickers() -> Dict[str, List[str]]:
    """Every ticker that has ever been run, A-Z (the ticker filter's choices)."""
    return {"items": history.list_tickers()}


@router.get("/runs/{run_id}", response_model=RunDetail, dependencies=[Depends(reject_unknown_query_params)])
def get_tiered_run(
    run_id: str,
    section: Optional[List[Section]] = Query(
        default=None,
        description=(
            "Which parts of the report to include (repeat to combine). "
            "Omit for everything. `core` (headline facts, a few KB) is always "
            "included; `data_reports` is the data reports (~60 KB), "
            "`deep_analysis` the deep-analysis overview (~10 KB: outlook, "
            "summary outline, pools, item count — the vote items themselves are "
            "paged at `GET /runs/{run_id}/vote_items`), `plan` the trade-plan receipt."
        ),
    ),
    data_report: Optional[List[str]] = Query(
        default=None,
        description=(
            "With the data_reports section: keep only these data reports, e.g. "
            "technicals, fundamentals, positioning, macro_economy, "
            "company_news, world_news."
        ),
    ),
) -> Dict[str, Any]:
    """One run with its stored report, whole or by section.

    `result` is null while the run is queued or running and after a
    failure (see `status` and `error`). Whatever the sections, `result`
    carries `data_report_index`: one light row per data report (name, kind,
    whether it counted, warnings). 404 for an unknown run id.
    """
    from src.tiered_analysis.report_sections import normalize_sections

    run = history.get_run(
        run_id, sections=normalize_sections(section), data_reports=data_report,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.delete("/runs/{run_id}", response_model=RunDeleted)
def delete_tiered_run(run_id: str) -> Dict[str, Any]:
    """Delete a run and its transcript.

    A queued run is taken out of the line — this is how a run is
    cancelled. A finished or failed run is removed from the history.

    - 404: unknown run id.
    - 409 `run_in_progress`: the run is executing and cannot be stopped;
      wait for it to finish or fail, then delete it.
    """
    try:
        deleted = run_queue.remove(run_id)
    except history.RunInProgressError:
        raise HTTPException(status_code=409, detail={
            "code": "run_in_progress", "run_id": run_id,
        })
    if deleted is None:
        raise HTTPException(status_code=404, detail="run not found")
    logger.info("tiered run %s (%s, %s) deleted",
                run_id, deleted["ticker"], deleted["status"])
    return {
        "run_id": deleted["run_id"],
        "ticker": deleted["ticker"],
        "status": deleted["status"],
    }


@router.get("/runs/{run_id}/vote_items", response_model=VoteItemPage, dependencies=[Depends(reject_unknown_query_params)])
def list_tiered_vote_items(
    run_id: str,
    data_report: Optional[List[str]] = Query(
        default=None,
        description="Keep items about these data reports (any of), e.g. technicals, company_news.",
    ),
    status: Optional[List[VoteItemStatus]] = Query(
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
    run id.
    """
    items = history.get_vote_items(
        run_id, data_reports=data_report, statuses=status,
        page=page, page_size=page_size,
    )
    if items is None:
        raise HTTPException(status_code=404, detail="run not found")
    return items


@router.get("/runs/{run_id}/transcript", response_model=TranscriptIndex)
def get_tiered_run_transcript(run_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """The run's LLM calls in call order, without their text.

    Each row carries the call's facts (stage, llm, time, tokens, error)
    and the size of its input and output in characters; fetch the text
    of one call with `GET /runs/{run_id}/transcript/{call_number}`. Empty when
    the run made no call or its rows expired (kept 14 days). 404 for an
    unknown run id.
    """
    if not history.run_exists(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return {"items": history.list_transcript(run_id)}


@router.get("/runs/{run_id}/transcript/{call_number}", response_model=TranscriptCall)
def get_tiered_run_transcript_call(run_id: str, call_number: int) -> Dict[str, Any]:
    """One LLM call of a run with its full input and raw output.

    404 when the run is unknown or has no call numbered `call_number`.
    """
    call = history.get_transcript_call(run_id, call_number)
    if call is None:
        raise HTTPException(status_code=404, detail="transcript call not found")
    return call
