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
- ``debate``: the deep-analysis record, ``tier2.debate_detail``, as an
  overview — the outlook, the summary outline, the pools and the item
  count, ~11 KB. The vote items themselves (~70 KB, one per piece of
  evidence) are a list, so they are served like one: paged and
  filtered, by ``page_debate_items`` behind ``GET
  /runs/{task_id}/debate/items``.
- ``plan``: the trade-plan receipt — ``levels_detail``, ``sizing`` and
  ``plan_warnings``. (The levels themselves are core: they are the
  headline of the plan and tiny.)

Whatever the sections, the answer carries ``dimension_index``: one light
row per data report (its name, kind, whether it counted, its warnings),
so a caller can see which reports exist and which went wrong without
paying for the reports themselves.

Pure functions: they never mutate the stored dict they are given.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
_DEBATE_ITEMS_KEY = "items"
#: The light per-report rows every answer carries.
DIMENSION_INDEX_KEY = "dimension_index"

#: A vote item's ``final_status`` values: counted toward the score, or
#: excluded (struck for a failed citation, outvoted, or unresolved).
ITEM_STATUSES: Tuple[str, ...] = ("counted", "excluded")
#: Vote items per page when the caller names no size, and the most one
#: page may hold (a whole record is under 200 items).
DEFAULT_ITEM_PAGE_SIZE = 20
MAX_ITEM_PAGE_SIZE = 200


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
        if key == "tier2" and isinstance(value, Mapping):
            out[key] = _tier2_view(value, keep_debate)
            continue
        out[key] = value
    out[DIMENSION_INDEX_KEY] = dimension_index(result)
    return out


def _tier2_view(section: Mapping[str, Any], keep_debate: bool) -> Dict[str, Any]:
    """The tier-2 section without the debate record, or with it cut down
    to the overview."""
    if not keep_debate:
        return {k: v for k, v in section.items() if k != _DEBATE_KEY}
    return {
        k: (debate_overview(v) if k == _DEBATE_KEY else v)
        for k, v in section.items()
    }


def dimension_index(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """One light row per data report: its name, kind, whether it counted
    (numeric with data), and its warnings. Empty for a report without
    dimensions."""
    reports = result.get("dimensions")
    if not isinstance(reports, list):
        return []
    return [
        {
            "dimension": report.get("dimension"),
            "kind": report.get("kind"),
            "is_actionable": bool(report.get("is_actionable")),
            "warnings": list(report.get("warnings") or []),
        }
        for report in reports
        if isinstance(report, Mapping)
    ]


def debate_record(result: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The stored deep-analysis record (``tier2.debate_detail``), or None
    when the report has none (tier 1, or an old shape)."""
    if not isinstance(result, Mapping):
        return None
    tier2 = result.get("tier2")
    if not isinstance(tier2, Mapping):
        return None
    detail = tier2.get(_DEBATE_KEY)
    return detail if isinstance(detail, Mapping) else None


def debate_overview(detail: Any) -> Any:
    """The debate record without its vote items, plus ``item_count`` so
    the reader knows how many there are to page through. Anything that
    is not a record passes through untouched."""
    if not isinstance(detail, Mapping):
        return detail
    items = detail.get(_DEBATE_ITEMS_KEY)
    overview = {k: v for k, v in detail.items() if k != _DEBATE_ITEMS_KEY}
    overview["item_count"] = len(items) if isinstance(items, list) else 0
    return overview


def page_count(total: int, page_size: int) -> int:
    """Pages needed for ``total`` rows; never less than one, so an empty
    list is still "page 1 of 1"."""
    return max(1, -(-int(total) // max(1, int(page_size))))


def page_debate_items(
    detail: Optional[Mapping[str, Any]],
    dimensions: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
    page: int = 1,
    page_size: int = DEFAULT_ITEM_PAGE_SIZE,
) -> Dict[str, Any]:
    """One page of the record's vote items in stored order, narrowed to
    the named dimensions and ``final_status`` values (empty means no
    filter): {items, page, page_size, total, page_count}. A missing
    record reads as an empty list, never an error, so a tier-1 or
    unfinished run simply has no items."""
    items = detail.get(_DEBATE_ITEMS_KEY) if isinstance(detail, Mapping) else None
    rows = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
    wanted_dimensions = _wanted(dimensions)
    if wanted_dimensions:
        rows = [r for r in rows if str(r.get("dimension", "")).lower() in wanted_dimensions]
    wanted_statuses = _wanted(statuses)
    if wanted_statuses:
        rows = [r for r in rows if str(r.get("final_status", "")).lower() in wanted_statuses]
    safe_size = max(1, min(int(page_size), MAX_ITEM_PAGE_SIZE))
    safe_page = max(1, int(page))
    start = (safe_page - 1) * safe_size
    return {
        "items": [dict(r) for r in rows[start:start + safe_size]],
        "page": safe_page,
        "page_size": safe_size,
        "total": len(rows),
        "page_count": page_count(len(rows), safe_size),
    }


def _wanted(names: Optional[Iterable[str]]) -> set:
    if names is None:
        return set()
    return {name.strip().lower() for name in names if name and name.strip()}


def _pick_dimensions(value: Any, names: Optional[Iterable[str]]) -> Any:
    if not isinstance(value, list):
        return value
    wanted = _wanted(names)
    if not wanted:
        return value
    return [
        item for item in value
        if isinstance(item, Mapping)
        and str(item.get("dimension", "")).lower() in wanted
    ]
