# -*- coding: utf-8 -*-
"""The chat bot's tool menu: one tool per thing the app's API can do.
Every parameter and result key is the analysis page's own word for the
thing (owner request 2026-09-24).

Each tool names a typed parameter form (a pydantic model, whose JSON
schema is what the model reads as documentation), a ``run`` that calls
the same Python function the HTTP route calls, and — for the tools that
change something or read something large — a ``confirm`` that gathers
the facts the chat page needs to ask the user first (what will be
started or deleted; how many characters and roughly how many tokens a
read would put through the user's model). A ``confirm`` that finds the
action impossible returns an ``error`` result instead, and the harness
hands that straight to the model with no question asked.

Every tool answers with a JSON-able dict. A refusal or a miss is a
normal answer with an ``error`` key (``not_found``, ``market_open``,
``duplicate_run``, ...), never an exception, so the model can explain
it to the user.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel, Field, ValidationError

from src.tiered_analysis import history, run_service
from src.tiered_analysis.report_sections import normalize_sections
from src.tiered_analysis.run_request import TieredAnalyzeRequest
from src.tiered_analysis.run_service import RunRefused, effective_inputs, submit_run
from src.tiered_analysis.server_status import server_status
from src.tiered_analysis.settings import DEFAULT_MAX_HOLD_WEEKS, DEFAULT_TIER

#: The most rows a listing tool hands the model at once: enough for an
#: answer, far under the routes' own caps (the page can ask for more).
MAX_LIST_PAGE = 50
DEFAULT_LIST_PAGE = 10
#: Characters per token, the usual rough figure, for the cost estimate
#: shown before a large read.
CHARS_PER_TOKEN = 4

VoteItemStatus = Literal["counted", "excluded"]
RunStatus = Literal["queued", "running", "done", "failed"]
OutlookFilter = Literal["bullish", "neutral", "bearish", "no_outlook"]
ExtraSection = Literal["plan", "deep_analysis"]
DATA_REPORTS = (
    "technicals", "fundamentals", "positioning",
    "macro_economy", "company_news", "world_news",
)


def not_found(what: str, run_id: str) -> Dict[str, Any]:
    return {"error": "not_found", "message": f"no {what} for run_id {run_id}"}


def token_estimate(chars: int) -> int:
    return -(-int(chars) // CHARS_PER_TOKEN)


def size_facts(chars: int) -> Dict[str, Any]:
    """What a large read costs: its size and a rough token count."""
    return {"chars": int(chars), "tokens_estimate": token_estimate(chars)}


# ---------------------------------------------------------------------------
# Parameter forms
# ---------------------------------------------------------------------------


class NoParams(BaseModel):
    pass


class ListRunsParams(BaseModel):
    ticker: List[str] = Field(default_factory=list, description="Keep only these tickers (any of; case-insensitive).")
    status: List[RunStatus] = Field(default_factory=list, description="Keep only these statuses (any of).")
    outlook: List[OutlookFilter] = Field(default_factory=list, description="Keep only these outlooks; 'no_outlook' = runs with no outlook (unfinished, failed, or the analysis produced none).")
    tier: List[int] = Field(default_factory=list, description="1 = preliminary analysis, 2 = deep analysis.")
    max_hold_weeks: List[int] = Field(default_factory=list, description="Max hold time in weeks, 1-4.")
    created_after: Optional[str] = Field(default=None, description="ISO 8601 date-time, inclusive; UTC when no offset.")
    created_before: Optional[str] = Field(default=None, description="ISO 8601 date-time, exclusive; UTC when no offset.")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_LIST_PAGE, ge=1, le=MAX_LIST_PAGE)


class RunParams(BaseModel):
    run_id: str = Field(description="The run's id (run_id).")


class GetRunParams(RunParams):
    sections: List[ExtraSection] = Field(
        default_factory=list,
        description=(
            "Extra report sections beyond the core facts: 'plan' (the "
            "trade-plan receipt: how the levels and share count were "
            "derived, plan warnings) and 'deep_analysis' (a tier-2 run's "
            "overview: outlook, summary outline, score pools, vote item "
            "count). The data reports are read with get_data_report; the "
            "vote items with list_vote_items."
        ),
    )


class DataReportParams(RunParams):
    data_report: str = Field(description="One of: " + ", ".join(DATA_REPORTS) + ".")


class VoteItemsParams(RunParams):
    data_report: List[str] = Field(default_factory=list, description="Keep items about these data reports (any of).")
    status: List[VoteItemStatus] = Field(default_factory=list, description="'counted' = counted toward the score; 'excluded' = struck out.")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_LIST_PAGE, ge=1, le=MAX_LIST_PAGE)


class TranscriptCallParams(RunParams):
    call_number: int = Field(ge=1, description="The LLM call's number within the run, from get_transcript.")


class StartRunParams(BaseModel):
    # The web form's fields, in its order and words, so what the chat
    # shows as a tool's input matches what the user sees on the analysis
    # page (owner request 2026-09-24). Same shape as the HTTP request.
    ticker: str = Field(description="Ticker: US like AAPL; A-share 6 digits like 600519; HK like hk00700; JP/KR/TW Yahoo-style like 7203.T, 005930.KS, 2330.TW.")
    capital: Optional[float] = Field(default=None, gt=0, description="Trading capital in the ticker's currency; omit for the default.")
    risk_pct: Optional[float] = Field(default=None, gt=0, lt=100, description="Percent of capital to risk on this trade (1 = 1%); omit for the default.")
    reward_ratio: Optional[float] = Field(default=None, gt=1, le=10, description="Target reward-to-risk ratio (target = entry + ratio × risk); omit for the default.")
    max_hold_weeks: int = Field(default=DEFAULT_MAX_HOLD_WEEKS, ge=1, le=4, description="Max hold time in weeks the AI judges against.")
    tier: int = Field(default=DEFAULT_TIER, ge=1, le=2, description="1 = preliminary analysis, 2 = deep analysis (the vote; slower, costs more).")
    run_anyway: bool = Field(default=False, description="Only when the user explicitly agreed: start during the trading day, analyzing the previous completed session.")


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

Runner = Callable[[Any], Dict[str, Any]]
Confirmer = Callable[[Any], Dict[str, Any]]
Resolver = Callable[[Any], Dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: Type[BaseModel]
    run: Runner
    #: Set on the tools that must wait for the user's yes: returns the
    #: facts the page words the question with, or an ``error`` result.
    confirm: Optional[Confirmer] = None
    #: The inputs as the tool will actually use them, every default
    #: filled in, for the page's input fold (owner request 2026-09-24:
    #: a user should see all of a call's inputs, not only the ones the
    #: model chose to send). Unset, the parsed parameters themselves;
    #: start_run resolves the server's sizing defaults too.
    resolve: Optional[Resolver] = None

    @property
    def needs_confirmation(self) -> bool:
        return self.confirm is not None

    def inputs(self, params: BaseModel) -> Dict[str, Any]:
        """The call's inputs with every default filled in."""
        if self.resolve is not None:
            return self.resolve(params)
        return params.model_dump(mode="json")

    def spec(self) -> Dict[str, Any]:
        """The tool as the model sees it (OpenAI function-calling shape)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": clean_schema(self.params.model_json_schema()),
            },
        }

    def parse(self, raw: Any) -> Tuple[Optional[BaseModel], Optional[Dict[str, Any]]]:
        """The validated parameters, or an ``error`` result naming what
        was wrong with the model's arguments."""
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError as exc:
            return None, {"error": "invalid_arguments", "message": f"arguments are not JSON: {exc}"}
        try:
            return self.params.model_validate(data if isinstance(data, dict) else {}), None
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg')}" for e in exc.errors()
            )
            return None, {"error": "invalid_arguments", "message": problems}


