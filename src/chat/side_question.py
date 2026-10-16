# -*- coding: utf-8 -*-
"""Side questions: the page's ``/btw <question>`` (owner request
2026-10-16, after Claude Code's ``/btw``).

A side question is answered from the conversation but never becomes
part of it. The harness stores the question as the user's own line and
the answer as a bot reply, both carrying ``SIDE_QUESTION_KEY`` — so the
page shows the exchange where it happened, and its tokens count toward
what the conversation cost — and every later request leaves the flagged
rows out (``without_side_questions``): the model never sees them again,
``/context`` does not count them, and a summary never covers them.

The call itself (``ChatHarness.side_question``) sees the standing
instructions, the same conversation rows the next step would have been
sent — as text only and with no tool menu, like the summary call
(src/chat/compact.py), since one call with no tools is the point — and
last the question under ``SIDE_QUESTION_INSTRUCTION``, which tells the
model it has no tools and that the exchange will not be kept.

This differs from Claude Code on purpose: there the answer shows in a
panel the user dismisses and nothing is stored (owner decision
2026-10-16: in a web chat the thread is the natural place to read it
back; the flag keeps the model's memory clean).
"""
from __future__ import annotations

from typing import Any, Dict, List

#: The stored key on the question row, the answer row, and a stopped
#: row that ended the side question's turn.
SIDE_QUESTION_KEY = "side_question"

SIDE_QUESTION_INSTRUCTION = """\
[This is a side question from the user, asked with /btw. Answer it directly, \
in one reply, from these instructions and what the conversation above already \
holds. You have no tools in this call: do not say you will look something up, \
check a run, or take any action, and if the answer is not in what you can see, \
say you do not know. Neither this question nor your answer will be part of \
the conversation afterwards, so do not pick up the conversation's open work \
here; just answer the question.]"""


def side_question_line(question: str) -> str:
    """The side question as the request's last user line."""
    return f"{SIDE_QUESTION_INSTRUCTION}\n\n{question}"


def is_side_question(message: Dict[str, Any]) -> bool:
    return bool(message.get(SIDE_QUESTION_KEY))


def without_side_questions(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The rows the conversation is made of, flagged rows left out."""
    return [message for message in messages if not is_side_question(message)]
