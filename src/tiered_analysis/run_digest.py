# -*- coding: utf-8 -*-
"""The run-list facts of one tiered run (2026-09-21).

The history list shows, and the list endpoint filters on, a handful of
facts per run: the tier it was asked for, the sizing inputs it used
(capital, risk fraction, reward-to-risk goal), the max hold in weeks,
and — once finished — its outlook and share count. Those used to be dug
out of the stored JSON on every list call, which meant the browser had
to fetch everything and filter itself. Now they are real columns on
``tiered_runs`` (``DIGEST_COLUMNS``), written at creation from the run's
inputs and again at completion from the report, and this module is the
one place that knows how to compute them from the two JSON blobs — the
history layer uses it for new rows, the storage layer for the one-time
backfill of rows stored before the columns existed.

Pure functions only: no database, no imports from the storage layer.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

#: The columns, in the order the history row shows them.
DIGEST_COLUMNS = (
    "tier", "capital", "risk_fraction", "reward_risk", "hold_weeks",
    "outlook", "shares",
)

#: The creation-time inputs that become columns (same names on both sides).
INPUT_COLUMNS = ("tier", "capital", "risk_fraction", "reward_risk", "hold_weeks")


def digest_from_inputs(inputs: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The column values a run has at creation: its inputs, and no
    outlook or shares yet. Unset inputs stay None."""
    inputs = inputs or {}
    return {key: inputs.get(key) for key in INPUT_COLUMNS}


def digest_from_result(result: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The column values a finished report carries: the outlook, the share
    count (0 when sizing ran but bought nothing, None when the report has
    no sizing block), the depth it actually ran at, the sizing inputs it
    used, and the hold window. Only keys the report actually provides are
    returned, so the caller can lay them over the creation-time values
    without None-overwriting anything."""
    digest: Dict[str, Any] = {}
    if not isinstance(result, Mapping):
        return digest
    if result.get("outlook") is not None:
        digest["outlook"] = result["outlook"]
    sizing = result.get("sizing")
    if isinstance(sizing, Mapping):
        shares = sizing.get("shares")
        digest["shares"] = shares if shares is not None else 0
        inputs = sizing.get("inputs")
        if isinstance(inputs, Mapping):
            for key in ("capital", "risk_fraction", "reward_risk"):
                if inputs.get(key) is not None:
                    digest[key] = inputs[key]
    if isinstance(result.get("depth"), int):
        digest["tier"] = result["depth"]
    if result.get("hold_weeks") is not None:
        digest["hold_weeks"] = result["hold_weeks"]
    return digest


def _load_object(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """A stored JSON text as a dict, None when absent or unreadable."""
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def digest_from_json(
    inputs_json: Optional[str], result_json: Optional[str], status: str,
) -> Dict[str, Any]:
    """Every digest column for a stored row, from its two JSON texts: the
    creation inputs first, then — on a finished run — the report's own
    values on top. Unreadable JSON degrades to None values rather than
    failing. This is what the storage backfill uses for old rows."""
    digest = {key: None for key in DIGEST_COLUMNS}
    digest.update(digest_from_inputs(_load_object(inputs_json)))
    if status == "done":
        digest.update(digest_from_result(_load_object(result_json)))
    return digest
