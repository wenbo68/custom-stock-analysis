# -*- coding: utf-8 -*-
"""Offline tests for the chat API (api/v1/endpoints/chat.py) on a
scripted model."""
from __future__ import annotations

import json
import os
import threading
from typing import List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import chat
from src.chat.harness import ChatHarness
from src.chat.model import ModelReply
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
    os.environ["DATABASE_PATH"] = str(tmp_path / "chat_api.db")
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
    def __init__(self, replies: List[ModelReply]) -> None:
        self.replies = list(replies)
        #: Cleared by a test that wants the model call to block.
        self.release = threading.Event()
        self.release.set()
        self.asked = threading.Event()
        #: Every request's messages, in order.
        self.requests: List[list] = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.asked.set()
        self.release.wait(timeout=5)
        self.requests.append(messages)
        return self.replies.pop(0)


def text(content):
    return ModelReply(content=content, input_tokens=20, output_tokens=4, llm="fake")


def call(name, args, call_id="c1"):
    return ModelReply(content=None, tool_calls=[{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }])


@pytest.fixture()
def scripted(monkeypatch):
    """Install a harness on the given replies: `scripted([...])`."""
    def install(replies):
        model = ScriptedModel(replies)
        monkeypatch.setattr(chat, "harness", ChatHarness(model))
        return model
    return install


@pytest.fixture()
def client(isolated_db, monkeypatch):
    monkeypatch.setenv("MAIN_LLM", "gemini/test-model")
    app = FastAPI()
    app.include_router(chat.router, prefix="/chat")
    return TestClient(app)


class TestConversations:
    def test_create_list_get_delete(self, client, scripted):
        scripted([])
        created = client.post("/chat/conversations")
        assert created.status_code == 201
        body = created.json()
        assert body["messages"] == [] and body["pending"] is None and body["title"] is None

        listed = client.get("/chat/conversations").json()["items"]
        assert [c["id"] for c in listed] == [body["id"]]
        assert (listed[0]["user_input_count"], listed[0]["total_tokens"], listed[0]["ended_at"]) == (0, 0, None)

        assert client.get(f"/chat/conversations/{body['id']}").status_code == 200
        assert client.get("/chat/conversations/nope").status_code == 404

        assert client.delete(f"/chat/conversations/{body['id']}").json() == {"id": body["id"]}
        assert client.delete(f"/chat/conversations/{body['id']}").status_code == 404

    def test_delete_during_a_turn_is_busy_then_works(self, client, scripted):
        """Regression (2026-10-10): a delete under a running turn used to
        make the turn fail with a 500. It is now refused as busy (409);
        once the turn is over the delete goes through and the harness
        forgets the conversation's lock."""
        model = scripted([text("slow")])
        model.release.clear()
        conversation_id = client.post("/chat/conversations").json()["id"]
        outcome = {}

        def send():
            outcome["response"] = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hi"})

        worker = threading.Thread(target=send)
        worker.start()
        try:
            assert model.asked.wait(timeout=COLD_TURN_WAIT)
            refused = client.delete(f"/chat/conversations/{conversation_id}")
            assert refused.status_code == 409
            assert refused.json()["detail"]["code"] == "busy"
        finally:
            model.release.set()
            worker.join(timeout=5)
        assert outcome["response"].status_code == 200
        assert [m["role"] for m in outcome["response"].json()["messages"]] == ["user", "assistant"]

        assert client.delete(f"/chat/conversations/{conversation_id}").status_code == 200
        assert conversation_id not in chat.harness._locks
        assert client.get(f"/chat/conversations/{conversation_id}").status_code == 404
        assert client.delete(f"/chat/conversations/{conversation_id}").status_code == 404


