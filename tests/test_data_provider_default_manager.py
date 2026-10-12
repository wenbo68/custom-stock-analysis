# -*- coding: utf-8 -*-
"""One DataFetcherManager for the whole process (2026-10-10).

Why: ``dsa_bars_loader`` built a fresh manager (five fetcher instances)
on every call, and a run loads bars three or four times. The vendor
rate limits live on the fetcher instances and the one-call-at-a-time
locks live on the manager, so four concurrent A-share runs became up to
sixteen independent clients hitting the same vendor. Sharing one
manager puts every run behind the same limits.
"""
from __future__ import annotations

import threading

import pandas as pd

from data_provider import base
from src.tiered_analysis.integration import dsa_bars_loader


class FakeManager:
    def __init__(self):
        self.calls = 0

    def get_daily_data(self, code, days=None, fresh_through=None):
        self.calls += 1
        return pd.DataFrame([]), "fake"


class TestDefaultManager:
    def test_is_built_once_and_shared(self, monkeypatch):
        built = []
        monkeypatch.setattr(base, "DataFetcherManager", lambda: built.append(FakeManager()) or built[-1])
        base.reset_default_manager()

        first = base.default_manager()
        second = base.default_manager()

        assert first is second
        assert len(built) == 1

    def test_concurrent_first_callers_share_one_manager(self, monkeypatch):
        built = []
        monkeypatch.setattr(base, "DataFetcherManager", lambda: built.append(FakeManager()) or built[-1])
        base.reset_default_manager()
        seen = []
        start = threading.Barrier(8)

        def grab():
            start.wait()
            seen.append(base.default_manager())

        threads = [threading.Thread(target=grab) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(built) == 1
        assert all(m is built[0] for m in seen)

    def test_reset_builds_a_new_one(self, monkeypatch):
        built = []
        monkeypatch.setattr(base, "DataFetcherManager", lambda: built.append(FakeManager()) or built[-1])
        base.reset_default_manager()
        first = base.default_manager()

        base.reset_default_manager()
        second = base.default_manager()

        assert first is not second
        assert len(built) == 2


class TestBarsLoader:
    def test_two_loads_use_the_same_manager(self, monkeypatch):
        built = []
        monkeypatch.setattr(base, "DataFetcherManager", lambda: built.append(FakeManager()) or built[-1])
        base.reset_default_manager()

        dsa_bars_loader("AAPL")
        dsa_bars_loader("MSFT")

        assert len(built) == 1
        assert built[0].calls == 2
        base.reset_default_manager()
