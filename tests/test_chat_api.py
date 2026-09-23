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
from src.chatbot.harness import ChatHarness
from src.chatbot.model import ModelReply
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
    return ModelReply(content=content, prompt_tokens=20, completion_tokens=4, model="fake")


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
        assert (listed[0]["question_count"], listed[0]["total_tokens"], listed[0]["last_question_at"]) == (0, 0, None)

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
        assert rows[2]["tool_name"] == "list_tickers"
        assert rows[2]["result"] == {"items": ["AAPL"]}
        assert rows[2]["result_chars"] == len('{"items": ["AAPL"]}')
        assert isinstance(rows[2]["duration_ms"], int)
        assert rows[3]["text"] == "You ran AAPL."
        assert rows[3]["usage"] == {"prompt_tokens": 20, "completion_tokens": 4}
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
        assert body["stage"] == "chat" and body["seq"] == 2
        assert body["prompt"].startswith("=== system ===")
        assert "=== user ===\nruns?" in body["prompt"]
        assert body["reply"].startswith("[tool calls]")
        assert body["temperature"] == 0.0 and isinstance(body["duration_ms"], int)

        last = client.get(f"/chat/conversations/{conversation_id}/messages/4/transcript").json()
        assert last["reply"] == "Nothing yet."
        assert last["prompt_tokens"] == 20 and last["completion_tokens"] == 4 and last["model"] == "fake"
        # User lines and tool results hold no model call.
        assert client.get(f"/chat/conversations/{conversation_id}/messages/1/transcript").status_code == 404
        assert client.get(f"/chat/conversations/{conversation_id}/messages/3/transcript").status_code == 404
        assert client.get(f"/chat/conversations/{conversation_id}/messages/99/transcript").status_code == 404
        assert client.get("/chat/conversations/nope/messages/1/transcript").status_code == 404

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
        scripted([call("delete_run", {"task_id": "q1"}), text("Cancelled.")])
        conversation_id = client.post("/chat/conversations").json()["id"]

        held = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "cancel it"}).json()
        pending = held["pending"]["calls"][0]
        assert pending["name"] == "delete_run"
        assert pending["arguments"] == {"task_id": "q1"}
        assert pending["facts"]["run"]["stock_code"] == "MSFT"

        again = client.post(f"/chat/conversations/{conversation_id}/messages", json={"text": "hurry"})
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "confirmation_pending"

        done = client.post(f"/chat/conversations/{conversation_id}/confirm", json={"approved": True}).json()
        assert done["pending"] is None
        assert done["messages"][2]["approved"] is True
        assert done["messages"][2]["result"]["deleted"] is True
        assert done["messages"][3]["text"] == "Cancelled."
        assert not history.run_exists("q1")

        nothing = client.post(f"/chat/conversations/{conversation_id}/confirm", json={"approved": True})
        assert nothing.status_code == 409
        assert nothing.json()["detail"]["code"] == "nothing_pending"
        assert client.post("/chat/conversations/nope/confirm", json={"approved": True}).status_code == 404
