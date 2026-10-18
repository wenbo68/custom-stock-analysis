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
removes a run — a queued one is thereby cancelled — POST
/runs/{run_id}/stop stops a running one part-way (2026-10-19; the report
keeps the sections that finished), and GET /status says
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

Starting a run — the model check, the market-open check, the duplicate
refusal (a 409 naming the unfinished run) and the queue — is
``src/tiered_analysis/run_service.py``, shared with the chat's start_run
tool so both clients get the same refusals (2026-10-10); this module
only maps its answers onto HTTP.
"""
from __future__ import annotations

import logging
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
    RunStopRequested,
    Section,
    ServerStatus,
    TickerList,
    TieredAnalyzeRequest,
    TranscriptCall,
    TranscriptIndex,
    VoteItemPage,
    VoteItemStatus,
)
from src.tiered_analysis import history, report_sections, run_service
from src.tiered_analysis.run_service import RunRefused, submit_run

logger = logging.getLogger(__name__)

router = APIRouter()


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
    cancelled. A finished, failed or stopped run is removed from the
    history.

    - 404: unknown run id.
    - 409 `run_in_progress`: the run is executing; stop it first
      (`POST /runs/{run_id}/stop`), then delete the stopped run.
    """
    try:
        deleted = run_service.run_queue.remove(run_id)
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


@router.post("/runs/{run_id}/stop", response_model=RunStopRequested)
def stop_tiered_run(run_id: str) -> Dict[str, Any]:
    """Stop a running run part-way.

    The run's stop flag goes up; the run ends at its next checkpoint —
    the start of its next step, or its next model call — and lands as
    `stopped`. A model call already in flight finishes and is counted,
    so the token totals match the bill. The stored report then holds
    the sections that finished (`GET /runs/{run_id}`: `data_reports`, and
    the analysis when it finished), `stopped_stage` (the step that was
    running when stop was pressed) and `stopped_stage_finished` (whether
    it still finished — a quick card or a one-call analysis may); the
    plan is never there. A step cut short is discarded whole, never
    shown half-built.

    - 404: unknown run id.
    - 409 `run_not_running`: the run is not executing (the body says its
      `status`). A queued run is cancelled with `DELETE /runs/{run_id}`.
    """
    run = history.get_run_summary(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not run_service.run_queue.stop(run_id):
        raise HTTPException(status_code=409, detail={
            "code": "run_not_running", "run_id": run_id, "status": run["status"],
        })
    logger.info("tiered run %s (%s) asked to stop", run_id, run["ticker"])
    return {"run_id": run_id, "ticker": run["ticker"]}


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