class TestMessages:
    def test_send_returns_the_whole_conversation(self, client, scripted):
        history.create_run("t1", "AAPL", inputs={"tier": 1}, status="queued")
        scripted([call("list_tickers", {}), text("You ran AAPL.")])
        conversation_id = client.post("/chat/conversations").json()["id"]

        answer = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "what did I run?"})
        assert answer.status_code == 200
        body = answer.json()
        assert body["title"] == "what did I run?"
        rows = body["messages"]
        assert [r["role"] for r in rows] == ["user", "assistant", "tool", "assistant"]
        assert rows[0]["text"] == "what did I run?"
        assert rows[1]["tool_calls"] == [{"id": "c1", "name": "list_tickers", "arguments": {}}]
        assert rows[2]["name"] == "list_tickers"
        assert rows[2]["output"] == {"items": ["AAPL"]}
        assert rows[2]["output_chars"] == len('{"items": ["AAPL"]}')
        assert isinstance(rows[2]["time_ms"], int)
        # The tool row carries the inputs with defaults filled in (2026-09-24).
        assert rows[2]["input"] == {}
        assert rows[3]["text"] == "You ran AAPL."
        assert rows[3]["usage"] == {"input_tokens": 20, "output_tokens": 4}
        assert body["pending"] is None
        # The transcript text stays out of the conversation; only its size rides along.
        assert rows[3]["transcript_chars"] > 0 and "transcript" not in rows[3]
        assert rows[0].get("transcript_chars") is None

    def test_a_reply_transcript_reads_like_a_run_call(self, client, scripted):
        scripted([call("list_tickers", {}), text("Nothing yet.")])
        conversation_id = client.post("/chat/conversations").json()["id"]
        client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "runs?"})

        first = client.get(f"/chat/conversations/{conversation_id}/messages/2/transcript")
        assert first.status_code == 200
        body = first.json()
        assert body["stage"] == "chat" and body["call_number"] == 2
        assert body["input"].startswith("=== system ===")
        assert "=== user ===\nruns?" in body["input"]
        assert body["output"].startswith("[tool calls]")
        assert body["temperature"] == 0.0 and isinstance(body["time_ms"], int)

        last = client.get(f"/chat/conversations/{conversation_id}/messages/4/transcript").json()
        assert last["output"] == "Nothing yet."
        assert last["input_tokens"] == 20 and last["output_tokens"] == 4 and last["llm"] == "fake"
        # User lines and tool results hold no model call.
        assert client.get(f"/chat/conversations/{conversation_id}/messages/1/transcript").status_code == 404
        assert client.get(f"/chat/conversations/{conversation_id}/messages/3/transcript").status_code == 404
        assert client.get(f"/chat/conversations/{conversation_id}/messages/99/transcript").status_code == 404
        assert client.get("/chat/conversations/nope/messages/1/transcript").status_code == 404

    def test_language_reaches_the_prompt_and_the_retry(self, client, scripted):
        english = "The latest run on AAPL is bullish with a score of 7.2 out of 10."
        model = scripted([text(english), text("苹果最近一次分析的展望是看涨，评分 7.2。")])
        model.requests = []
        original = model.complete

        def complete(messages, tools, tool_choice="auto"):
            model.requests.append(messages)
            return original(messages, tools)

        model.complete = complete
        conversation_id = client.post("/chat/conversations").json()["id"]
        body = client.post(f"/chat/conversations/{conversation_id}/messages",
                           json={"text": "AAPL 怎么样？", "language": "zh"}).json()
        assert "Reply in Simplified Chinese" in model.requests[0][0]["content"]
        assert [m["role"] for m in body["messages"]] == ["user", "assistant", "assistant"]
        assert body["messages"][1]["notice"] == "wrong_language"
        assert body["messages"][2]["notice"] is None

    def test_an_unknown_language_is_rejected(self, client, scripted):
        scripted([text("hi")])
        conversation_id = client.post("/chat/conversations").json()["id"]
        response = client.post(f"/chat/conversations/{conversation_id}/messages",
                               json={"text": "hi", "language": "fr"})
        assert response.status_code == 422

    def test_blank_message_is_rejected(self, client, scripted):
        scripted([])
        conversation_id = client.post("/chat/conversations").json()["id"]
        assert client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "   "}).status_code == 422
        assert client.post("/chat/conversations/nope/messages", json={"text": "hi"}).status_code == 404

    def test_no_model_is_a_400(self, client, scripted, monkeypatch):
        scripted([])
        monkeypatch.delenv("MAIN_LLM", raising=False)
        conversation_id = client.post("/chat/conversations").json()["id"]
        refused = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hi"})
        assert refused.status_code == 400
        assert refused.json()["detail"]["error"] == "llm_not_configured"


