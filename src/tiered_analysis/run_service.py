# -*- coding: utf-8 -*-
"""Starting and executing runs: the one path every client goes through.

Two clients start runs — the web page over HTTP (api/v1/endpoints/
tiered.py) and the chat's start_run tool in-process (src/chat/tools.py)
— and both must get the same model check, the same market-open check,
the same duplicate refusal and the same queue. This module holds that
path, plus the process's one run queue and the runner that turns a
finished analysis into the stored report, so neither client depends on
the other's module. It sits in ``src`` because the chat lives there and
``src`` must not import from ``api`` (layering, 2026-10-10): before this
the chat imported the queue from the HTTP route module, and one import
the other way would have made a cycle that only fails at request time.

Run queue (2026-09-15): a new run is stored ``queued`` and the global
queue (run_queue.py) starts it when one of the ``MAX_CONCURRENT_RUNS``
slots is free. An exact duplicate of an unfinished run (same ticker and
inputs) is refused naming that run, so a double click never pays twice.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, Optional

from src.languages import DEFAULT_LANGUAGE
from src.tiered_analysis import history
from src.tiered_analysis.llm_support import LlmTranscript
from src.tiered_analysis.run_context import llm_model
from src.tiered_analysis.run_queue import QueuedRun, RunQueue
from src.tiered_analysis.run_request import TieredAnalyzeRequest
from src.tiered_analysis.settings import SizingSettings, merge_overrides

logger = logging.getLogger(__name__)


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
        history.mark_succeeded(run.run_id, _serialize_outcome(outcome))
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
    # Looked up at call time, not import time, so tests can swap the
    # check on its own module (the libraries it needs preload at
    # startup, so there is no load-time reason any more).
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
