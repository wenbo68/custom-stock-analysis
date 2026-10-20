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
        # The same facts for one conversation and for the whole list.
        assert {k: store.get_conversation(conversation_id)[k] for k in facts} == facts
        # Only the user's own lines are questions; bot replies and tool rows are not.
        assert facts["user_input_count"] == 2
        # Every model call's prompt and completion tokens together; missing counts read as 0.
        assert facts["total_tokens"] == 4500
        # The last question's time, not the conversation's last touch.
        second = store.messages(conversation_id)[-1]
        assert facts["ended_at"] == second["created_at"]
        assert store.get_conversation(conversation_id)["user_input_count"] == 2

    def test_token_counts_are_columns_filled_on_write(self, isolated_db):
        """The sidebar's token total is summed in SQL (2026-10-10), so
        every row carries its counts as columns: the usage's numbers on
        a bot reply, 0 everywhere else, never NULL."""
        from src.storage import ChatMessageRecord

        conversation_id = store.create_conversation()["id"]
        store.append_message(conversation_id, {"role": "user", "content": "q"})
        store.append_message(conversation_id, {
            "role": "assistant", "content": "a", "usage": {"input_tokens": 30, "output_tokens": None},
        })
        store.append_message(conversation_id, {"role": "assistant", "content": "b"})
        with isolated_db.get_session() as session:
            rows = session.query(ChatMessageRecord).order_by(ChatMessageRecord.seq).all()
            assert [(r.input_tokens, r.output_tokens) for r in rows] == [(0, 0), (30, 0), (0, 0)]

    def test_timestamps_carry_the_utc_offset(self, isolated_db):
        """Regression (2026-10-10): times were rendered naive
        (``2026-10-10T12:00:00``) although they are UTC, so the model
        could misplace them next to the prompt's offset-bearing clock."""
        conversation_id = store.create_conversation()["id"]
        store.append_message(conversation_id, {"role": "user", "content": "q"})
        conversation = store.get_conversation(conversation_id)
        assert conversation["created_at"].endswith("+00:00")
        assert conversation["updated_at"].endswith("+00:00")
        assert conversation["ended_at"].endswith("+00:00")
        assert conversation["messages"][0]["created_at"].endswith("+00:00")
        assert store.list_conversations()[0]["ended_at"] == conversation["ended_at"]

    def test_long_first_message_is_cut_for_the_title(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        store.append_message(conversation_id, {"role": "user", "content": "x" * 200})
        title = store.get_conversation(conversation_id)["title"]
        assert len(title) == store.TITLE_MAX_CHARS
        assert title.endswith("…")

    def test_conversations_list_the_one_the_user_last_wrote_in_first(self, isolated_db):
        first = store.create_conversation()["id"]
        second = store.create_conversation()["id"]
        store.append_message(first, {"role": "user", "content": "later"})
        assert [c["id"] for c in store.list_conversations()] == [first, second]
        store.append_message(second, {"role": "user", "content": "latest"})
        assert [c["id"] for c in store.list_conversations()] == [second, first]
        # A reply landing in the first does not lift it: only the user's
        # own lines order the list (owner request 2026-10-15).
        store.append_message(first, {"role": "assistant", "content": "answer"})
        assert [c["id"] for c in store.list_conversations()] == [second, first]


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


class TestOldDatabases:
    """A database written before the token columns existed (2026-10-10)
    gains them at startup and has them filled from the stored usage."""

    @staticmethod
    def _old_shape_database(path):
        import json
        import sqlite3

        connection = sqlite3.connect(path)
        connection.executescript("""
            CREATE TABLE chat_conversations (
                id VARCHAR(64) NOT NULL PRIMARY KEY, title VARCHAR(120),
                created_at DATETIME, updated_at DATETIME, pending_json TEXT
            );
            CREATE TABLE chat_messages (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                conversation_id VARCHAR(64) NOT NULL, seq INTEGER NOT NULL,
                role VARCHAR(16) NOT NULL, content_json TEXT NOT NULL, created_at DATETIME
            );
        """)
        connection.execute(
            "INSERT INTO chat_conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("old", "old talk", "2026-09-01 10:00:00", "2026-09-01 10:05:00"),
        )
        rows = [
            ("old", 1, "user", {"role": "user", "content": "q"}, "2026-09-01 10:00:00"),
            ("old", 2, "assistant", {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}],
                                     "usage": {"input_tokens": 1200, "output_tokens": 40}}, "2026-09-01 10:00:01"),
            ("old", 3, "tool", {"role": "tool", "tool_call_id": "c1", "content": "{}"}, "2026-09-01 10:00:02"),
            ("old", 4, "assistant", {"role": "assistant", "content": "a"}, "2026-09-01 10:00:03"),
            ("old", 5, "assistant", {"role": "assistant", "content": "b",
                                     "usage": {"input_tokens": 1300, "output_tokens": None}}, "2026-09-01 10:00:04"),
        ]
        connection.executemany(
            "INSERT INTO chat_messages (conversation_id, seq, role, content_json, created_at) VALUES (?, ?, ?, ?, ?)",
            [(c, seq, role, json.dumps(body), when) for c, seq, role, body, when in rows],
        )
        connection.commit()
        connection.close()

    def test_old_shape_file_gains_the_columns_and_is_backfilled(self, tmp_path):
        from sqlalchemy import inspect

        from src.config import Config
        from src.storage import ChatMessageRecord, DatabaseManager

        path = tmp_path / "old_chat.db"
        self._old_shape_database(str(path))
        old_database_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        try:
            db = DatabaseManager.get_instance()
            columns = {c["name"] for c in inspect(db._engine).get_columns("chat_messages")}
            assert {"input_tokens", "output_tokens"} <= columns
            with db.get_session() as session:
                rows = session.query(ChatMessageRecord).order_by(ChatMessageRecord.seq).all()
                assert all(r.input_tokens is None and r.output_tokens is None for r in rows)

            assert store.backfill_tokens() == 5
            with db.get_session() as session:
                rows = session.query(ChatMessageRecord).order_by(ChatMessageRecord.seq).all()
                assert [(r.input_tokens, r.output_tokens) for r in rows] == [
                    (0, 0), (1200, 40), (0, 0), (0, 0), (1300, 0),
                ]
            # Already filled rows are left alone: the backfill is a one-off.
            assert store.backfill_tokens() == 0
            facts = store.list_conversations()[0]
            assert (facts["message_count"], facts["user_input_count"], facts["total_tokens"]) == (5, 1, 2540)
            assert facts["ended_at"] == "2026-09-01T10:00:00+00:00"
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            if old_database_path is None:
                os.environ.pop("DATABASE_PATH", None)
            else:
                os.environ["DATABASE_PATH"] = old_database_path

    def test_app_startup_backfills(self, tmp_path):
        from fastapi.testclient import TestClient

        from src.config import Config
        from src.storage import ChatMessageRecord, DatabaseManager

        path = tmp_path / "old_chat_startup.db"
        self._old_shape_database(str(path))
        old_database_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        try:
            from api.app import create_app

            with TestClient(create_app()) as client:
                assert client.get("/api/health").status_code == 200
            with DatabaseManager.get_instance().get_session() as session:
                rows = session.query(ChatMessageRecord).order_by(ChatMessageRecord.seq).all()
                assert [r.input_tokens for r in rows] == [0, 1200, 0, 0, 1300]
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            if old_database_path is None:
                os.environ.pop("DATABASE_PATH", None)
            else:
                os.environ["DATABASE_PATH"] = old_database_path


