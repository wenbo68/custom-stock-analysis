# -*- coding: utf-8 -*-
"""Run notices (owner request 2026-10-20, after Claude Code's task
notifications): how a conversation hears that a run it started has
ended.

The way in needs nothing new — the bot's start_run tool is the queue.
The way back is this: start_run's result adds a *watch* (src/chat/
store.py, one row per conversation and run), and when the run ends the
run service tells the chat harness, which turns every watch on that
run into a ``notice`` row in its conversation and wakes the bot for one
turn so it reports the end to the user. The bot cannot do this on its
own: a model only runs when it is handed input, so the push has to be
the app's.

A notice row is the app's line, not the user's, but it sets off a turn
the way a user's line does: the page shows it as a user-styled line
with an amber "notice" mark, worded from the row's facts (``run``), and
the model sees it as a user line (``content``) starting with
``NOTICE_PREFIX``. The line carries every fact the bot's report needs —
when the run ended, its outlook and score, the levels, the summary —
because the turn it sets off is one call with every tool refused
(owner decision 2026-10-20, after the bot spent a get_run call on
facts the notice could have carried): the bot reports from the line,
and whatever the user wants next is a normal turn with tools. The
standing instructions (src/chat/prompt.py) tell it what such a line is
and to report, not to act; the model is not asked to retry a failed
run (owner decision 2026-10-20).

A watch ends without a notice when the conversation itself stopped or
deleted the run (the stop_run and delete_run tools, ``Tool.run_watch``):
the user already saw that here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence

from src.tiered_analysis import history
from src.tiered_analysis.report_sections import SECTION_CORE, SECTION_DEEP_ANALYSIS

NOTICE_ROLE = "notice"
NOTICE_PREFIX = "[Run notice]"

#: The statuses a run ends in: a watch waits for any of them.
FINISHED_STATUSES = frozenset({history.STATUS_SUCCEEDED, history.STATUS_FAILED, history.STATUS_STOPPED})

#: Where a report keeps its 0-10 score, in the order the page looks: the
#: preliminary analysis's outlook (tier 1), then the deep analysis's
#: record (tier 2). The top-level ``score`` is null on both today.
_SCORE_PATHS: Sequence[Sequence[str]] = (
    ("preliminary_analysis", "outlook", "final_score"),
    ("deep_analysis", "detail", "outlook", "final_score"),
)

_NOT_GIVEN = "not given"


def _dig(mapping: Any, path: Sequence[str]) -> Any:
    """``mapping[path[0]][path[1]]...`` or None wherever the shape ends."""
    value = mapping
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def score_of(result: Mapping[str, Any]) -> Optional[float]:
    """The report's score where the page reads it: the top-level
    ``score`` when set, else the first ``final_score`` under
    ``_SCORE_PATHS``; None when the report has none."""
    if result.get("score") is not None:
        return result["score"]
    for path in _SCORE_PATHS:
        value = _dig(result, path)
        if value is not None:
            return value
    return None


def run_facts(run_id: str) -> Optional[Dict[str, Any]]:
    """What the notice says about the run, read off its row and its
    report's headline (the core section, plus the deep-analysis
    overview for a tier-2 score): None for an unknown run, or one that
    has not ended. A failed run has no report, so its report facts
    are None; a stopped run's are whatever had finished."""
    run = history.get_run(run_id, sections=(SECTION_CORE, SECTION_DEEP_ANALYSIS))
    if run is None or run.get("status") not in FINISHED_STATUSES:
        return None
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    levels = result.get("levels") if isinstance(result.get("levels"), dict) else {}
    warnings = result.get("warnings")
    return {
        "run_id": run["run_id"],
        "ticker": run["ticker"],
        "tier": run.get("tier"),
        "status": run["status"],
        # The row's last change is the run's end (the page shows it).
        "ended_at": run.get("updated_at"),
        "outlook": run.get("outlook") or result.get("outlook"),
        "score": score_of(result),
        "confidence": result.get("confidence"),
        "action": result.get("action"),
        "levels": {key: levels.get(key) for key in ("entry", "stop_loss", "target")},
        "shares": run.get("shares"),
        "earnings_date": _dig(result, ("earnings", "next_date")),
        "summary": result.get("summary"),
        "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        "error": run.get("error"),
        "stopped_stage": result.get("stopped_stage"),
    }


def _text(value: Any) -> str:
    return _NOT_GIVEN if value is None else str(value)


def _when(ended_at: Optional[str]) -> str:
    """The stored ISO time as the model reads it: minute precision, UTC."""
    if not ended_at:
        return _NOT_GIVEN
    try:
        return datetime.fromisoformat(ended_at).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ended_at


def _succeeded(facts: Dict[str, Any]) -> str:
    levels = facts.get("levels") or {}
    parts = [
        f"It succeeded: outlook {facts.get('outlook') or 'no_outlook'}",
        f"score {_text(facts.get('score'))}",
        f"action {_text(facts.get('action'))}",
        f"confidence {_text(facts.get('confidence'))}",
        f"levels entry {_text(levels.get('entry'))}, stop loss {_text(levels.get('stop_loss'))}, "
        f"target {_text(levels.get('target'))}",
        f"shares {_text(facts.get('shares'))}",
        f"next earnings {_text(facts.get('earnings_date'))}",
        f"{facts.get('warning_count') or 0} warnings on the report",
    ]
    ending = ", ".join(parts) + "."
    summary = facts.get("summary")
    return f"{ending} Summary: {summary}" if summary else ending


def notice_line(facts: Dict[str, Any]) -> str:
    """The notice as the model reads it: the run named the way the bot
    is told to name runs, when it ended, how it ended with the facts
    the report needs, and a word that this reply has no tool."""
    head = (
        f"{NOTICE_PREFIX} The run you started in this conversation has ended: "
        f"{facts['ticker']}, tier {facts['tier']}, run_id {facts['run_id']}, "
        f"finished {_when(facts.get('ended_at'))}."
    )
    status = facts["status"]
    if status == history.STATUS_SUCCEEDED:
        ending = _succeeded(facts)
    elif status == history.STATUS_FAILED:
        ending = f"It failed: {facts.get('error') or 'no error text was recorded'}."
    else:
        stage = facts.get("stopped_stage")
        ending = (
            "It was stopped" + (f" during {stage}" if stage else "")
            + "; the report keeps the sections that had finished."
        )
    tail = "Report this to the user from these facts; no tool can be called in this reply."
    return f"{head} {ending} {tail}"


def notice_message(facts: Dict[str, Any]) -> Dict[str, Any]:
    """The stored row: the model's line under ``content`` and the
    page's facts under ``run``."""
    return {"role": NOTICE_ROLE, "content": notice_line(facts), "run": facts}
