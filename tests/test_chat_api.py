# -*- coding: utf-8 -*-
"""Offline tests for the chat API (api/v1/endpoints/chat.py) on a
scripted model."""
from __future__ import annotations

import json
import os
from typing import List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import chat
from src.chat.harness import ChatHarness
from src.chat.model import ModelReply
from src.tiered_analysis import history


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


class ScriptedModel:
    def __init__(self, replies: List[ModelReply]) -> None:
        self.replies = list(replies)

    def complete(self, messages, tools):
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

        def complete(messages, tools):
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
