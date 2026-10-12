# -*- coding: utf-8 -*-
"""The run service lives in ``src``, below the HTTP layer (2026-10-10).

Why: the chat's tools (``src.chat.tools``) used to import the run
queue, ``submit_run`` and the request shape from the tiered route
module in ``api``. Nothing in ``api`` imported ``src.chat`` back, so
there was no cycle yet, but one such import added to the route would
have produced a cycle that only fails at request time. Now both the
route and the chat import the same ``src.tiered_analysis.run_service``
and ``src.tiered_analysis.run_request``, and no module under ``src``
imports from ``api``.
"""
from __future__ import annotations

import re
from pathlib import Path

from api.v1.endpoints import tiered, tiered_schemas
from src.chat import tools
from src.tiered_analysis import run_request, run_service

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


class TestLayering:
    def test_nothing_under_src_imports_from_api(self):
        offenders = []
        for path in SRC_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*(?:from api\b|import api\b)", text, re.M):
                offenders.append(str(path.relative_to(SRC_ROOT.parent)))
        assert offenders == []

    def test_the_route_and_the_chat_share_one_queue(self):
        assert tiered.run_service.run_queue is run_service.run_queue
        assert tools.run_service.run_queue is run_service.run_queue

    def test_the_route_and_the_chat_share_one_request_shape(self):
        assert tiered.TieredAnalyzeRequest is run_request.TieredAnalyzeRequest
        assert tiered_schemas.TieredAnalyzeRequest is run_request.TieredAnalyzeRequest
        assert tools.TieredAnalyzeRequest is run_request.TieredAnalyzeRequest
