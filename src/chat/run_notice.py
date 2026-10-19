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

A notice row is the app's line, not the user's: the page shows it as a
quiet line naming the run and how it ended (``run``, the page's facts),
and the model sees it as a user line (``content``) starting with
``NOTICE_PREFIX`` — the standing instructions (src/chat/prompt.py) tell
it what such a line is and to report, not to act. The model is not
asked to retry a failed run (owner decision 2026-10-20): it says what
happened, and the user asks for whatever comes next.

A watch ends without a notice when the conversation itself stopped or
deleted the run (the stop_run and delete_run tools, ``Tool.run_watch``):
the user already saw that here.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.tiered_analysis import history
from src.tiered_analysis.report_sections import SECTION_CORE

NOTICE_ROLE = "notice"
NOTICE_PREFIX = "[Run notice]"

#: The statuses a run ends in: a watch waits for any of them.
FINISHED_STATUSES = frozenset({history.STATUS_SUCCEEDED, history.STATUS_FAILED, history.STATUS_STOPPED})


def run_facts(run_id: str) -> Optional[Dict[str, Any]]:
    """What the notice says about the run, read off its row and its
    report's core section: None for an unknown run, or one that has
    not ended."""
    run = history.get_run(run_id, sections=(SECTION_CORE,))
    if run is None or run.get("status") not in FINISHED_STATUSES:
        return None
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    return {
        "run_id": run["run_id"],
        "ticker": run["ticker"],
        "tier": run.get("tier"),
        "status": run["status"],
        "outlook": run.get("outlook") or result.get("outlook"),
        "score": result.get("score"),
        "error": run.get("error"),
        "stopped_stage": result.get("stopped_stage"),
    }


def notice_line(facts: Dict[str, Any]) -> str:
    """The notice as the model reads it: the run named the way the
    bot is told to name runs, then how it ended."""
    head = (
        f"{NOTICE_PREFIX} The run you started in this conversation has ended: "
        f"{facts['ticker']}, tier {facts['tier']}, run_id {facts['run_id']}."
    )
    status = facts["status"]
    if status == history.STATUS_SUCCEEDED:
        outlook = facts.get("outlook") or "no_outlook"
        score = facts.get("score")
        ending = f"It succeeded: outlook {outlook}" + (f", score {score}" if score is not None else "") + "."
    elif status == history.STATUS_FAILED:
        ending = f"It failed: {facts.get('error') or 'no error text was recorded'}."
    else:
        stage = facts.get("stopped_stage")
        ending = (
            "It was stopped" + (f" during {stage}" if stage else "")
            + "; the report keeps the sections that had finished."
        )
    return f"{head} {ending}"


def notice_message(facts: Dict[str, Any]) -> Dict[str, Any]:
    """The stored row: the model's line under ``content`` and the
    page's facts under ``run``."""
    return {"role": NOTICE_ROLE, "content": notice_line(facts), "run": facts}
