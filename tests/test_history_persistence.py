"""Tests for encrypted history persistence."""

from __future__ import annotations

import pytest

from agentirc.history import HistoryStore


@pytest.fixture
def fernet_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


class TestHistoryPersistence:
    def test_save_and_load(self, tmp_path, fernet_key):
        store = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        store.add("#test", "alice", "user", "hello")
        store.add("#test", "alice", "assistant", "hi there")

        store2 = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        msgs = store2.get("#test", "alice")
        assert len(msgs) == 3
        assert msgs[1]["content"] == "hello"
        assert msgs[2]["content"] == "hi there"

    def test_wrong_key_starts_empty(self, tmp_path, fernet_key):
        from cryptography.fernet import Fernet

        store = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        store.add("#test", "alice", "user", "secret")

        wrong_key = Fernet.generate_key().decode()
        store2 = HistoryStore(store_path=str(tmp_path), encryption_key=wrong_key)
        msgs = store2.get("#test", "alice")
        assert len(msgs) == 1  # only system prompt
        assert msgs[0]["role"] == "system"

    def test_no_persistence_without_key(self, tmp_path):
        store = HistoryStore()
        store.add("#test", "alice", "user", "hello")
        # No file created
        assert not list(tmp_path.iterdir())

    def test_clear_all_persists(self, tmp_path, fernet_key):
        store = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        store.add("#test", "alice", "user", "hello")
        store.clear_all()

        store2 = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        msgs = store2.get("#test", "alice")
        assert len(msgs) == 1  # fresh system prompt

    def test_multi_room_multi_user(self, tmp_path, fernet_key):
        store = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        store.add("#room1", "alice", "user", "msg1")
        store.add("#room2", "bob", "user", "msg2")

        store2 = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        assert store2.get("#room1", "alice")[1]["content"] == "msg1"
        assert store2.get("#room2", "bob")[1]["content"] == "msg2"

    def test_locations_persist(self, tmp_path, fernet_key):
        store = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        store.set_location("alice", "New York")

        store2 = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        assert store2.get_location("alice") == "New York"

    def test_locations_survive_clear_all(self, tmp_path, fernet_key):
        store = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        store.set_location("alice", "Tokyo")
        store.clear_all()

        store2 = HistoryStore(store_path=str(tmp_path), encryption_key=fernet_key)
        assert store2.get_location("alice") == "Tokyo"