class TestRunWatches:
    def test_add_list_remove(self, isolated_db):
        first = store.create_conversation()["id"]
        second = store.create_conversation()["id"]
        store.add_watch(first, "r1", "en")
        store.add_watch(first, "r1", "zh")  # the same run again: not added twice
        store.add_watch(first, "r2", "ko")
        store.add_watch(second, "r1", "en")

        assert [(w["run_id"], w["language"]) for w in store.watches(first)] == [("r1", "en"), ("r2", "ko")]
        assert store.conversations_watching("r1") == [first, second]
        assert sorted(store.conversations_with_watches()) == sorted([first, second])

        assert store.remove_watch(first, "r1") is True
        assert store.remove_watch(first, "r1") is False
        assert [w["run_id"] for w in store.watches(first)] == ["r2"]
        assert store.conversations_watching("r1") == [second]

    def test_a_notice_row_drops_its_watch_in_the_same_commit(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        store.add_watch(conversation_id, "r2", "en")
        store.append_message(conversation_id, {"role": "notice", "content": "[Run notice] r1 ended."}, drop_watch="r1")
        assert [w["run_id"] for w in store.watches(conversation_id)] == ["r2"]
        assert [m["role"] for m in store.messages(conversation_id)] == ["notice"]
        # A notice sets off a turn like the user's own line, so the
        # sidebar's turn count and last-turn time take it in (owner
        # decision 2026-10-20).
        facts = store.get_conversation(conversation_id)
        assert facts["user_input_count"] == 1
        assert facts["ended_at"] == store.messages(conversation_id)[0]["created_at"]

    def test_deleting_the_conversation_drops_its_watches(self, isolated_db):
        conversation_id = store.create_conversation()["id"]
        store.add_watch(conversation_id, "r1", "en")
        assert store.delete_conversation(conversation_id) is True
        assert store.conversations_watching("r1") == []

