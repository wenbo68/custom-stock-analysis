# -*- coding: utf-8 -*-
"""Offline tests for chat conversations in the database (src/chat/store.py)."""
from __future__ import annotations

import os

import pytest

from src.chat import store


@pytest.fixture()
def isolated_db(tmp_path):
    from src.config import Config
    from src.storage import DatabaseManager

    old_database_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(tmp_path / "chat_store.db")
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


class TestConversations:
    def test_create_list_get_delete(self, isolated_db):
        created = store.create_conversation()
        assert created["title"] is None
        assert created["message_count"] == 0

        listed = store.list_conversations()
        assert [c["id"] for c in listed] == [created["id"]]

        fetched = store.get_conversation(created["id"])
        assert fetched["messages"] == []
        assert fetched["pending"] is None

        assert store.delete_conversation(created["id"]) is True
        assert store.delete_conversation(created["id"]) is False
        assert store.get_conversation(created["id"]) is None
        assert store.conversation_exists(created["id"]) is False

    def test_unknown_conversation_reads_as_none(self, isolated_db):
        assert store.get_conversation("nope") is None
        assert store.get_pending("nope") is None
        with pytest.raises(KeyError):
            store.append_message("nope", {"role": "user", "content": "hi"})


class TestMessages:
    def test_messages_are_numbered_and_the_first_user_line_titles(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        assert store.append_message(conversation_id, {"role": "user", "content": "  show my   NVDA runs "}) == 1
        assert store.append_message(conversation_id, {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "list_runs", "arguments": "{}"}}],
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }) == 2
        assert store.append_message(conversation_id, {
            "role": "tool", "tool_call_id": "c1", "name": "list_runs", "content": "{}",
        }) == 3

        rows = store.messages(conversation_id)
        assert [r["seq"] for r in rows] == [1, 2, 3]
        assert rows[0]["content"] == "  show my   NVDA runs "
        assert rows[1]["tool_calls"][0]["function"]["name"] == "list_runs"
        assert rows[1]["usage"] == {"input_tokens": 10, "output_tokens": 2}
        assert rows[2]["tool_call_id"] == "c1"
        assert all(r["created_at"] for r in rows)

        conversation = store.get_conversation(conversation_id)
        assert conversation["title"] == "show my NVDA runs"
        assert conversation["message_count"] == 3
        assert store.list_conversations()[0]["message_count"] == 3

    def test_history_facts_count_questions_and_sum_tokens(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        empty = store.get_conversation(conversation_id)
        assert (empty["user_input_count"], empty["total_tokens"], empty["ended_at"]) == (0, 0, None)

        store.append_message(conversation_id, {"role": "user", "content": "first"})
        store.append_message(conversation_id, {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "list_runs", "arguments": "{}"}}],
            "usage": {"input_tokens": 3000, "output_tokens": 1000},
        })
        store.append_message(conversation_id, {"role": "tool", "tool_call_id": "c1", "name": "list_runs", "content": "{}"})
        store.append_message(conversation_id, {
            "role": "assistant", "content": "done", "usage": {"input_tokens": 500, "output_tokens": None},
        })
        store.append_message(conversation_id, {"role": "assistant", "content": "no usage at all"})
        store.append_message(conversation_id, {"role": "user", "content": "second"})

        facts = store.list_conversations()[0]
        assert facts["message_count"] == 6
        # Only the user's own lines are questions; bot replies and tool rows are not.
        assert facts["user_input_count"] == 2
        # Every model call's prompt and completion tokens together; missing counts read as 0.
        assert facts["total_tokens"] == 4500
        # The last question's time, not the conversation's last touch.
        second = store.messages(conversation_id)[-1]
        assert facts["ended_at"] == second["created_at"]
        assert store.get_conversation(conversation_id)["user_input_count"] == 2

    def test_long_first_message_is_cut_for_the_title(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        store.append_message(conversation_id, {"role": "user", "content": "x" * 200})
        title = store.get_conversation(conversation_id)["title"]
        assert len(title) == store.TITLE_MAX_CHARS
        assert title.endswith("…")

    def test_conversations_list_most_recently_touched_first(self, isolated_db):
        first = store.create_conversation()["id"]
        second = store.create_conversation()["id"]
        store.append_message(first, {"role": "user", "content": "later"})
        assert [c["id"] for c in store.list_conversations()] == [first, second]


class TestPending:
    def test_pending_round_trips_and_clears(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        held = {"calls": [{"call_id": "c1", "name": "delete_run", "input": {"run_id": "t"}, "facts": {}}],
                "tool_calls": 1}
        store.set_pending(conversation_id, held)
        assert store.get_pending(conversation_id) == held
        assert store.get_conversation(conversation_id)["pending"] == held
        store.set_pending(conversation_id, None)
        assert store.get_pending(conversation_id) is None