class TestConfirmation:
    def test_pending_action_then_yes(self, client, scripted):
        history.create_run("q1", "MSFT", inputs={"tier": 2}, status="queued")
        scripted([call("delete_run", {"run_id": "q1"}), text("Cancelled.")])
        conversation_id = client.post("/chat/conversations").json()["id"]

        held = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "cancel it"}).json()
        pending = held["pending"]["calls"][0]
        assert pending["name"] == "delete_run"
        assert pending["input"] == {"run_id": "q1"}
        assert pending["facts"]["run"]["ticker"] == "MSFT"

        again = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hurry"})
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "confirmation_pending"

        done = client.post(f"/chat/conversations/{conversation_id}/confirm", json={"approved": True}).json()
        assert done["pending"] is None
        assert done["messages"][2]["approved"] is True
        assert done["messages"][2]["output"]["deleted"] is True
        assert done["messages"][3]["text"] == "Cancelled."
        assert not history.run_exists("q1")

        nothing = client.post(f"/chat/conversations/{conversation_id}/confirm", json={"approved": True})
        assert nothing.status_code == 409
        assert nothing.json()["detail"]["code"] == "nothing_pending"
        assert client.post("/chat/conversations/nope/confirm", json={"approved": True}).status_code == 404


class TestStop:
    def test_stop_during_a_turn_ends_it_with_a_stopped_row(self, client, scripted):
        """The page's stop button (2026-10-12): the stop request answers
        at once; the turn's own request waits for the step in flight,
        then returns the stopped conversation — the reply, its calls
        answered as stopped, and the `stopped` line last."""
        model = scripted([call("list_tickers", {})])
        model.release.clear()
        conversation_id = client.post("/chat/conversations").json()["id"]
        outcome = {}

        def send():
            outcome["response"] = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hi"})

        worker = threading.Thread(target=send)
        worker.start()
        try:
            assert model.asked.wait(timeout=COLD_TURN_WAIT)
            stopped = client.post(f"/chat/conversations/{conversation_id}/stop")
            assert stopped.status_code == 200
            assert stopped.json() == {"id": conversation_id, "stopped": True}
            # The turn waits for the step in flight.
            worker.join(timeout=0.5)
            assert worker.is_alive()
        finally:
            model.release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert outcome["response"].status_code == 200
        messages = outcome["response"].json()["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant", "tool", "stopped"]
        assert messages[2]["output"]["error"] == "stopped"
        assert messages[3]["text"].startswith("[The user stopped this reply")
        # The page takes the server's word on whether a step would have followed.
        assert messages[3]["late"] is False
        assert client.get(f"/chat/conversations/{conversation_id}").json()["user_input_count"] == 1

    def test_stop_with_nothing_running_is_false_and_unknown_is_404(self, client, scripted):
        scripted([])
        conversation_id = client.post("/chat/conversations").json()["id"]
        assert client.post(f"/chat/conversations/{conversation_id}/stop").json() == {"id": conversation_id, "stopped": False}
        assert client.post("/chat/conversations/nope/stop").status_code == 404


