# -*- coding: utf-8 -*-
"""Offline tests for the chat bot loop (src/chat/harness.py) on a
scripted model: every reply is queued in advance, so the tests pin
exactly what the loop stores, when it stops, and what it asks."""
from __future__ import annotations

import dataclasses
import json
import os
import threading
from typing import Any, Dict, List

import pytest

from src.chat import harness as harness_module
from src.chat import store
from src.chat.harness import (
    LANGUAGE_RETRY_LIMIT,
    STOPPED_LATE_MESSAGE,
    STOPPED_MESSAGE,
    STOPPED_ROLE,
    TOOL_CALL_LIMIT,
    ChatHarness,
    ConfirmationPendingError,
    ConversationBusyError,
    NothingPendingError,
    NothingToCompactError,
    UnknownConversationError,
    cap_result,
    model_view,
    trim_history,
)
from src.chat.model import ModelReply
from src.chat.tools import TOOLS, NoParams, Tool, ToolCatalog
from src.tiered_analysis import history

#: How long a test waits for the scripted model to be asked. Generous:
#: the first turn in a process pays the cold imports behind the system
#: prompt's server status (the analysis stack, about 4 s) and the
#: model-table lookup (litellm, about 3 s), which made a 5 s wait fail
#: now and then (2026-10-14). A broken turn still fails, just later.
COLD_TURN_WAIT = 30


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


@pytest.fixture(autouse=True)
def fallback_window(monkeypatch):
    """Size requests against the fallback window: the model-table lookup
    imports litellm, which takes seconds on a cold process."""
    from src.chat import context

    context.litellm_limits.cache_clear()
    monkeypatch.setattr(context, "litellm_limits", lambda llm: None)


