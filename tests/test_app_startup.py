# -*- coding: utf-8 -*-
"""Startup loads ``.env`` and the heavy libraries once, on the main
thread, before the app serves a request (2026-10-10).

Why: litellm hooks itself into uvicorn's access-log logger the moment
it is imported, and that hook imports more of litellm on every log
line. When the first ``import litellm`` happened inside a chat turn's
worker thread, the event loop logged a polling request at the same
moment, the two threads waited on each other's import locks, Python
aborted the import, and the half-installed hook then crashed every log
line with ``KeyError: 'litellm'``. The price-data stack (pandas, the
exchange calendars, the vendor libraries) had the same shape: first
imported lazily from request handlers and run threads, several of which
start at once when the queue resumes at startup. Loading everything at
startup, alone on the main thread, leaves nothing to race.

``.env`` used to load only because ``server.py`` imported ``src.config``
first; ``api.app`` itself never did, so ``uvicorn api.app:app`` and the
tests silently ran without the file's settings.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app as app_module


class TestDotenv:
    def test_app_module_loads_env_before_any_other_project_import(self):
        # ``src.config`` runs load_dotenv() on import, so it must come
        # before any import that could read the environment.
        source = Path(app_module.__file__).read_text(encoding="utf-8")
        project_imports = re.findall(r"^(?:from|import) ((?:src|api|data_provider)[\w.]*)", source, re.M)
        assert project_imports[0] == "src.config"


class TestPreloadLibraries:
    def test_imports_the_model_client_then_the_price_data_stack(self, monkeypatch):
        asked = []
        monkeypatch.setattr(app_module, "import_module", lambda name: asked.append(name))

        app_module.preload_libraries()

        assert asked == [
            "litellm",
            "src.core.trading_calendar",
            "data_provider",
            "yfinance",
            "akshare",
            "efinance",
        ]

    def test_a_broken_install_fails_startup_and_names_the_library(self, monkeypatch):
        def boom(name):
            if name == "akshare":
                raise ImportError("no module named akshare")

        monkeypatch.setattr(app_module, "import_module", boom)

        with pytest.raises(RuntimeError, match="akshare"):
            app_module.preload_libraries()


class TestStartup:
    def test_the_libraries_are_loaded_before_housekeeping_and_the_first_request(self, monkeypatch):
        order = []
        monkeypatch.setattr(app_module, "preload_libraries", lambda: order.append("libraries"))
        monkeypatch.setattr(app_module, "startup_housekeeping", lambda: order.append("housekeeping"))

        with TestClient(app_module.create_app()) as client:
            order.append("request")
            assert client.get("/api/health").status_code == 200

        assert order[:2] == ["libraries", "housekeeping"]
        assert order[-1] == "request"
