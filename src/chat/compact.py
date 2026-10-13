# -*- coding: utf-8 -*-
"""Compaction: summarizing the conversation so far to free up context
(owner request 2026-10-13, after Claude Code's ``/compact`` and its
autocompact).

When a request is about to pass ``context.COMPACT_AT_PERCENT`` of the
max, or the user types ``/compact``, the harness makes one more model
call: the same conversation the next step would have been sent, plus
``SUMMARY_INSTRUCTION`` as the last user line, with the tool menu
offered but tools refused. The reply is stored as a row of its own
role, ``SUMMARY_ROLE`` — a bot step like any other on the page, with
its token line and transcript — carrying under ``compacted`` what it
stands for: the first and last ``seq`` it summarizes, whether it was
automatic or asked for, and the tokens the request held before.

Nothing is deleted. The page shows every row as before; the model's
view of the conversation starts at the newest summary row that
succeeded (``after_last_summary``), which it is shown as a user line
(``summary_for_model``). A summary call that failed is stored with its
error and is no boundary: the model keeps seeing the full history,
the page says the summary failed, and the next turn tries again. One
attempt per turn, never while a held call waits for the user's answer.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .language import language_name

SUMMARY_ROLE = "summary"

#: ``compacted.trigger``: the harness crossed the line, or the user asked.
TRIGGER_AUTO = "auto"
TRIGGER_MANUAL = "manual"

SUMMARY_INSTRUCTION = """\
[The conversation above is being summarized to free up context. Write a \
summary that will stand in for every message above, since they will be \
taken out of view. Respond with text only; do not call any tools.

Cover, in this order, leaving out whatever does not apply:
1. What the user has asked for so far, in order, and what is still open.
2. The tickers and runs discussed: each run's run_id, ticker, tier, date, \
status, outlook, score and action, and the numbers the user cared about.
3. What you concluded or told the user, including anything the user \
corrected, declined, or asked you not to do.
4. The facts from tool results that the current task still needs.
5. What was in progress at the moment of this summary, and the exact next step.

Write in {reply_language}. Keep tickers, run ids and the app's field names \
as they are. Be exact with numbers and brief with everything else.]"""

SUMMARY_PREFACE = (
    "[Summary of the conversation so far. The messages it stands for were "
    "taken out of view to free up context; continue from here.]"
)


def summary_instruction(language: str) -> str:
    """The last user line of the summary request, naming the language."""
    return SUMMARY_INSTRUCTION.format(reply_language=language_name(language))


def summary_for_model(summary: str) -> str:
    """A stored summary as the user line the model is shown."""
    return f"{SUMMARY_PREFACE}\n\n{summary}"


def is_summary(message: Dict[str, Any]) -> bool:
    return message.get("role") == SUMMARY_ROLE


def is_boundary(message: Dict[str, Any]) -> bool:
    """A summary row that succeeded: the model's view starts here."""
    return is_summary(message) and not message.get("error") and bool(message.get("content"))


def after_last_summary(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The rows the model may see: from the newest successful summary
    row, that row included, to the end; all of them when there is none."""
    for index in range(len(messages) - 1, -1, -1):
        if is_boundary(messages[index]):
            return list(messages[index:])
    return list(messages)
