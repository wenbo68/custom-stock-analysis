# -*- coding: utf-8 -*-
"""The chat bot's side of the app's languages (src/languages.py): the
language of the turn in progress, and the shared names re-exported for
the harness and the API schemas.

The page sends the language the user chose for the app with every turn
(owner decision 2026-09-25): the bot answers in that language whatever
language the user types in. A model follows that instruction almost
always, but not always, so after each final reply the loop checks the
language the text is written in and, when it is the wrong one, shows
the model the problem and asks again (``LANGUAGE_RETRY_LIMIT`` times) —
the same show-the-problem retry the analysis uses for a bad JSON reply.

A run the bot starts is written in the same language: the harness holds
the turn's language in a context variable while the turn runs, and the
start_run tool reads it from there (``turn_language``), since it is the
user's choice, not the model's.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from src.languages import (  # noqa: F401 — re-exported
    DEFAULT_LANGUAGE,
    LANGUAGE_RETRY_LIMIT,
    LANGUAGES,
    correction_message,
    is_supported,
    language_name,
    matches_language,
)

_turn_language: ContextVar[str] = ContextVar("chat_turn_language", default=DEFAULT_LANGUAGE)


def turn_language() -> str:
    """The language of the chat turn running on this thread (the app's
    default outside a turn)."""
    return _turn_language.get()


@contextmanager
def using_turn_language(code: str) -> Iterator[None]:
    token = _turn_language.set(code)
    try:
        yield
    finally:
        _turn_language.reset(token)