class TestContextAndCompact:
    def test_context_with_and_without_a_conversation(self, client, scripted, monkeypatch):
        from src.chat import context

        monkeypatch.setenv(context.CONTEXT_WINDOW_ENV, "50000")
        scripted([ModelReply(content="answer", input_tokens=3000, output_tokens=4, llm="fake")])
        empty = client.get("/chat/context")
        assert empty.status_code == 200
        body = empty.json()
        assert (body["llm"], body["source"], body["window"], body["max_tokens"]) == ("gemini/test-model", "env", 50_000, 25_000)
        assert body["conversation_tokens"] == 0 and body["used_tokens"] > 0
        assert body["compact_at_tokens"] == 25_000 * 85 // 100
        assert "spent_tokens" not in body and isinstance(body["percent"], float)

        conversation_id = client.post("/chat/conversations").json()["id"]
        client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hi"})
        sized = client.get("/chat/context", params={"conversation_id": conversation_id, "language": "ko"}).json()
        assert sized["conversation_tokens"] > 0 and sized["calibrated"] is True
        assert client.get("/chat/context", params={"conversation_id": "nope"}).status_code == 404
        assert client.get("/chat/context", params={"language": "xx"}).status_code == 422
        assert client.get("/chat/context", params={"page": 2}).status_code == 422

    def test_compact_stores_a_summary_step_the_page_can_show(self, client, scripted):
        scripted([text("answer"), text("the summary")])
        conversation_id = client.post("/chat/conversations").json()["id"]
        refused = client.post(f"/chat/conversations/{conversation_id}/compact", json={})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "nothing_to_compact"

        client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hi"})
        compacted = client.post(f"/chat/conversations/{conversation_id}/compact", json={"language": "en"})
        assert compacted.status_code == 200
        rows = compacted.json()["messages"]
        assert [m["role"] for m in rows] == ["user", "assistant", "user", "summary"]
        assert rows[2]["text"] == "/compact"
        summary = rows[3]
        assert summary["text"] == "the summary"
        assert summary["compacted"] == {"trigger": "manual", "first_seq": 1, "last_seq": 2, "tokens_before": summary["compacted"]["tokens_before"]}
        assert summary["usage"] == {"input_tokens": 20, "output_tokens": 4}
        assert summary["llm"] == "fake" and summary["error"] is None and summary["transcript_chars"] > 0
        transcript = client.get(f"/chat/conversations/{conversation_id}/messages/4/transcript").json()
        assert transcript["stage"] == "summary" and transcript["output"] == "the summary"
        assert compacted.json()["total_tokens"] == 48
        assert client.post("/chat/conversations/nope/compact", json={}).status_code == 404
        assert client.post(f"/chat/conversations/{conversation_id}/compact", json={"language": "xx"}).status_code == 422

    def test_a_stopped_row_carries_the_servers_late_flag(self):
        from api.v1.endpoints.chat import _message_view
        from src.chat.harness import STOPPED_LATE_MESSAGE, STOPPED_MESSAGE, STOPPED_ROLE

        late = _message_view({"seq": 4, "role": STOPPED_ROLE, "content": STOPPED_LATE_MESSAGE})
        cut = _message_view({"seq": 4, "role": STOPPED_ROLE, "content": STOPPED_MESSAGE})
        assert late["late"] is True and cut["late"] is False
        assert "late" not in _message_view({"seq": 1, "role": "user", "content": "hi"})

    def test_compact_while_a_call_waits_is_refused(self, client, scripted):
        scripted([call("delete_run", {"run_id": "q1"})])
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        conversation_id = client.post("/chat/conversations").json()["id"]
        assert client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "cancel q1"}).json()["pending"]
        refused = client.post(f"/chat/conversations/{conversation_id}/compact", json={})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "confirmation_pending"


class TestSideQuestion:
    def test_side_question_rows_are_flagged_and_the_next_reply_never_sees_them(self, client, scripted):
        model = scripted([text("hello"), text("the aside"), text("again")])
        conversation_id = client.post("/chat/conversations").json()["id"]
        client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hi"})
        asked = client.post(f"/chat/conversations/{conversation_id}/side_question", json={"text": "btw?", "language": "en"})
        assert asked.status_code == 200
        rows = asked.json()["messages"]
        assert [(m["role"], m.get("side_question")) for m in rows] == [
            ("user", None), ("assistant", None), ("user", True), ("assistant", True),
        ]
        assert rows[2]["text"] == "btw?" and rows[3]["text"] == "the aside"
        assert rows[3]["usage"] == {"input_tokens": 20, "output_tokens": 4} and rows[3]["transcript_chars"] > 0
        assert asked.json()["total_tokens"] == 48 and asked.json()["user_input_count"] == 2
        transcript = client.get(f"/chat/conversations/{conversation_id}/messages/4/transcript").json()
        assert transcript["stage"] == "side_question" and transcript["output"] == "the aside"
        assert "btw?" in transcript["input"]

        # /context does not count it, and the next reply is not shown it.
        with_aside = client.get("/chat/context", params={"conversation_id": conversation_id}).json()["used_tokens"]
        client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "more"})
        assert not any("btw?" in str(m.get("content")) or "the aside" in str(m.get("content")) for m in model.requests[-1])
        assert with_aside < client.get("/chat/context", params={"conversation_id": conversation_id}).json()["used_tokens"]

    def test_side_question_refusals(self, client, scripted, monkeypatch):
        scripted([call("delete_run", {"run_id": "q1"})])
        history.create_run("q1", "AAPL", inputs={"tier": 1}, status="queued")
        conversation_id = client.post("/chat/conversations").json()["id"]
        assert client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "cancel q1"}).json()["pending"]
        refused = client.post(f"/chat/conversations/{conversation_id}/side_question", json={"text": "which?"})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "confirmation_pending"
        assert client.post("/chat/conversations/nope/side_question", json={"text": "hi"}).status_code == 404
        assert client.post(f"/chat/conversations/{conversation_id}/side_question", json={"text": "  "}).status_code == 422
        monkeypatch.delenv("MAIN_LLM")
        assert client.post(f"/chat/conversations/{conversation_id}/side_question", json={"text": "hi"}).status_code == 400
