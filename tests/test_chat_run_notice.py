# -*- coding: utf-8 -*-
"""Offline tests for run notices (src/chat/run_notice.py and the
harness's watch and delivery path, 2026-10-20): a run the bot starts
is watched, and when it ends the conversation gets a notice row and
one turn of the bot's own, at a moment the conversation is idle."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.chat import store
from src.chat import tools as tools_module
from src.chat.harness import ChatHarness, model_view, starts_turn, trim_history
from src.chat.model import ModelReply
from src.chat.run_notice import NOTICE_PREFIX, NOTICE_ROLE, notice_line, run_facts
from src.tiered_analysis import history, run_service

COLD_TURN_WAIT = 30


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "chat_notice.db")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


@pytest.fixture(autouse=True)
def fallback_window(monkeypatch):
    from src.chat import context

    context.litellm_limits.cache_clear()
    monkeypatch.setattr(context, "litellm_limits", lambda llm: None)


class ScriptedModel:
    def __init__(self, replies: List[ModelReply]) -> None:
        self.replies = list(replies)
        self.requests: List[Dict[str, Any]] = []
        self.release = threading.Event()
        self.release.set()
        self.asked = threading.Event()

    def complete(self, messages, tools, tool_choice="auto"):
        self.asked.set()
        self.release.wait(timeout=5)
        self.requests.append({"messages": messages, "tools": tools})
        if not self.replies:
            raise AssertionError("model asked more often than scripted")
        return self.replies.pop(0)


def text(content):
    return ModelReply(content=content, input_tokens=20, output_tokens=4, llm="fake")


def call(name, args, call_id="c1"):
    return ModelReply(content=None, tool_calls=[{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }])


def roles(conversation_id):
    return [m["role"] for m in store.messages(conversation_id)]


def wait_until(condition, timeout=COLD_TURN_WAIT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def finished_run(run_id="r1", ticker="AAPL", status=history.STATUS_SUCCEEDED, **report):
    history.create_run(run_id, ticker, inputs={"tier": 1}, status=history.STATUS_QUEUED)
    if status == history.STATUS_SUCCEEDED:
        history.mark_succeeded(run_id, {"outlook": "bullish", "score": 7.2, **report})
    elif status == history.STATUS_FAILED:
        history.mark_failed(run_id, report.get("error", "boom"))
    else:
        history.mark_stopped(run_id, {"stopped_stage": report.get("stopped_stage", "technicals")})
    return run_id


class TestNoticeText:
    def test_a_succeeded_run_names_its_outlook_and_score(self, isolated_db):
        finished_run()
        facts = run_facts("r1")
        assert facts == {
            "run_id": "r1", "ticker": "AAPL", "tier": 1, "status": "succeeded",
            "outlook": "bullish", "score": 7.2, "error": None, "stopped_stage": None,
        }
        line = notice_line(facts)
        assert line.startswith(NOTICE_PREFIX)
        assert "AAPL, tier 1, run_id r1" in line
        assert "succeeded: outlook bullish, score 7.2" in line

    def test_a_failed_run_carries_its_error(self, isolated_db):
        finished_run(status=history.STATUS_FAILED, error="provider down")
        line = notice_line(run_facts("r1"))
        assert "It failed: provider down." in line

    def test_a_stopped_run_names_the_step(self, isolated_db):
        finished_run(status=history.STATUS_STOPPED, stopped_stage="fundamentals")
        line = notice_line(run_facts("r1"))
        assert "stopped during fundamentals" in line and "sections that had finished" in line

    def test_an_unfinished_or_unknown_run_has_no_facts(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status=history.STATUS_QUEUED)
        assert run_facts("q1") is None
        assert run_facts("ghost") is None

    def test_the_model_sees_a_notice_as_a_user_line_that_starts_a_turn(self):
        row = {"role": NOTICE_ROLE, "content": f"{NOTICE_PREFIX} ...", "run": {"run_id": "r1"}, "seq": 3}
        assert model_view(row) == {"role": "user", "content": f"{NOTICE_PREFIX} ..."}
        assert starts_turn(row)
        rows = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                row, {"role": "assistant", "content": "c"}]
        assert trim_history(rows, limit=2) == rows[2:]


class TestWatching:
    def test_a_started_run_is_watched_in_the_turns_language(self, isolated_db, monkeypatch):
        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        model = ScriptedModel([call("start_run", {"ticker": "AAPL"}), text("已开始。")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "run AAPL", language="zh")
        assert store.get_pending(conversation_id)["calls"][0]["name"] == "start_run"

        accepted = {"run_id": "r1", "ticker": "AAPL", "tier": 1, "status": "queued"}
        with patch.object(tools_module, "submit_run", lambda request: accepted):
            bot.confirm(conversation_id, True, language="zh")
        watches = store.watches(conversation_id)
        assert [(w["run_id"], w["language"]) for w in watches] == [("r1", "zh")]

    def test_a_refused_start_is_not_watched(self, isolated_db, monkeypatch):
        monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
        model = ScriptedModel([call("start_run", {"ticker": "AAPL"}), text("Refused.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "run AAPL")

        def refuse(request):
            raise run_service.RunRefused(409, {"code": "duplicate_run", "run_id": "other", "status": "running"})

        with patch.object(tools_module, "submit_run", refuse):
            bot.confirm(conversation_id, True)
        assert store.watches(conversation_id) == []

    def test_stopping_the_run_here_ends_the_watch(self, isolated_db):
        history.create_run("r1", "AAPL", inputs={"tier": 1}, status=history.STATUS_RUNNING)
        model = ScriptedModel([call("stop_run", {"run_id": "r1"}), text("Stopping.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        bot.send(conversation_id, "stop it")
        with patch.object(run_service.run_queue, "stop", lambda run_id: True):
            bot.confirm(conversation_id, True)
        assert store.watches(conversation_id) == []

    def test_deleting_the_run_here_ends_the_watch(self, isolated_db):
        history.create_run("r1", "AAPL", inputs={"tier": 1}, status=history.STATUS_QUEUED)
        model = ScriptedModel([call("delete_run", {"run_id": "r1"}), text("Deleted.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        bot.send(conversation_id, "delete it")
        bot.confirm(conversation_id, True)
        assert history.get_run_summary("r1") is None
        assert store.watches(conversation_id) == []


class TestDelivery:
    def test_a_finished_run_lands_as_a_notice_and_the_bot_reports_it(self, isolated_db):
        finished_run()
        model = ScriptedModel([text("AAPL came back bullish, 7.2.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.append_message(conversation_id, {"role": "user", "content": "run AAPL"})
        store.append_message(conversation_id, {"role": "assistant", "content": "Started r1."})
        store.add_watch(conversation_id, "r1", "en")

        assert bot.deliver_notices(conversation_id) is True

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", NOTICE_ROLE, "assistant"]
        assert rows[2]["content"].startswith(NOTICE_PREFIX)
        assert rows[2]["run"]["run_id"] == "r1" and rows[2]["run"]["status"] == "succeeded"
        assert rows[3]["content"] == "AAPL came back bullish, 7.2."
        assert store.watches(conversation_id) == []
        # The model read the notice as the user's line, last in the request.
        sent = model.requests[0]["messages"]
        assert sent[-1] == {"role": "user", "content": rows[2]["content"]}
        assert "[Run notice]" in sent[0]["content"]

    def test_the_report_is_written_in_the_language_the_run_was_started_in(self, isolated_db):
        finished_run()
        model = ScriptedModel([text("苹果：看多，7.2。")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "zh")
        assert bot.deliver_notices(conversation_id) is True
        assert "Reply in Simplified Chinese" in model.requests[0]["messages"][0]["content"]
        assert "notice" not in store.messages(conversation_id)[-1]

    def test_nothing_happens_while_a_watched_run_still_runs(self, isolated_db):
        history.create_run("r1", "AAPL", inputs={"tier": 1}, status=history.STATUS_RUNNING)
        model = ScriptedModel([])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        assert bot.deliver_notices(conversation_id) is False
        assert store.messages(conversation_id) == []
        assert [w["run_id"] for w in store.watches(conversation_id)] == ["r1"]

    def test_a_watch_on_a_run_that_is_gone_is_dropped_without_a_notice(self, isolated_db):
        model = ScriptedModel([])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "ghost", "en")
        assert bot.deliver_notices(conversation_id) is False
        assert store.watches(conversation_id) == []
        assert store.messages(conversation_id) == []

    def test_run_finished_delivers_on_its_own_thread(self, isolated_db):
        finished_run()
        model = ScriptedModel([text("Done: bullish.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")

        bot.run_finished("r1", history.STATUS_SUCCEEDED)

        assert wait_until(lambda: roles(conversation_id) == [NOTICE_ROLE, "assistant"])
        assert wait_until(lambda: not bot.is_busy(conversation_id))

    def test_a_notice_waits_for_the_running_turn_and_lands_at_its_exit(self, isolated_db):
        finished_run()
        model = ScriptedModel([text("Hello."), text("And r1 finished: bullish.")])
        model.release.clear()
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")

        turn = threading.Thread(target=bot.send, args=(conversation_id, "hi"))
        turn.start()
        assert model.asked.wait(COLD_TURN_WAIT)
        # Mid-turn: the run's end is noted, but no row lands.
        assert bot.is_busy(conversation_id)
        assert bot.deliver_notices(conversation_id) is False
        bot.run_finished("r1", history.STATUS_SUCCEEDED)
        time.sleep(0.1)
        assert roles(conversation_id) == ["user"]

        model.release.set()
        turn.join(COLD_TURN_WAIT)
        # The turn's exit delivered it: the notice after the reply, never inside the turn.
        assert wait_until(lambda: roles(conversation_id) == ["user", "assistant", NOTICE_ROLE, "assistant"])
        assert wait_until(lambda: not bot.is_busy(conversation_id))
        assert store.messages(conversation_id)[-1]["content"] == "And r1 finished: bullish."

    def test_a_notice_waits_while_a_held_call_waits_for_the_user(self, isolated_db):
        finished_run()
        model = ScriptedModel([call("delete_run", {"run_id": "r1"}), text("Kept it."), text("r1 finished: bullish.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        bot.send(conversation_id, "delete r1")
        assert store.get_pending(conversation_id) is not None
        # The exit of that turn tried to deliver and found the held call.
        assert wait_until(lambda: not bot.is_busy(conversation_id))
        time.sleep(0.1)
        assert roles(conversation_id) == ["user", "assistant"]
        assert bot.deliver_notices(conversation_id) is False

        bot.confirm(conversation_id, False)
        assert wait_until(lambda: roles(conversation_id) == ["user", "assistant", "tool", "assistant", NOTICE_ROLE, "assistant"])

    def test_the_notice_turns_own_exit_sets_off_no_further_turn(self, isolated_db):
        finished_run()
        history.create_run("r2", "MSFT", inputs={"tier": 1}, status=history.STATUS_RUNNING)
        model = ScriptedModel([text("r1: bullish.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        store.add_watch(conversation_id, "r2", "en")
        assert bot.deliver_notices(conversation_id) is True
        time.sleep(0.3)
        assert len(model.requests) == 1
        assert [w["run_id"] for w in store.watches(conversation_id)] == ["r2"]

    def test_two_finished_runs_land_as_two_notices_and_one_turn(self, isolated_db):
        finished_run("r1", "AAPL")
        finished_run("r2", "MSFT", status=history.STATUS_FAILED, error="boom")
        model = ScriptedModel([text("AAPL bullish; MSFT failed.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        store.add_watch(conversation_id, "r2", "en")
        assert bot.deliver_notices(conversation_id) is True
        assert roles(conversation_id) == [NOTICE_ROLE, NOTICE_ROLE, "assistant"]
        assert len(model.requests) == 1

    def test_catch_up_delivers_every_waiting_conversation(self, isolated_db):
        finished_run()
        model = ScriptedModel([text("r1 done."), text("r1 done.")])
        bot = ChatHarness(model)
        first = store.create_conversation()["id"]
        second = store.create_conversation()["id"]
        store.add_watch(first, "r1", "en")
        store.add_watch(second, "r1", "en")
        bot.catch_up()
        assert wait_until(lambda: roles(first) == [NOTICE_ROLE, "assistant"] and roles(second) == [NOTICE_ROLE, "assistant"])

    def test_the_page_can_stop_the_notice_turn(self, isolated_db):
        finished_run()
        model = ScriptedModel([call("get_run", {"run_id": "r1"})])
        model.release.clear()
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        bot.run_finished("r1", history.STATUS_SUCCEEDED)
        assert model.asked.wait(COLD_TURN_WAIT)
        assert bot.stop(conversation_id) is True
        model.release.set()
        assert wait_until(lambda: roles(conversation_id) == [NOTICE_ROLE, "assistant", "tool", "stopped"])


class TestRunServiceSignal:
    def test_the_harness_is_told_when_a_run_ends(self, isolated_db):
        told: List[Any] = []
        run_service.on_run_finished(lambda run_id, status: told.append((run_id, status)))
        try:
            history.create_run("r1", "AAPL", inputs={"tier": 1}, status=history.STATUS_RUNNING)
            run = run_service.QueuedRun(run_id="r1", ticker="AAPL", inputs={"tier": 1})

            def fail(*args, **kwargs):
                raise RuntimeError("boom")

            with patch.object(run_service, "_run_analysis", fail):
                run_service._execute_run(run)
        finally:
            run_service._finished_listeners.clear()
        assert told == [("r1", history.STATUS_FAILED)]
        assert history.get_run_summary("r1")["status"] == history.STATUS_FAILED

    def test_a_failing_listener_never_fails_the_run_or_the_others(self, isolated_db):
        told: List[str] = []

        def bad(run_id, status):
            raise RuntimeError("listener broke")

        run_service.on_run_finished(bad)
        run_service.on_run_finished(lambda run_id, status: told.append(status))
        try:
            history.create_run("r1", "AAPL", inputs={"tier": 1}, status=history.STATUS_RUNNING)
            run = run_service.QueuedRun(run_id="r1", ticker="AAPL", inputs={"tier": 1})
            with patch.object(run_service, "_run_analysis", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))):
                run_service._execute_run(run)
        finally:
            run_service._finished_listeners.clear()
        assert told == [history.STATUS_FAILED]
