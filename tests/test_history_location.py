"""Tests for per-user location in HistoryStore."""

from __future__ import annotations

from agentirc.history import HistoryStore


class TestHistoryLocation:
    def test_location_appended_to_system_prompt(self):
        store = HistoryStore(personality="a bot")
        store.set_location("alice", "Paris")
        msgs = store.get("#test", "alice")
        assert msgs[0]["role"] == "system"
        assert "The user has indicated they are located in Paris." in msgs[0]["content"]

    def test_no_location_no_suffix(self):
        store = HistoryStore(personality="a bot")
        msgs = store.get("#test", "alice")
        assert "located in" not in msgs[0]["content"]

    def test_clear_location_removes_suffix(self):
        store = HistoryStore(personality="a bot")
        store.set_location("alice", "Paris")
        store.set_location("alice", "")
        msgs = store.get("#test", "alice")
        assert "located in" not in msgs[0]["content"]

    def test_get_location(self):
        store = HistoryStore()
        assert store.get_location("alice") is None
        store.set_location("alice", "London")
        assert store.get_location("alice") == "London"
        store.set_location("alice", "")
        assert store.get_location("alice") is None

    def test_location_in_new_threads(self):
        store = HistoryStore(personality="a bot")
        store.set_location("alice", "Tokyo")
        # Access a new room — should include location
        msgs = store.get("#newroom", "alice")
        assert "The user has indicated they are located in Tokyo." in msgs[0]["content"]

    def test_location_updates_existing_threads(self):
        store = HistoryStore(personality="a bot")
        store.add("#test", "alice", "user", "hello")
        store.set_location("alice", "Berlin")
        msgs = store.get("#test", "alice")
        assert "The user has indicated they are located in Berlin." in msgs[0]["content"]

    def test_location_with_custom_prompt(self):
        store = HistoryStore(personality="a bot")
        store.init_prompt("#test", "alice", custom="You are a pirate.")
        store.set_location("alice", "Caribbean")
        msgs = store.get("#test", "alice")
        assert "pirate" in msgs[0]["content"]
        assert "The user has indicated they are located in Caribbean." in msgs[0]["content"]

    def test_location_with_persona(self):
        store = HistoryStore(personality="a bot")
        store.init_prompt("#test", "alice", persona="a wizard")
        store.set_location("alice", "Hogwarts")
        msgs = store.get("#test", "alice")
        assert "wizard" in msgs[0]["content"]
        assert "The user has indicated they are located in Hogwarts." in msgs[0]["content"]

    def test_clear_all_preserves_locations(self):
        store = HistoryStore(personality="a bot")
        store.set_location("alice", "Seoul")
        store.clear_all()
        assert store.get_location("alice") == "Seoul"
        # New thread should still include location
        msgs = store.get("#test", "alice")
        assert "The user has indicated they are located in Seoul." in msgs[0]["content"]

    def test_multi_room_location_update(self):
        store = HistoryStore(personality="a bot")
        store.add("#room1", "alice", "user", "hello")
        store.add("#room2", "alice", "user", "hi")
        store.set_location("alice", "NYC")
        assert "NYC" in store.get("#room1", "alice")[0]["content"]
        assert "NYC" in store.get("#room2", "alice")[0]["content"]