#: Schema keywords some providers reject; pydantic still enforces them
#: when the arguments are parsed, so dropping them here loses nothing.
_DROPPED_SCHEMA_KEYS = ("title", "exclusiveMinimum", "exclusiveMaximum")


def clean_schema(schema: Any) -> Any:
    """A pydantic JSON schema cut down to what every provider accepts:
    no titles or open-interval bounds, and an optional field described
    by its real type rather than an any-of with null (the model simply
    leaves it out)."""
    if isinstance(schema, dict):
        options = schema.get("anyOf")
        if isinstance(options, list):
            real = [o for o in options if not (isinstance(o, dict) and o.get("type") == "null")]
            if len(real) == 1 and isinstance(real[0], dict):
                merged = {k: v for k, v in schema.items() if k != "anyOf"}
                merged.update(real[0])
                return clean_schema(merged)
        return {
            key: clean_schema(value)
            for key, value in schema.items()
            if key not in _DROPPED_SCHEMA_KEYS and not (key == "default" and value is None)
        }
    if isinstance(schema, list):
        return [clean_schema(item) for item in schema]
    return schema


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _parse_when(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run_server_status(_: NoParams) -> Dict[str, Any]:
    return server_status()


def run_list_runs(p: ListRunsParams) -> Dict[str, Any]:
    try:
        after, before = _parse_when(p.created_after), _parse_when(p.created_before)
    except ValueError as exc:
        return {"error": "invalid_arguments", "message": f"bad date: {exc}"}
    filters = history.RunFilters(
        tickers=tuple(p.ticker), statuses=tuple(p.status), outlooks=tuple(p.outlook),
        tiers=tuple(p.tier), max_hold_weeks=tuple(p.max_hold_weeks),
        created_after=after, created_before=before,
    )
    return history.list_runs(filters, page=p.page, page_size=p.page_size)


def run_list_tickers(_: NoParams) -> Dict[str, Any]:
    return {"items": history.list_tickers()}


def run_get_run(p: GetRunParams) -> Dict[str, Any]:
    run = history.get_run(p.run_id, sections=normalize_sections(["core", *p.sections]))
    return run if run is not None else not_found("run", p.run_id)


def _data_report(p: DataReportParams) -> Optional[Dict[str, Any]]:
    """The one data report, or None when the run or the report is absent."""
    run = history.get_run(p.run_id, sections=("core", "data_reports"), data_reports=[p.data_report])
    if run is None or not isinstance(run.get("result"), dict):
        return None
    reports = run["result"].get("data_reports") or []
    return reports[0] if reports else None


def confirm_data_report(p: DataReportParams) -> Dict[str, Any]:
    if not history.run_exists(p.run_id):
        return not_found("run", p.run_id)
    report = _data_report(p)
    if report is None:
        return {"error": "not_found", "message": f"run {p.run_id} has no '{p.data_report}' data report (unfinished, failed, or no such report)"}
    return size_facts(len(json.dumps(report, ensure_ascii=False)))


def run_data_report(p: DataReportParams) -> Dict[str, Any]:
    report = _data_report(p)
    if report is None:
        return not_found(f"'{p.data_report}' report", p.run_id)
    return {"run_id": p.run_id, "report": report}


def run_vote_items(p: VoteItemsParams) -> Dict[str, Any]:
    page = history.get_vote_items(
        p.run_id, data_reports=p.data_report, statuses=p.status,
        page=p.page, page_size=p.page_size,
    )
    return page if page is not None else not_found("run", p.run_id)


def run_transcript(p: RunParams) -> Dict[str, Any]:
    if not history.run_exists(p.run_id):
        return not_found("run", p.run_id)
    return {"run_id": p.run_id, "items": history.list_transcript(p.run_id)}


def confirm_transcript_call(p: TranscriptCallParams) -> Dict[str, Any]:
    call = history.get_transcript_call(p.run_id, p.call_number)
    if call is None:
        return not_found(f"LLM call {p.call_number}", p.run_id)
    return size_facts(len(call.get("input") or "") + len(call.get("output") or ""))


def run_transcript_call(p: TranscriptCallParams) -> Dict[str, Any]:
    call = history.get_transcript_call(p.run_id, p.call_number)
    return call if call is not None else not_found(f"LLM call {p.call_number}", p.run_id)


def _analyze_request(p: StartRunParams):
    from src.chat.language import turn_language

    # The tool's parameters are the HTTP request's fields, name for name;
    # the language is the user's choice for the app, not the model's, so
    # it comes from the turn.
    return TieredAnalyzeRequest(**p.model_dump(), language=turn_language())


def resolve_start_run(p: StartRunParams) -> Dict[str, Any]:
    """The settings the run would use — the server's defaults filled in
    for whatever the model left out, in the form's order — so the user
    sees exactly what they are paying for. Both the confirmation facts
    and the input fold."""
    return effective_inputs(_analyze_request(p))


confirm_start_run = resolve_start_run


def run_start_run(p: StartRunParams) -> Dict[str, Any]:
    try:
        return submit_run(_analyze_request(p))
    except RunRefused as exc:
        detail = dict(exc.detail)
        code = detail.pop("code", None) or detail.pop("error", None) or "refused"
        return {"error": code, **detail}


def confirm_delete_run(p: RunParams) -> Dict[str, Any]:
    run = history.get_run_summary(p.run_id)
    if run is None:
        return not_found("run", p.run_id)
    if run["status"] == history.STATUS_RUNNING:
        return {"error": "run_in_progress", "run_id": p.run_id,
                "message": "the run is executing and cannot be stopped; wait for it to finish, then delete it"}
    return {"run": run}


def run_delete_run(p: RunParams) -> Dict[str, Any]:
    try:
        deleted = run_service.run_queue.remove(p.run_id)
    except history.RunInProgressError:
        return {"error": "run_in_progress", "run_id": p.run_id,
                "message": "the run is executing and cannot be stopped"}
    if deleted is None:
        return not_found("run", p.run_id)
    return {"deleted": True, "run_id": deleted["run_id"],
            "ticker": deleted["ticker"], "status": deleted["status"]}


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

TOOLS: Tuple[Tool, ...] = (
    Tool(
        name="get_server_status",
        description=(
            "What the server can do right now: the configured model (never the key), "
            "which data sources are set, run slots and how many runs are running or "
            "queued, the run defaults, and each market's clock — whether a run would "
            "be refused now and when runs are accepted again."
        ),
        params=NoParams, run=run_server_status,
    ),
    Tool(
        name="list_runs",
        description=(
            "One page of the run history, newest first, filtered in the database. "
            "Each row: run_id, ticker, status, error, times, capital, risk_pct, "
            "reward_ratio, max_hold_weeks, tier, outlook (once done) and share count. "
            "Filters combine with AND."
        ),
        params=ListRunsParams, run=run_list_runs,
    ),
    Tool(
        name="list_tickers",
        description="Every ticker that has ever been run, A-Z.",
        params=NoParams, run=run_list_tickers,
    ),
    Tool(
        name="get_run",
        description=(
            "One run's core facts and, once done, its report's headline: outlook, "
            "score, confidence, levels (entry, stop loss, target), share count, summary, "
            "warnings, earnings date, per-stage LLM usage, and data_report_index — one "
            "light row per data report (name, whether it counted, its warnings). "
            "'result' is null while the run is queued or running and after a failure."
        ),
        params=GetRunParams, run=run_get_run,
    ),
    Tool(
        name="get_data_report",
        description=(
            "One data report of a finished run in full (its numbers, formulas, "
            "summary, citations, warnings). Large (4-25 KB); the user is asked "
            "before it is read. Use get_run's data_report_index first to see which "
            "reports exist."
        ),
        params=DataReportParams, run=run_data_report, confirm=confirm_data_report,
    ),
    Tool(
        name="list_vote_items",
        description=(
            "One page of a deep-analysis (tier 2) run's vote items: each is one piece "
            "of evidence with the claim, its data report and field, the item_outlook it "
            "argues for, the listers' and checkers' votes with their 1-5 scores, and "
            "final_status (counted or excluded). Empty for a tier-1 run."
        ),
        params=VoteItemsParams, run=run_vote_items,
    ),
    Tool(
        name="get_transcript",
        description=(
            "The run's LLM calls in order without their text: call_number, stage, llm, "
            "time, token counts, error, and the size of each input and output."
        ),
        params=RunParams, run=run_transcript,
    ),
    Tool(
        name="get_transcript_call",
        description=(
            "One LLM call of a run with its full input (the prompt) and raw output. "
            "Can be very large (up to ~80 KB); the user is asked before it is read."
        ),
        params=TranscriptCallParams, run=run_transcript_call, confirm=confirm_transcript_call,
    ),
    Tool(
        name="start_run",
        description=(
            "Start an analysis run (the user is asked to confirm first). Returns the "
            "run_id and whether it started at once or is queued. Refusals come back "
            "as errors: llm_not_configured, market_open (the market is inside its "
            "trading day — do NOT retry with run_anyway unless the user says so), "
            "duplicate_run (an unfinished run has the same ticker and inputs; its "
            "run_id is given). A run takes minutes; check get_run later."
        ),
        params=StartRunParams, run=run_start_run, confirm=confirm_start_run, resolve=resolve_start_run,
    ),
    Tool(
        name="delete_run",
        description=(
            "Delete a run and its transcript (the user is asked to confirm first). "
            "A queued run is thereby cancelled. A running run cannot be stopped."
        ),
        params=RunParams, run=run_delete_run, confirm=confirm_delete_run,
    ),
)


class ToolCatalog:
    """The tools by name, and their specs for the model."""

    def __init__(self, tools: Tuple[Tool, ...] = TOOLS) -> None:
        self._tools: Dict[str, Tool] = {tool.name: tool for tool in tools}

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return list(self._tools)

    def specs(self) -> List[Dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]
