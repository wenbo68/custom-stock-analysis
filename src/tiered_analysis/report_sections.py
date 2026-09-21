# -*- coding: utf-8 -*-
"""Partial reads of a stored report (2026-09-21).

A finished report is 60-150 KB of JSON, and almost all of it sits in two
places: the per-dimension data reports (``dimensions``, ~60 KB) and the
deep-analysis debate record (``tier2.debate_detail``, ~80 KB). Everything
else — the outlook, scores, levels, warnings, usage — is under 5 KB.

``GET /runs/{task_id}`` therefore takes a list of sections and returns
only those, so a caller after the trade plan (or a chatbot after one
data report) never pays for the debate. The sections are:

- ``core``: the light headline facts. Always present, so the answer
  stands on its own whatever else was asked for.
- ``dimensions``: the data reports (optionally narrowed to named ones).
- ``debate``: the deep-analysis record, ``tier2.debate_detail``.
- ``plan``: the trade-plan receipt — ``levels_detail``, ``sizing`` and
  ``plan_warnings``. (The levels themselves are core: they are the
  headline of the plan and tiny.)

Pure functions: they never mutate the stored dict they are given.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

SECTION_CORE = "core"
SECTION_DIMENSIONS = "dimensions"
SECTION_DEBATE = "debate"
SECTION_PLAN = "plan"
ALL_SECTIONS: Tuple[str, ...] = (
    SECTION_CORE, SECTION_DIMENSIONS, SECTION_DEBATE, SECTION_PLAN,
)

#: Top-level report keys owned by a heavy section.
_PLAN_KEYS = ("levels_detail", "sizing", "plan_warnings")
_DEBATE_KEY = "debate_detail"


class UnknownSectionError(ValueError):
    """A requested section name is not one of ``ALL_SECTIONS``."""


def normalize_sections(requested: Optional[Iterable[str]]) -> Tuple[str, ...]:
    """The sections to return, in canonical order: everything when none
    were named, else the named ones plus ``core``. Unknown names raise
    ``UnknownSectionError`` (the endpoint turns that into a 422)."""
    if requested is None:
        return ALL_SECTIONS
    wanted = {name.strip().lower() for name in requested if name and name.strip()}
    if not wanted:
        return ALL_SECTIONS
    unknown = sorted(wanted - set(ALL_SECTIONS))
    if unknown:
        raise UnknownSectionError(
            f"unknown section(s) {', '.join(unknown)}; "
            f"choose from {', '.join(ALL_SECTIONS)}"
        )
    wanted.add(SECTION_CORE)
    return tuple(name for name in ALL_SECTIONS if name in wanted)


def select_sections(
    result: Mapping[str, Any],
    sections: Sequence[str],
    dimensions: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """A copy of ``result`` holding only the given sections. ``dimensions``
    narrows the data reports to the named ones (case-insensitive) when the
    dimensions section is included; an empty match yields an empty list,
    never an error, so a report from before a dimension existed reads as
    "not there" rather than failing."""
    keep_dimensions = SECTION_DIMENSIONS in sections
    keep_debate = SECTION_DEBATE in sections
    keep_plan = SECTION_PLAN in sections

    out: Dict[str, Any] = {}
    for key, value in result.items():
        if key == SECTION_DIMENSIONS:
            if keep_dimensions:
                out[key] = _pick_dimensions(value, dimensions)
            continue
        if key in _PLAN_KEYS:
            if keep_plan:
                out[key] = value
            continue
        if key == "tier2" and isinstance(value, Mapping) and not keep_debate:
            out[key] = {k: v for k, v in value.items() if k != _DEBATE_KEY}
            continue
        out[key] = value
    return out


def _pick_dimensions(value: Any, names: Optional[Iterable[str]]) -> Any:
    if names is None or not isinstance(value, list):
        return value
    wanted = {name.strip().lower() for name in names if name and name.strip()}
    if not wanted:
        return value
    return [
        item for item in value
        if isinstance(item, Mapping)
        and str(item.get("dimension", "")).lower() in wanted
    ]
