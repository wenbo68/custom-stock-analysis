# -*- coding: utf-8 -*-
"""The languages the app speaks, in one place (owner decision 2026-09-26).

Every model-written text a person reads — a chat reply, a run's summary —
is written in the language the user chose for the app. The page sends
that choice as a two-letter code; this module says which codes exist,
how to name them to a model, and whether a piece of text is written in
one of them.

**To add a language, add one ``AppLanguage`` to ``LANGUAGES``.** The
API accepts the new code at once (schemas validate against this table),
the prompts name it, and the check below recognizes it — the detector
knows about a hundred languages by their ISO 639-1 codes. The page's
own words (web/src/i18n) still need their column, written by hand.

The check is plain code, not a model: py3langid compares the text's
letter patterns against fixed per-language profiles, so the same text
always gets the same answer, and it tells apart languages that share an
alphabet (Spanish from English) as well as ones that don't. Before the
check, what reads the same in every language is removed — tickers and
run ids (words with digits), code spans, URLs — and a text with too few
letters left passes, since there is nothing to judge.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from py3langid.langid import MODEL_FILE, LanguageIdentifier


@dataclass(frozen=True)
class AppLanguage:
    #: The two-letter code the page and the API use (ISO 639-1, which the
    #: detector uses too).
    code: str
    #: How the prompt names the language to a model.
    name: str


LANGUAGES: Dict[str, AppLanguage] = {
    "en": AppLanguage("en", "English"),
    "zh": AppLanguage("zh", "Simplified Chinese"),
}

DEFAULT_LANGUAGE = "en"

#: How many times a reply in the wrong language is sent back to be
#: rewritten — the chat bot and every run stage that writes reader-facing
#: text use the same number.
LANGUAGE_RETRY_LIMIT = 2

#: Below this many letters (after the ignored tokens are removed) a text
#: is too short to judge and passes.
MIN_LETTERS_TO_JUDGE = 15

# Left out of the text before detection: code spans, URLs, and words
# holding a digit (tickers like 600519 or 7203.T, run ids, dates, amounts).
_IGNORED = re.compile(
    r"`[^`\n]*`"
    r"|https?://\S+"
    r"|\b[A-Za-z0-9_./-]*\d[A-Za-z0-9_./-]*\b"
)
# A letter in any script (no digits, punctuation or spaces).
_LETTER = re.compile(r"[^\W\d_]")


def is_supported(code: Optional[str]) -> bool:
    return code in LANGUAGES


def language_name(code: str) -> str:
    """How the prompt names the language; the default's name for an unknown code."""
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE]).name


def require_supported(code: str) -> str:
    """The code back, or ValueError naming the offered codes (for the
    API schemas' validators)."""
    if not is_supported(code):
        raise ValueError(f"language must be one of {', '.join(sorted(LANGUAGES))}")
    return code


def reply_language_rule(code: str) -> str:
    """The prompt line that tells a run's model which language to write
    in. Cited values are exempt: the citation checks compare them to the
    report's display strings character for character, so a value stays
    as displayed — including words like "billion" — inside any sentence."""
    name = language_name(code)
    return (
        f"Language: write every sentence a reader sees — claims, reasons, "
        f"score reasons, summaries — in {name}. Values copied from the report "
        f"stay exactly as displayed (numbers, and words like \"billion\" or "
        f"\"above\"), whatever the language; field refs, tickers and JSON keys "
        f"stay as they are."
    )


_detector: Optional[LanguageIdentifier] = None
_detector_guard = threading.Lock()


def _get_detector() -> LanguageIdentifier:
    """The detector, loaded once and limited to the app's languages so
    it never answers with a language the app does not offer."""
    global _detector
    with _detector_guard:
        if _detector is None:
            detector = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
            detector.set_languages(sorted(LANGUAGES))
            _detector = detector
        return _detector


def detect_language(text: Optional[str]) -> Tuple[Optional[str], int]:
    """(code, letters): the app language the text reads as, and how many
    letters were judged. The code is None when there were too few."""
    cleaned = _IGNORED.sub(" ", text or "")
    letters = len(_LETTER.findall(cleaned))
    if letters < MIN_LETTERS_TO_JUDGE:
        return None, letters
    code, _probability = _get_detector().classify(cleaned)
    return str(code), letters


def matches_language(text: Optional[str], code: str) -> bool:
    """True when ``text`` reads as the language ``code`` (or is too short
    to judge, or ``code`` is not one the app offers)."""
    if not is_supported(code):
        return True
    detected, _letters = detect_language(text)
    return detected is None or detected == code


def language_problem(texts: Iterable[Optional[str]], code: str) -> Optional[str]:
    """None when the texts together read as ``code``; otherwise the
    problem, worded for a retry prompt and a warning: "reply not in
    Simplified Chinese"."""
    joined = "\n".join(text for text in texts if text)
    if matches_language(joined, code):
        return None
    return f"reply not in {language_name(code)}"


def correction_message(code: str) -> str:
    """The line a retry adds after a reply in the wrong language."""
    name = language_name(code)
    return (
        f"Your reply is not in {name}. Write the same reply again, in {name}. "
        "Keep tickers, run ids and the app's field names as they are."
    )