class ScriptedModel:
    """Answers with the queued replies in order and records every
    request, so a test can inspect what the model was shown."""

    def __init__(self, replies: List[ModelReply]) -> None:
        self.replies = list(replies)
        self.requests: List[Dict[str, Any]] = []
        self.release = threading.Event()
        self.release.set()
        #: Set the moment the model is asked, before it waits on `release`.
        self.asked = threading.Event()

    def complete(self, messages, tools, tool_choice="auto"):
        self.asked.set()
        self.release.wait(timeout=5)
        self.requests.append({"messages": messages, "tools": tools})
        if not self.replies:
            raise AssertionError("model asked more often than scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def text(content, **usage):
    return ModelReply(content=content, input_tokens=usage.get("prompt"),
                      output_tokens=usage.get("completion"), llm="fake")


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


class TestReplyLanguage:
    ENGLISH = "The latest run on AAPL is bullish with a score of 7.2 out of 10."
    CHINESE = "苹果最近一次分析的展望是看涨，评分 7.2。"

    def test_a_wrong_language_reply_is_sent_back_with_a_correction(self, isolated_db):
        model = ScriptedModel([text(self.ENGLISH), text(self.CHINESE)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "how is AAPL?", language="zh")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "assistant"]
        assert rows[1]["content"] == self.ENGLISH
        assert rows[1]["notice"] == "wrong_language"
        assert rows[2]["content"] == self.CHINESE
        assert "notice" not in rows[2]
        # The retry shows the model its wrong reply, then the correction as
        # the last user line — which is not stored, only in the transcript.
        retry = model.requests[1]["messages"]
        assert retry[-2] == {"role": "assistant", "content": self.ENGLISH}
        assert retry[-1]["role"] == "user"
        assert "Simplified Chinese" in retry[-1]["content"]
        assert "Simplified Chinese" in rows[2]["transcript"]["input"]

    def test_after_the_retry_limit_the_last_reply_stands(self, isolated_db):
        model = ScriptedModel([text(self.ENGLISH)] * (LANGUAGE_RETRY_LIMIT + 1))
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "how is AAPL?", language="zh")

        assert len(model.requests) == LANGUAGE_RETRY_LIMIT + 1
        rows = store.messages(conversation_id)
        assert [r.get("notice") for r in rows[1:]] == ["wrong_language"] * (LANGUAGE_RETRY_LIMIT + 1)

    def test_a_right_language_reply_is_not_questioned(self, isolated_db):
        model = ScriptedModel([text(self.ENGLISH)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "how is AAPL?", language="en")
        assert len(model.requests) == 1
        assert "notice" not in store.messages(conversation_id)[1]

    def test_a_tool_calling_reply_is_never_a_language_problem(self, isolated_db):
        model = ScriptedModel([call("list_tickers", {}), text(self.CHINESE)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "有哪些运行？", language="zh")
        assert roles(conversation_id) == ["user", "assistant", "tool", "assistant"]
        assert all("notice" not in r for r in store.messages(conversation_id))

    def test_the_resumed_loop_after_a_yes_keeps_the_language(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("delete_run", {"run_id": "q1"}), text(self.ENGLISH), text(self.CHINESE)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "删除 AAPL 的运行", language="zh")
        assert store.get_pending(conversation_id)
        bot.confirm(conversation_id, True, language="zh")

        assert "Reply in Simplified Chinese" in model.requests[1]["messages"][0]["content"]
        rows = store.messages(conversation_id)
        assert rows[-2]["notice"] == "wrong_language"
        assert rows[-1]["content"] == self.CHINESE


class TestPlainTurns:
    def test_answer_without_tools(self, isolated_db):
        model = ScriptedModel([text("Hello!", prompt=50, completion=5)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant"]
        assert rows[1]["content"] == "Hello!"
        assert rows[1]["usage"] == {"input_tokens": 50, "output_tokens": 5}
        assert rows[1]["llm"] == "fake"
        sent = model.requests[0]["messages"]
        assert sent[0]["role"] == "system"
        assert "Custom Stock Analysis" in sent[0]["content"]
        assert "Server time" in sent[0]["content"]
        assert sent[1:] == [{"role": "user", "content": "hi"}]
        assert {t["function"]["name"] for t in model.requests[0]["tools"]} >= {"list_runs", "start_run"}
        # The call's transcript rides on the reply for the page: the whole
        # request as text, the raw reply, and the time it took.
        transcript = rows[1]["transcript"]
        assert transcript["input"].startswith("=== system ===\n")
        assert "=== user ===\nhi" in transcript["input"]
        assert "=== tools offered ===" in transcript["input"] and '"list_runs"' in transcript["input"]
        assert transcript["output"] == "Hello!"
        assert transcript["temperature"] == 0.0
        assert isinstance(rows[1]["time_ms"], int)

    def test_the_prompt_names_the_chosen_language(self, isolated_db):
        model = ScriptedModel([text("你好！")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi", language="zh")
        assert "Reply in Simplified Chinese" in model.requests[0]["messages"][0]["content"]
        assert "notice" not in store.messages(conversation_id)[1]

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
        assert rows[2]["output_chars"] == len(rows[2]["content"])
        assert rows[2]["truncated"] is False
        assert isinstance(rows[2]["time_ms"], int)
        # The second model request carries the call and its result, and
        # nothing of the page-only facts.
        second = model.requests[1]["messages"]
        assert second[2]["role"] == "assistant"
        assert second[2]["tool_calls"][0]["id"] == "c1"
        assert second[3] == {"role": "tool", "tool_call_id": "c1", "name": "list_tickers",
                             "content": rows[2]["content"]}
        assert "output_chars" not in second[3]
        assert "transcript" not in second[2] and "time_ms" not in second[2]
        # The tool-asking reply's transcript shows the calls as JSON.
        assert rows[1]["transcript"]["output"].startswith("[tool calls]\n")
        assert '"list_tickers"' in rows[1]["transcript"]["output"]

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

    def test_tool_call_limit_stops_a_looping_model(self, isolated_db):
        model = ScriptedModel([call("list_tickers", {}, f"c{i}") for i in range(TOOL_CALL_LIMIT + 1)])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "loop")
        rows = store.messages(conversation_id)
        assert rows[-1]["notice"] == "tool_call_limit"
        assert len(model.requests) == TOOL_CALL_LIMIT + 1
        # The reply that hit the limit is answered too, with an error
        # result instead of a run, so no tool call is ever left open.
        assert roles(conversation_id).count("tool") == TOOL_CALL_LIMIT + 1
        assert rows[-2]["role"] == "tool" and rows[-2]["tool_call_id"] == f"c{TOOL_CALL_LIMIT}"
        assert tool_result(rows[-2])["error"] == "tool_call_limit"
        assert "time_ms" not in rows[-2]  # nothing ran

    def test_the_conversation_still_works_after_the_limit(self, isolated_db):
        """Regression (2026-10-10): the limit used to leave the last
        reply's tool calls unanswered, and OpenAI-style providers reject
        every later request that carries an unanswered call."""
        model = ScriptedModel(
            [calls((f"c{i}a", "list_tickers", {}), (f"c{i}b", "list_tickers", {}))
             for i in range(TOOL_CALL_LIMIT + 1)] + [text("Still here.")]
        )
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "loop")
        bot.send(conversation_id, "and now?")

        assert store.messages(conversation_id)[-1]["content"] == "Still here."
        sent = model.requests[-1]["messages"]
        asked = {c["id"] for m in sent if m.get("tool_calls") for c in m["tool_calls"]}
        answered = {m["tool_call_id"] for m in sent if m["role"] == "tool"}
        assert asked and asked == answered

    def test_a_tool_that_raises_answers_with_an_error(self, isolated_db, monkeypatch):
        from src.chat import tools

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
    def test_the_answer_and_the_remaining_held_calls_are_one_write(self, isolated_db, monkeypatch):
        """Regression (2026-10-10): the tool result and the shortened
        pending list used to be two commits; a crash between them left
        the already-answered call still held, to be run again."""
        history.create_run("a", "AAPL", inputs={"tier": 1}, status="queued")
        history.create_run("b", "MSFT", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([
            calls(("c1", "delete_run", {"run_id": "a"}), ("c2", "delete_run", {"run_id": "b"})),
            text("Done."),
        ])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "clean up")
        assert [c["call_id"] for c in store.get_pending(conversation_id)["calls"]] == ["c1", "c2"]

        commits: List[int] = []
        real_session = store._session

        def counting_session():
            session = real_session()
            real_commit = session.commit

            def commit():
                commits.append(1)
                real_commit()

            session.commit = commit
            return session

        monkeypatch.setattr(store, "_session", counting_session)
        bot.confirm(conversation_id, approved=False)

        assert len(commits) == 1
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "tool"]
        assert tool_result(rows[2])["declined"] is True
        assert [c["call_id"] for c in store.get_pending(conversation_id)["calls"]] == ["c2"]

    def test_gated_tool_waits_then_runs_on_yes(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("delete_run", {"run_id": "q1"}), text("Deleted.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "cancel q1")

        assert roles(conversation_id) == ["user", "assistant"]
        pending = store.get_pending(conversation_id)
        assert pending["calls"][0]["name"] == "delete_run"
        assert pending["calls"][0]["input"] == {"run_id": "q1"}
        assert pending["calls"][0]["facts"]["run"]["ticker"] == "AAPL"
        assert history.run_exists("q1")
        with pytest.raises(ConfirmationPendingError):
            bot.send(conversation_id, "another message")

        bot.confirm(conversation_id, approved=True)
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "tool", "assistant"]
        assert tool_result(rows[2])["deleted"] is True
        assert rows[2]["approved"] is True
        # The row keeps the inputs it ran with, for the page's input fold.
        assert rows[2]["input"] == {"run_id": "q1"}
        assert rows[3]["content"] == "Deleted."
        assert store.get_pending(conversation_id) is None
        assert not history.run_exists("q1")

    def test_no_records_the_refusal_and_keeps_the_run(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("delete_run", {"run_id": "q1"}), text("Kept.")])
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
        model = ScriptedModel([call("delete_run", {"run_id": "ghost"}), text("No such run.")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "delete ghost")
        assert store.get_pending(conversation_id) is None
        assert tool_result(store.messages(conversation_id)[2])["error"] == "not_found"

    def test_several_held_calls_are_answered_one_at_a_time(self, isolated_db):
        history.create_run("a", "AAPL", inputs={"tier": 1}, status="queued")
        history.create_run("b", "MSFT", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([
            calls(("c1", "delete_run", {"run_id": "a"}), ("c2", "list_tickers", {}),
                  ("c3", "delete_run", {"run_id": "b"})),
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
        assert bot.delete_conversation("nope") is False

    def test_delete_waits_for_no_turn_and_frees_the_lock(self, isolated_db):
        """Regression (2026-10-10): deleting a conversation under a
        running turn made the turn crash with a bare KeyError (a 500 to
        the user, and the paid model call wasted). Now the delete is
        refused as busy while a turn runs, and once it is through, the
        delete also drops the conversation's lock entry."""
        model = ScriptedModel([text("slow")])
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
                bot.delete_conversation(conversation_id)
        finally:
            model.release.set()
            worker.join(timeout=5)
        assert errors == []
        assert roles(conversation_id) == ["user", "assistant"]
        assert conversation_id in bot._locks

        assert bot.delete_conversation(conversation_id) is True
        assert conversation_id not in bot._locks
        assert store.conversation_exists(conversation_id) is False
        with pytest.raises(UnknownConversationError):
            bot.send(conversation_id, "two")

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
                           "output_chars": 1, "truncated": False, "approved": True}) == {
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

    def test_trim_history_keeps_the_whole_last_turn_even_over_the_limit(self):
        """Regression (2026-10-10): one turn of 50 rows under a 40-row
        window used to leave no user row inside the window, so the model
        got only the system prompt."""
        turn = [{"role": "user", "content": "q"}]
        for i in range(8):
            turn.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}{j}"} for j in range(5)]})
            turn.extend({"role": "tool", "tool_call_id": f"c{i}{j}", "content": "{}"} for j in range(5))
        turn.append({"role": "assistant", "content": "a"})
        assert len(turn) == 50
        kept = trim_history(turn, limit=40)
        assert kept == turn

        # Older turns come back in whole while they fit.
        older = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old a"}]
        assert trim_history(older + turn, limit=40) == turn
        assert trim_history(older + turn, limit=52) == older + turn
        assert trim_history(older + older + turn, limit=53) == older + turn

    def test_cap_result_cuts_with_a_note(self):
        small = cap_result({"a": 1})
        assert small == {"content": '{"a": 1}', "output_chars": 8, "truncated": False}
        big = cap_result({"text": "x" * 100}, cap=20)
        assert big["truncated"] is True
        assert big["output_chars"] == len(json.dumps({"text": "x" * 100}))
        assert big["content"].startswith('{"text": "xxxxxxxxxx')
        assert "cut:" in big["content"]

    def test_history_limit_is_the_documented_one(self):
        assert harness_module.HISTORY_MESSAGE_LIMIT == 40


class TestStop:
    """The stop button (2026-10-12): a turn asked to stop lets the model
    call in flight finish and stores its reply, tokens and all (so the
    page's spent total matches the bill, whichever provider); then every
    tool call not yet run is answered with a `stopped` error instead of
    run (never held), and a `stopped` row ends the turn — one the model
    later sees as a user line, so the stopped turn stays in the context
    as what it was. A stop during the final reply cuts nothing: the reply
    stands and the row says so."""

    @staticmethod
    def _start(bot, conversation_id, text_="one"):
        errors: List[Exception] = []

        def turn():
            try:
                bot.send(conversation_id, text_)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        worker = threading.Thread(target=turn)
        worker.start()
        return worker, errors

    def test_stop_during_the_model_call_waits_for_its_reply_then_ends_the_turn(self, isolated_db):
        slow = dataclasses.replace(call("list_tickers", {}), input_tokens=120, output_tokens=30)
        model = ScriptedModel([slow, text("again")])
        model.release.clear()
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        worker, errors = self._start(bot, conversation_id)
        try:
            assert model.asked.wait(timeout=COLD_TURN_WAIT)
            assert bot.stop(conversation_id) is True
            # The turn does not end while the model is still "thinking":
            # the step in flight is let finish, so its tokens are known.
            worker.join(timeout=0.5)
            assert worker.is_alive()
            assert roles(conversation_id) == ["user"]
        finally:
            model.release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert errors == []
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "tool", STOPPED_ROLE]
        # The reply stands, with what it cost; its call is answered, not run.
        assert rows[1]["usage"] == {"input_tokens": 120, "output_tokens": 30}
        assert rows[1]["tool_calls"][0]["id"] == "c1"
        assert tool_result(rows[2])["error"] == "stopped"
        assert "time_ms" not in rows[2]
        assert rows[3]["content"] == STOPPED_MESSAGE
        assert conversation_id not in bot._stops
        assert len(model.requests) == 1
        # Not one of the user's inputs: the sidebar counts one question,
        # and the step's tokens are in its total.
        facts = store.get_conversation(conversation_id)
        assert facts["user_input_count"] == 1
        assert facts["total_tokens"] == 150

        # The next turn runs as usual; the model sees the stop as a user
        # line before the new question.
        bot.send(conversation_id, "two")
        assert roles(conversation_id) == ["user", "assistant", "tool", STOPPED_ROLE, "user", "assistant"]
        shown = next(r["messages"] for r in model.requests if r["messages"][-1] == {"role": "user", "content": "two"})
        assert shown[-2] == {"role": "user", "content": STOPPED_MESSAGE}
        assert shown[-3]["role"] == "tool"

    def test_stop_during_the_final_reply_keeps_it_whole_and_says_so(self, isolated_db):
        # The last step asks for no tool, so stopping it cuts nothing:
        # the reply is whole, and the stopped row tells the model (and
        # the page) that, not that a finished answer was cut short.
        model = ScriptedModel([text("done")])
        model.release.clear()
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        worker, errors = self._start(bot, conversation_id)
        try:
            assert model.asked.wait(timeout=COLD_TURN_WAIT)
            assert bot.stop(conversation_id) is True
        finally:
            model.release.set()
        worker.join(timeout=5)
        assert errors == []
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", STOPPED_ROLE]
        assert rows[1]["content"] == "done"
        assert rows[2]["content"] == STOPPED_LATE_MESSAGE

    def test_stop_during_a_final_reply_in_the_wrong_language_sends_no_retry(self, isolated_db):
        holder: Dict[str, Any] = {}

        class StoppingModel(ScriptedModel):
            def complete(self, messages, tools, tool_choice="auto"):
                holder["bot"].stop(holder["id"])
                return super().complete(messages, tools)

        model = StoppingModel([text("English where Chinese was asked")])
        bot = ChatHarness(model)
        conversation_id = store.create_conversation()["id"]
        holder.update(bot=bot, id=conversation_id)
        bot.send(conversation_id, "你好", language="zh")
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", STOPPED_ROLE]
        assert rows[1]["notice"] == "wrong_language"
        assert rows[2]["content"] == STOPPED_LATE_MESSAGE
        assert len(model.requests) == 1

    def test_stop_under_a_tool_answers_the_rest_and_asks_the_model_nothing_more(self, isolated_db):
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        holder: Dict[str, Any] = {}

        def stopper(params):
            holder["bot"].stop(holder["id"])
            return {"ok": True}

        catalog = ToolCatalog((Tool(name="stopper", description="stops the turn", params=NoParams, run=stopper), *TOOLS))
        model = ScriptedModel([calls(
            ("c1", "delete_run", {"run_id": "q1"}), ("c2", "stopper", {}), ("c3", "list_tickers", {}),
        )])
        bot = ChatHarness(model, catalog)
        conversation_id = store.create_conversation()["id"]
        holder.update(bot=bot, id=conversation_id)
        bot.send(conversation_id, "go")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "tool", "tool", "tool", STOPPED_ROLE]
        assert tool_result(rows[2]) == {"ok": True}
        # Not run after the stop: an answer, so the provider sees no open call.
        assert rows[3]["tool_call_id"] == "c3"
        assert tool_result(rows[3])["error"] == "stopped"
        assert "time_ms" not in rows[3]
        # Would have waited for a yes: answered the same way, not held.
        assert rows[4]["tool_call_id"] == "c1"
        assert tool_result(rows[4])["error"] == "stopped"
        assert rows[4]["input"] == {"run_id": "q1"}
        assert store.get_pending(conversation_id) is None
        assert history.run_exists("q1")
        assert len(model.requests) == 1

    def test_stop_with_no_turn_running_is_false_and_unknown_is_an_error(self, isolated_db):
        bot = ChatHarness(ScriptedModel([]))
        conversation_id = store.create_conversation()["id"]
        assert bot.stop(conversation_id) is False
        with pytest.raises(UnknownConversationError):
            bot.stop("nope")

    def test_the_stopped_row_is_a_user_line_to_the_model_and_starts_no_turn(self):
        assert model_view({"role": STOPPED_ROLE, "content": "x", "seq": 3, "created_at": "t"}) == {"role": "user", "content": "x"}
        messages = [
            {"role": "user", "content": "one"}, {"role": "assistant", "content": "a"},
            {"role": STOPPED_ROLE, "content": "x"},
            {"role": "user", "content": "two"}, {"role": "assistant", "content": "b"},
        ]
        # Were the stopped row a turn start, three rows would fit and the
        # turn would open on it, orphaning its own question.
        assert trim_history(messages, limit=3) == messages[3:]
        assert trim_history(messages, limit=5) == messages


class TestCompaction:
    """The context limit and the summary (src/chat/context.py,
    src/chat/compact.py): the loop summarizes by itself past the line,
    the user can ask for it, and the model's view starts at the summary."""

    @staticmethod
    def limit(max_tokens):
        from src.chat.context import ContextLimit

        return lambda: ContextLimit(llm="fake", window=max_tokens * 2, output_limit=max_tokens,
                                    max_tokens=max_tokens, source="litellm")

    def test_past_the_line_the_loop_summarizes_first_and_the_model_sees_the_summary(self, isolated_db):
        from src.chat.compact import SUMMARY_PREFACE, SUMMARY_ROLE, SUMMARY_SYSTEM_PROMPT, TRIGGER_AUTO

        model = ScriptedModel([text("first answer", prompt=100, completion=5)])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hello")
        assert roles(conversation_id) == ["user", "assistant"]

        # A max the standing instructions alone pass: the next turn
        # summarizes before it answers.
        bot = ChatHarness(ScriptedModel([
            text("SUMMARY: the user said hello and was answered.", prompt=120, completion=10),
            text("second answer", prompt=50, completion=5),
        ]), limit=self.limit(100))
        bot.send(conversation_id, "and now?")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "user", SUMMARY_ROLE, "assistant"]
        summary = rows[3]
        assert summary["content"].startswith("SUMMARY:")
        assert summary["compacted"] == {"trigger": TRIGGER_AUTO, "first_seq": 1, "last_seq": 3,
                                        "tokens_before": summary["compacted"]["tokens_before"]}
        assert summary["compacted"]["tokens_before"] >= 85
        assert summary["usage"] == {"input_tokens": 120, "output_tokens": 10}
        assert summary["transcript"]["output"].startswith("SUMMARY:")
        # The summary request: its own one-paragraph system prompt (not
        # the standing instructions), the conversation, the instruction
        # last, and no tool menu.
        summary_request = bot._model.requests[0]
        assert summary_request["messages"][0] == {"role": "system", "content": SUMMARY_SYSTEM_PROMPT}
        assert "## What the app does" not in summary_request["messages"][0]["content"]
        assert summary_request["messages"][-1]["role"] == "user"
        assert "summarized to free up context" in summary_request["messages"][-1]["content"]
        assert [m["content"] for m in summary_request["messages"][1:-1]] == ["hello", "first answer", "and now?"]
        assert summary_request["tools"] == []
        # The answer's request: the summary as a user line, nothing before it.
        answer_request = bot._model.requests[1]
        assert [m["role"] for m in answer_request["messages"]] == ["system", "user"]
        assert answer_request["messages"][1]["content"] == f"{SUMMARY_PREFACE}\n\nSUMMARY: the user said hello and was answered."
        assert rows[4]["content"] == "second answer"

    def test_the_summary_call_writes_tool_calls_out_as_text(self, isolated_db):
        """With no tools defined, a provider may refuse a history that
        holds tool calls (Anthropic's API does), so the summary call
        gets each call and result as plain lines instead."""
        from src.chat.compact import SUMMARY_ROLE, as_text_only

        history.create_run("t1", "AAPL", inputs={"tier": 1}, status="queued")
        model = ScriptedModel([call("list_tickers", {}), text("You have run AAPL.")])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "what have I run?")
        assert roles(conversation_id) == ["user", "assistant", "tool", "assistant"]

        model = ScriptedModel([text("SUMMARY: AAPL was listed.", prompt=90, completion=8)])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        assert bot.compact(conversation_id, "en") is True
        assert roles(conversation_id)[-1] == SUMMARY_ROLE
        sent = model.requests[0]
        assert sent["tools"] == []
        rows = sent["messages"][1:-1]
        assert [m["role"] for m in rows] == ["user", "assistant", "user", "assistant"]
        assert all("tool_calls" not in m and "tool_call_id" not in m for m in rows)
        assert rows[1]["content"] == "[Called list_tickers with {}]"
        assert rows[2]["content"].startswith("[Result of list_tickers]\n") and '"AAPL"' in rows[2]["content"]
        assert rows[3]["content"] == "You have run AAPL."
        # The transcript shows the same text-only request, and an empty tool menu.
        transcript = store.messages(conversation_id)[-1]["transcript"]["input"]
        assert "[Called list_tickers with {}]" in transcript and transcript.endswith("=== tools offered ===\n(none)")

        # A reply with text beside its calls keeps both; the rest passes through.
        rows = as_text_only([
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "Looking.", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "get_run", "arguments": '{"run_id": "r1"}'}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "name": "get_run", "content": "{}"},
        ])
        assert rows == [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": 'Looking.\n[Called get_run with {"run_id": "r1"}]'},
            {"role": "user", "content": "[Result of get_run]\n{}"},
        ]

    def test_one_summary_per_turn_and_the_next_message_starts_after_it(self, isolated_db):
        from src.chat.compact import SUMMARY_ROLE

        model = ScriptedModel([
            text("S1", prompt=1, completion=1),
            call("list_tickers", {}),
            text("done", prompt=1, completion=1),
            text("S2", prompt=1, completion=1),
            text("again", prompt=1, completion=1),
        ])
        bot = ChatHarness(model, limit=self.limit(100))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "list")
        # Still past the line after the tool ran: no second summary this turn.
        assert roles(conversation_id) == ["user", SUMMARY_ROLE, "assistant", "tool", "assistant"]

        bot.send(conversation_id, "more")
        assert roles(conversation_id) == ["user", SUMMARY_ROLE, "assistant", "tool", "assistant", "user", SUMMARY_ROLE, "assistant"]
        rows = store.messages(conversation_id)
        # The second summary stands for everything from the first one on.
        assert (rows[6]["compacted"]["first_seq"], rows[6]["compacted"]["last_seq"]) == (2, 6)
        assert model.requests[3]["messages"][1]["content"].endswith("S1")

    def test_a_failed_summary_is_stored_with_its_error_and_is_no_boundary(self, isolated_db):
        from src.chat.compact import SUMMARY_ROLE
        from src.chat.model import ModelCallError

        model = ScriptedModel([ModelCallError("quota"), text("still answered", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(100))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi")

        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", SUMMARY_ROLE, "assistant"]
        assert rows[1]["error"] == "quota" and rows[1]["content"] is None
        assert rows[1]["compacted"]["trigger"] == "auto"
        assert "time_ms" in rows[1] and rows[1]["transcript"]["output"] is None
        # The model still saw the whole history, and the failed row not at all.
        assert [m["content"] for m in model.requests[1]["messages"][1:]] == ["hi"]
        assert model_view(rows[1]) is None

        # A reply with no text is a failure too.
        model = ScriptedModel([text(None, prompt=1, completion=1), text("ok", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(100))
        bot.send(conversation_id, "again")
        failed = store.messages(conversation_id)[4]
        assert failed["role"] == SUMMARY_ROLE and failed["error"] == "the model wrote no summary"

    def test_compact_on_request_and_its_refusals(self, isolated_db):
        from src.chat.compact import COMPACT_COMMAND, SUMMARY_ROLE, TRIGGER_MANUAL

        model = ScriptedModel([text("answer", prompt=1, completion=1), text("S", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        with pytest.raises(NothingToCompactError):
            bot.compact(conversation_id)
        with pytest.raises(UnknownConversationError):
            bot.compact("nope")

        bot.send(conversation_id, "hi")
        assert bot.compact(conversation_id, language="zh") is True
        rows = store.messages(conversation_id)
        # The command is the user's own line; the summary follows it and
        # stands for the rows before it, never for the command.
        assert roles(conversation_id) == ["user", "assistant", "user", SUMMARY_ROLE]
        assert rows[2]["content"] == COMPACT_COMMAND
        assert rows[3]["compacted"] == {"trigger": TRIGGER_MANUAL, "first_seq": 1, "last_seq": 2,
                                        "tokens_before": rows[3]["compacted"]["tokens_before"]}
        summary_request = model.requests[1]["messages"]
        assert not any(COMPACT_COMMAND in str(m.get("content")) for m in summary_request)
        # The instruction names the chosen language.
        assert "Simplified Chinese" in summary_request[-1]["content"]
        assert store.get_conversation(conversation_id)["total_tokens"] == 4
        assert store.get_conversation(conversation_id)["user_input_count"] == 2
        # The model's view starts at the summary: the command line is behind it.
        assert [m["role"] for m in bot._request(conversation_id, "en").conversation] == ["user"]

        # Nothing new since the summary: the model sees the summary row only, which is something.
        bot = ChatHarness(ScriptedModel([text("S2", prompt=1, completion=1)]), limit=self.limit(10_000_000))
        assert bot.compact(conversation_id) is True

    def test_compact_is_refused_while_a_call_waits(self, isolated_db):
        model = ScriptedModel([call("delete_run", {"run_id": "q1"})])
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "cancel q1")
        assert store.get_pending(conversation_id)
        with pytest.raises(ConfirmationPendingError):
            bot.compact(conversation_id)

    def test_context_usage_sizes_the_next_request(self, isolated_db):
        # A receipt in a real tokenizer's range: the prompt is some
        # 12,000 characters of instructions and tool menu.
        model = ScriptedModel([text("answer", prompt=3000, completion=5)])
        bot = ChatHarness(model, limit=self.limit(10_000))
        empty = bot.context_usage(None)
        assert empty.conversation_tokens == 0 and empty.system_prompt_tokens > 0 and empty.tools_tokens > 0
        assert empty.calibrated is False

        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi")
        usage = bot.context_usage(conversation_id)
        # Measured: the stored reply's prompt text over its 400 input tokens.
        sent = store.messages(conversation_id)[1]["transcript"]["input"]
        assert usage.calibrated is True
        assert usage.chars_per_token == pytest.approx(len(sent) / 3000)
        assert usage.conversation_tokens > 0
        assert usage.view()["max_tokens"] == 10_000
        with pytest.raises(UnknownConversationError):
            bot.context_usage("nope")

    def test_a_stop_during_the_summary_ends_the_turn_after_it(self, isolated_db):
        from src.chat.compact import SUMMARY_ROLE

        holder: Dict[str, Any] = {}

        class StopDuringSummary(ScriptedModel):
            def complete(self, messages, tools, tool_choice="auto"):
                reply = super().complete(messages, tools, tool_choice)
                holder["bot"].stop(holder["id"])
                return reply

        model = StopDuringSummary([text("S", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(100))
        conversation_id = store.create_conversation()["id"]
        holder.update(bot=bot, id=conversation_id)
        bot.send(conversation_id, "hi")
        assert roles(conversation_id) == ["user", SUMMARY_ROLE, STOPPED_ROLE]
        assert store.messages(conversation_id)[2]["content"] == STOPPED_MESSAGE
        assert len(model.requests) == 1

    def test_a_failed_summary_mid_turn_leaves_the_turn_whole(self, isolated_db):
        """Regression (review 2026-10-13): a failed summary row started a
        turn for the window, so a long turn's next request could open
        on it — and the model, which sees no failed row, got the system
        prompt alone."""
        from src.chat.compact import SUMMARY_ROLE
        from src.chat.model import ModelCallError

        model = ScriptedModel([
            calls(*[(f"c{i}", "list_tickers", {}) for i in range(3)]),
            ModelCallError("quota"),
            text("done", prompt=1, completion=1),
        ])
        bot = ChatHarness(model, limit=self.limit(100))
        # Past the line only once the tool results are in.
        limits = iter([self.limit(10_000_000)(), self.limit(100)(), self.limit(100)(), self.limit(100)()])
        bot._limit = lambda: next(limits)
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "list three times")
        assert roles(conversation_id) == ["user", "assistant", "tool", "tool", "tool", SUMMARY_ROLE, "assistant"]
        # With a window of three rows the failed row must not open it.
        window = trim_history(store.messages(conversation_id)[:6], limit=3)
        assert [m["role"] for m in window][0] == "user"
        # And the loop's own request after the failure held the whole turn.
        sent = model.requests[2]["messages"]
        assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "tool", "tool"]

    def test_a_failed_summary_keeps_the_language_correction(self, isolated_db):
        """Regression (review 2026-10-13): the retry after a wrong-language
        reply dropped its correction line when the summary before it failed."""
        from src.chat.model import ModelCallError

        model = ScriptedModel([
            text(TestReplyLanguage.ENGLISH, prompt=1, completion=1),
            ModelCallError("quota"),
            text(TestReplyLanguage.CHINESE, prompt=1, completion=1),
        ])
        bot = ChatHarness(model, limit=self.limit(100))
        conversation_id = store.create_conversation()["id"]
        # Past the line only from the second call on: the first measure
        # sees a max of 10M, the retry's a max of 100.
        limits = iter([self.limit(10_000_000)(), self.limit(100)(), self.limit(100)(), self.limit(100)()])
        bot._limit = lambda: next(limits)
        bot.send(conversation_id, "how is AAPL?", language="zh")
        retry = model.requests[2]["messages"]
        assert retry[-1]["role"] == "user" and "Simplified Chinese" in retry[-1]["content"]
        assert store.messages(conversation_id)[-1]["content"] == TestReplyLanguage.CHINESE

    def test_a_stop_during_a_requested_summary_is_recorded_as_late(self, isolated_db):
        from src.chat.compact import SUMMARY_ROLE

        holder: Dict[str, Any] = {}

        class StopDuringSummary(ScriptedModel):
            def complete(self, messages, tools, tool_choice="auto"):
                reply = super().complete(messages, tools, tool_choice)
                holder["bot"].stop(holder["id"])
                return reply

        model = StopDuringSummary([text("answer", prompt=1, completion=1), text("S", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hi")
        holder.update(bot=bot, id=conversation_id)
        assert bot.compact(conversation_id) is True
        assert roles(conversation_id)[-2:] == [SUMMARY_ROLE, STOPPED_ROLE]
        assert store.messages(conversation_id)[-1]["content"] == STOPPED_LATE_MESSAGE

    def test_a_summary_row_is_a_turn_start_and_a_user_line_to_the_model(self):
        from src.chat.compact import SUMMARY_PREFACE, SUMMARY_ROLE, after_last_summary

        messages = [
            {"role": "user", "content": "one", "seq": 1}, {"role": "assistant", "content": "a", "seq": 2},
            {"role": SUMMARY_ROLE, "content": "S", "seq": 3},
            {"role": "user", "content": "two", "seq": 4}, {"role": "assistant", "content": "b", "seq": 5},
        ]
        assert after_last_summary(messages) == messages[2:]
        assert trim_history(messages[2:], limit=2) == messages[3:]
        assert trim_history(messages[2:], limit=3) == messages[2:]
        assert model_view(messages[2]) == {"role": "user", "content": f"{SUMMARY_PREFACE}\n\nS"}
        failed = {"role": SUMMARY_ROLE, "content": None, "error": "x", "seq": 6}
        assert after_last_summary(messages + [failed]) == messages[2:] + [failed]
        assert model_view(failed) is None


class TestSideQuestion:
    """/btw (src/chat/side_question.py): the question and its answer are
    stored and flagged, the one call sees the conversation but no
    tools, and no later request, measure or summary carries the rows."""

    @staticmethod
    def limit(max_tokens):
        return TestCompaction.limit(max_tokens)

    def test_the_rows_are_stored_flagged_and_left_out_of_later_requests(self, isolated_db):
        from src.chat.side_question import SIDE_QUESTION_INSTRUCTION, SIDE_QUESTION_KEY

        model = ScriptedModel([
            text("first answer", prompt=10, completion=2),
            text("Tier 2 is the deep analysis.", prompt=20, completion=3),
            text("second answer", prompt=10, completion=2),
        ])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hello")
        before = bot.context_usage(conversation_id).used_tokens

        assert bot.side_question(conversation_id, "btw what is tier 2?", language="en") is True
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "user", "assistant"]
        assert rows[2]["content"] == "btw what is tier 2?" and rows[2][SIDE_QUESTION_KEY] is True
        assert rows[3]["content"] == "Tier 2 is the deep analysis." and rows[3][SIDE_QUESTION_KEY] is True
        assert rows[3]["usage"] == {"input_tokens": 20, "output_tokens": 3}
        assert rows[3]["transcript"]["output"] == "Tier 2 is the deep analysis."
        # The side call: the standing instructions, the conversation so
        # far, the question last under its instruction, and no tools.
        side_request = model.requests[1]
        assert "## What the app does" in side_request["messages"][0]["content"]
        assert [m["content"] for m in side_request["messages"][1:-1]] == ["hello", "first answer"]
        assert side_request["messages"][-1] == {
            "role": "user", "content": f"{SIDE_QUESTION_INSTRUCTION}\n\nbtw what is tier 2?",
        }
        assert side_request["tools"] == []
        # The exchange counts toward what the conversation cost, and as
        # one of the user's inputs, but takes no context.
        facts = store.get_conversation(conversation_id)
        assert facts["total_tokens"] == 35 and facts["user_input_count"] == 2
        assert bot.context_usage(conversation_id).used_tokens == before

        # The next message's request has no trace of it.
        bot.send(conversation_id, "and now?")
        answer_request = model.requests[2]["messages"]
        assert [m["content"] for m in answer_request[1:]] == ["hello", "first answer", "and now?"]
        assert not any("what is tier 2" in str(m.get("content")).lower() for m in answer_request)
        assert [m["role"] for m in bot._request(conversation_id, "en").history] == ["user", "assistant", "user", "assistant"]

    def test_the_side_call_sees_tool_calls_as_text_and_works_on_an_empty_conversation(self, isolated_db):
        model = ScriptedModel([
            call("list_tickers", {}), text("You have AAPL.", prompt=1, completion=1),
            text("A ticker is a stock's symbol.", prompt=1, completion=1),
        ])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "what do I have?")
        bot.side_question(conversation_id, "what is a ticker?")
        side_request = model.requests[2]["messages"]
        assert all(m["role"] != "tool" for m in side_request)
        assert not any(m.get("tool_calls") for m in side_request)
        assert any("[Called list_tickers" in str(m["content"]) for m in side_request)
        assert any("[Result of list_tickers]" in str(m["content"]) for m in side_request)

        # With nothing said yet, the instructions and the question alone;
        # the question names the conversation like any first line.
        fresh = store.create_conversation()["id"]
        bot = ChatHarness(ScriptedModel([text("Hi!", prompt=1, completion=1)]), limit=self.limit(10_000_000))
        assert bot.side_question(fresh, "anyone there?") is True
        assert [m["role"] for m in bot._model.requests[0]["messages"]] == ["system", "user"]
        assert store.get_conversation(fresh)["title"] == "anyone there?"
        assert bot._request(fresh, "en").history == []

    def test_refusals_and_a_failed_call(self, isolated_db):
        from src.chat.side_question import SIDE_QUESTION_KEY

        bot = ChatHarness(ScriptedModel([]), limit=self.limit(10_000_000))
        with pytest.raises(UnknownConversationError):
            bot.side_question("nope", "hi")

        model = ScriptedModel([call("delete_run", {"run_id": "q1"})])
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "cancel q1")
        assert store.get_pending(conversation_id)
        with pytest.raises(ConfirmationPendingError):
            bot.side_question(conversation_id, "which run is that?")
        assert roles(conversation_id) == ["user", "assistant"]

        # A failed call is a flagged reply carrying the error; the
        # question stays stored, and neither row reaches the model.
        failing = ScriptedModel([RuntimeError("quota")])
        bot = ChatHarness(failing, limit=self.limit(10_000_000))
        fresh = store.create_conversation()["id"]
        assert bot.side_question(fresh, "hm?") is False
        rows = store.messages(fresh)
        assert roles(fresh) == ["user", "assistant"]
        assert rows[1]["error"] == "quota" and rows[1][SIDE_QUESTION_KEY] is True
        assert rows[1]["content"].startswith("The model call failed")
        assert bot._request(fresh, "en").history == []

    def test_a_summary_never_covers_a_side_question(self, isolated_db):
        from src.chat.compact import SUMMARY_ROLE

        model = ScriptedModel([text("first answer", prompt=100, completion=5), text("An aside.", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        bot.send(conversation_id, "hello")
        bot.side_question(conversation_id, "secret aside")

        # A max the standing instructions alone pass: the next turn
        # summarizes first, and the summary skips the aside.
        model = ScriptedModel([
            text("SUMMARY: hello was answered.", prompt=120, completion=10),
            text("second answer", prompt=50, completion=5),
        ])
        bot = ChatHarness(model, limit=self.limit(100))
        bot.send(conversation_id, "and now?")
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", "user", "assistant", "user", SUMMARY_ROLE, "assistant"]
        summary_request = model.requests[0]["messages"]
        assert not any("secret aside" in str(m["content"]) or "An aside" in str(m["content"]) for m in summary_request)
        assert [m["content"] for m in summary_request[1:-1]] == ["hello", "first answer", "and now?"]
        assert rows[5]["compacted"]["first_seq"] == 1 and rows[5]["compacted"]["last_seq"] == 5

    def test_a_stop_during_a_side_question_is_late_and_hidden_from_the_model(self, isolated_db):
        from src.chat.side_question import SIDE_QUESTION_KEY

        holder: Dict[str, Any] = {}

        class StopDuringCall(ScriptedModel):
            def complete(self, messages, tools, tool_choice="auto"):
                reply = super().complete(messages, tools, tool_choice)
                holder["bot"].stop(holder["id"])
                return reply

        model = StopDuringCall([text("An aside.", prompt=1, completion=1), text("answer", prompt=1, completion=1)])
        bot = ChatHarness(model, limit=self.limit(10_000_000))
        conversation_id = store.create_conversation()["id"]
        holder.update(bot=bot, id=conversation_id)
        assert bot.side_question(conversation_id, "psst") is True
        rows = store.messages(conversation_id)
        assert roles(conversation_id) == ["user", "assistant", STOPPED_ROLE]
        assert rows[2]["content"] == STOPPED_LATE_MESSAGE and rows[2][SIDE_QUESTION_KEY] is True
        # The stopped row went with the aside: the model sees none of the three.
        assert bot._request(conversation_id, "en").history == []
