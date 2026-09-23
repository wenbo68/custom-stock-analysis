# -*- coding: utf-8 -*-
"""Offline tests for the chatbot loop (src/chatbot/harness.py) on a
scripted model: every reply is queued in advance, so the tests pin
exactly what the loop stores, when it stops, and what it asks."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

import pytest

from src.chatbot import harness as harness_module
from src.chatbot import store
from src.chatbot.harness import (
    MAX_TOOL_ROUNDS,
    ChatHarness,
    ConfirmationPendingError,
    ConversationBusyError,
    NothingPendingError,
    UnknownConversationError,
    cap_result,
    model_view,
    trim_history,
)
from src.chatbot.model import ModelReply
from src.tiered_analysis import history


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "chat_harness.db")
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


class ScriptedModel:
    """Answers with the queued replies in order and records every
    request, so a test can inspect what the model was shown."""

    def __init__(self, replies: List[ModelReply]) -> None:
        self.replies = list(replies)
        self.requests: List[Dict[str, Any]] = []
        self.release = threading.Event()
        self.release.set()

    def complete(self, messages, tools):
        self.release.wait(timeout=5)
        self.requests.append({"messages": messages, "tools": tools})
        if not self.replies:
            raise AssertionError("model asked more often than scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def text(content, **usage):
    return ModelReply(content=content, prompt_tokens=usage.get("prompt"),
                      completion_tokens=usage.get("completion"), model="fake")


def call(name, args, call_id="c1"):
    return ModelReply(content=None, tool_calls=[{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }])


def calls(*specs):
    return ModelReply(content=None, tool_calls=[{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    } for call_id, name, args in specs])


def roles(conversation_id):
    return [m["role"] for m in store.messages(conversation_id)]


def tool_result(message):
    return json.loads(message["content"])


class TestPlainTurns:
    def test_answer_without_tools(self, isolated_db):
        model = ScriptedModel([text("Hello!", prompt=50, completion=5)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant"]
        assert rows[1]["content"] == "Hello!"
        assert rows[1]["usage"] == {"prompt_tokens": 50, "completion_tokens": 5}
        assert rows[1]["model"] == "fake"
        sent = model.requests[0]["messages"]
        assert sent[0]["role"] == "system"
        assert "Custom Stock Analysis" in sent[0]["content"]
        assert "Server time" in sent[0]["content"]
        assert sent[1:] == [{"role": "user", "content": "hi"}]
        assert {t["function"]["name"] for t in model.requests[0]["tools"]} >= {"list_runs", "start_run"}
        # The call's transcript rides on the reply for the page: the whole
        # request as text, the raw reply, and the time it took.
        transcript = rows[1]["transcript"]
        assert transcript["prompt"].startswith("=== system ===\n")
        assert "=== user ===\nhi" in transcript["prompt"]
        assert "=== tools offered ===" in transcript["prompt"] and '"list_runs"' in transcript["prompt"]
        assert transcript["reply"] == "Hello!"
        assert transcript["temperature"] == 0.0
        assert isinstance(rows[1]["duration_ms"], int)

    def test_tool_call_then_answer(self, isolated_db):
        history.create_run("t1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("list_tickers", {}), text("You have run AAPL.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "what have I run?")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "tool", "assistant"]
        assert rows[1]["tool_calls"][0]["function"]["name"] == "list_tickers"
        assert tool_result(rows[2]) == {"items": ["AAPL"]}
        assert rows[2]["chars"] == len(rows[2]["content"])
        assert rows[2]["truncated"] is False
        assert isinstance(rows[2]["duration_ms"], int)
        # The second model request carries the call and its result, and
        # nothing of the page-only facts.
        second = model.requests[1]["messages"]
        assert second[2]["role"] == "assistant"
        assert second[2]["tool_calls"][0]["id"] == "c1"
        assert second[3] == {"role": "tool", "tool_call_id": "c1", "name": "list_tickers",
                             "content": rows[2]["content"]}
        assert "chars" not in second[3]
        assert "transcript" not in second[2] and "duration_ms" not in second[2]
        # The tool-asking reply's transcript shows the calls as JSON.
        assert rows[1]["transcript"]["reply"].startswith("[tool calls]\n")
        assert '"list_tickers"' in rows[1]["transcript"]["reply"]

    def test_unknown_tool_and_bad_arguments_answer_as_errors(self, isolated_db):
        model = ScriptedModel([
            calls(("c1", "fly_to_moon", {}), ("c2", "get_run", {})),
            text("Sorry."),
        ])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "go")
        rows = store.messages(conversation_id)
        assert tool_result(rows[2])["error"] == "unknown_tool"
        assert tool_result(rows[3])["error"] == "invalid_arguments"
        assert rows[4]["content"] == "Sorry."

    def test_model_failure_is_a_visible_message_not_a_crash(self, isolated_db):
        model = ScriptedModel([RuntimeError("quota exceeded")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi")
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant"]
        assert rows[1]["error"] == "quota exceeded"
        assert "quota exceeded" in rows[1]["content"]

    def test_step_cap_stops_a_looping_model(self, isolated_db):
        model = ScriptedModel([call("list_tickers", {}, f"c{i}") for i in range(MAX_TOOL_ROUNDS + 1)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "loop")
        rows = store.messages(conversation_id)
        assert rows[-1]["notice"] == "step_cap"
        assert len(model.requests) == MAX_TOOL_ROUNDS + 1
        assert roles(conversation_id).count("tool") == MAX_TOOL_ROUNDS

    def test_a_tool_that_raises_answers_with_an_error(self, isolated_db, monkeypatch):
        from src.chatbot import tools

        def boom(_):
            raise RuntimeError("db gone")

        catalog = tools.ToolCatalog((tools.Tool("list_tickers", "x", tools.NoParams, boom),))
        model = ScriptedModel([call("list_tickers", {}), text("hm")])
        bot = ChatHarness(model, catalog)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "go")
        assert tool_result(store.messages(conversation_id)[2]) == {
            "error": "tool_failed", "message": "RuntimeError: db gone",
        }


class TestConfirmation:
    def test_gated_tool_waits_then_runs_on_yes(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("delete_run", {"task_id": "q1"}), text("Deleted.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "cancel q1")

        assert roles(conversation_id) == ["user", "assistant"]
        pending = store.get_pending(conversation_id)
        assert pending["calls"][0]["name"] == "delete_run"
        assert pending["calls"][0]["args"] == {"task_id": "q1"}
        assert pending["calls"][0]["facts"]["run"]["stock_code"] == "AAPL"
        assert history.run_exists("q1")
        with pytest.raises(ConfirmationPendingError):
            bot.send(conversation_id, "another message")

        bot.confirm(conversation_id, approved=True)
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "tool", "assistant"]
        assert tool_result(rows[2])["deleted"] is True
        assert rows[2]["approved"] is True
        assert rows[3]["content"] == "Deleted."
        assert store.get_pending(conversation_id) is None
        assert not history.run_exists("q1")

    def test_no_records_the_refusal_and_keeps_the_run(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("delete_run", {"task_id": "q1"}), text("Kept.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "cancel q1")
        bot.confirm(conversation_id, approved=False)
        rows = store.messages(conversation_id)
        assert tool_result(rows[2])["declined"] is True
        assert rows[2]["approved"] is False
        assert history.run_exists("q1")
        assert rows[3]["content"] == "Kept."

    def test_gate_that_finds_nothing_to_confirm_answers_at_once(self, isolated_db):
        model = ScriptedModel([call("delete_run", {"task_id": "ghost"}), text("No such run.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "delete ghost")
        assert store.get_pending(conversation_id) is None
        assert tool_result(store.messages(conversation_id)[2])["error"] == "not_found"

    def test_several_held_calls_are_answered_one_at_a_time(self, isolated_db):
        history.create_run("a", "AAPL", inputs={"tier": 1}, status="queued")
        history.create_run("b", "MSFT", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([
            calls(("c1", "delete_run", {"task_id": "a"}), ("c2", "list_tickers", {}),
                  ("c3", "delete_run", {"task_id": "b"})),
            text("Done."),
        ])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "clean up")
        # The ungated call ran at once; the two gated ones wait in order.
        assert roles(conversation_id) == ["user", "assistant", "tool"]
        assert [c["call_id"] for c in store.get_pending(conversation_id)["calls"]] == ["c1", "c3"]

        bot.confirm(conversation_id, approved=True)
        assert [c["call_id"] for c in store.get_pending(conversation_id)["calls"]] == ["c3"]
        assert len(model.requests) == 1
        bot.confirm(conversation_id, approved=False)
        assert store.get_pending(conversation_id) is None
        assert len(model.requests) == 2
        assert store.messages(conversation_id)[-1]["content"] == "Done."
        assert not history.run_exists("a")
        assert history.run_exists("b")

    def test_confirm_with_nothing_held_is_refused(self, isolated_db):
        bot = ChatHarness(ScriptedModel([]))
        conversation_id = store.create_conversation()["id"]
        with pytest.raises(NothingPendingError):
            bot.confirm(conversation_id, approved=True)


class TestGuards:
    def test_unknown_conversation(self, isolated_db):
        bot = ChatHarness(ScriptedModel([]))
        with pytest.raises(UnknownConversationError):
            bot.send("nope", "hi")

    def test_a_second_turn_while_one_runs_is_refused(self, isolated_db):
        model = ScriptedModel([text("slow"), text("fast")])
        model.release.clear()
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        errors: List[Exception] = []

        def first_turn():
            try:
                bot.send(conversation_id, "one")
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        worker = threading.Thread(target=first_turn)
        worker.start()
        try:
            deadline = threading.Event()
            for _ in range(200):
                if model.requests or not worker.is_alive():
                    break
                deadline.wait(0.01)
            with pytest.raises(ConversationBusyError):
                bot.send(conversation_id, "two")
        finally:
            model.release.set()
            worker.join(timeout=5)
        assert errors == []
        assert roles(conversation_id) == ["user", "assistant"]


class TestHelpers:
    def test_model_view_strips_page_facts(self):
        assert model_view({"role": "tool", "tool_call_id": "c", "name": "n", "content": "x",
                           "chars": 1, "truncated": False, "approved": True}) == {
            "role": "tool", "tool_call_id": "c", "name": "n", "content": "x",
        }
        assert model_view({"role": "assistant", "content": None, "usage": {}}) == {"role": "assistant"}

    def test_trim_history_cuts_at_a_user_message(self):
        messages = [{"role": "user", "content": "0"}]
        for i in range(1, 50):
            messages.append({"role": "assistant" if i % 3 == 1 else "tool" if i % 3 == 2 else "user",
                             "content": str(i)})
        kept = trim_history(messages, limit=10)
        assert len(kept) <= 10
        assert kept[0]["role"] == "user"
        assert kept[-1] is messages[-1]
        assert trim_history([{"role": "tool", "content": "orphan"}], limit=5) == []

    def test_cap_result_cuts_with_a_note(self):
        small = cap_result({"a": 1})
        assert small == {"content": '{"a": 1}', "chars": 8, "truncated": False}
        big = cap_result({"text": "x" * 100}, cap=20)
        assert big["truncated"] is True
        assert big["chars"] == len(json.dumps({"text": "x" * 100}))
        assert big["content"].startswith('{"text": "xxxxxxxxxx')
        assert "cut:" in big["content"]

    def test_history_limit_is_the_documented_one(self):
        assert harness_module.HISTORY_MESSAGE_LIMIT == 40
