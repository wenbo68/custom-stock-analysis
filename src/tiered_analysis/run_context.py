# -*- coding: utf-8 -*-
"""Which model answers and which data keys the report cards may use.

One place that reads the LLM and data-source configuration from the
environment (``.env``), so no stage or provider reads ``os.environ``
for these on its own. Empty values read as None, never as "".
"""
from __future__ import annotations

import os
from typing import Dict, Optional

#: Data-source key name -> the environment variable it comes from.
DATA_KEY_ENV: Dict[str, str] = {
    "finnhub": "FINNHUB_API_KEY",
    "alphavantage": "ALPHAVANTAGE_API_KEY",
    "fred": "FRED_API_KEY",
}


def llm_model() -> Optional[str]:
    """``LITELLM_MODEL`` — the model that does the analysis."""
    model = os.getenv("LITELLM_MODEL") or ""
    return model.strip() or None


def llm_sub_model() -> Optional[str]:
    """The screening model (``NEWS_SCREEN_MODEL``, a cheaper one for the
    news screen's is-this-about-the-company chores), else the main
    model."""
    model = os.getenv("NEWS_SCREEN_MODEL") or os.getenv("LITELLM_MODEL") or ""
    return model.strip() or None


def data_key(name: str) -> Optional[str]:
    """A data-source key from the environment, None when unset."""
    if name not in DATA_KEY_ENV:
        raise KeyError(f"unknown data key {name!r}")
    value = (os.getenv(DATA_KEY_ENV[name]) or "").strip()
    return value or None
