from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class HistoryStore:
    """In-memory history per room and user with system prompt support.

    Optionally persists to an encrypted file when *store_path* and
    *encryption_key* are both provided.
    """

    def __init__(
        self,
        prompt_prefix: str = "you are ",
        prompt_suffix: str = ".",
        personality: str = "",
        *,
        prompt_suffix_extra: str = "",
        max_items: int = 24,
        history_size: Optional[int] = None,
        system_prompt: Optional[str] = None,
        store_path: Optional[str] = None,
        encryption_key: Optional[str] = None,
    ) -> None:
        if system_prompt is not None:
            self.prompt_prefix = ""
            self.prompt_suffix = ""
            self.prompt_suffix_extra = ""
            self.personality = ""
            self._fixed_system_prompt = system_prompt
        else:
            self.prompt_prefix = prompt_prefix
            self.prompt_suffix = prompt_suffix
            self.prompt_suffix_extra = prompt_suffix_extra
            self.personality = personality
            self._fixed_system_prompt = None
        self.max_items = history_size or max_items
        self._include_extra = True
        self._messages: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        self._locations: Dict[str, str] = {}
        self.user_models: Dict[str, Dict[str, str]] = {}

        # Encrypted persistence setup
        self._fernet = None
        self._store_file: Optional[Path] = None
        if store_path and encryption_key:
            try:
                from cryptography.fernet import Fernet
                self._fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
                self._store_file = Path(store_path) / "history.enc"
                self._store_file.parent.mkdir(parents=True, exist_ok=True)
                self._load()
            except Exception:
                log.exception("Failed to initialize encrypted persistence")
                self._fernet = None
                self._store_file = None

    @property
    def messages(self) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
        return self._messages

    def set_verbose(self, verbose: bool) -> None:
        self._include_extra = not bool(verbose)

    def _full_suffix(self) -> str:
        extra = self.prompt_suffix_extra if self._include_extra and self.prompt_suffix_extra else ""
        return f"{self.prompt_suffix}{extra}"

    def _location_suffix(self, user: str) -> str:
        loc = self._locations.get(user, "")
        if loc:
            return f" The user has indicated they are located in {loc}.  Use when needed, Do not adopt this as part of your personality."
        return ""

    def _system_for(self, room: str, user: str) -> str:
        del room
        if self._fixed_system_prompt is not None:
            return self._fixed_system_prompt + self._location_suffix(user)
        return f"{self.prompt_prefix}{self.personality}{self._full_suffix()}{self._location_suffix(user)}"

    def _ensure(self, room: str, user: str) -> None:
        if room not in self._messages:
            self._messages[room] = {}
        if user not in self._messages[room]:
            self._messages[room][user] = [{"role": "system", "content": self._system_for(room, user)}]

    def init_prompt(
        self,
        room: str,
        user: str,
        persona: Optional[str] = None,
        custom: Optional[str] = None,
    ) -> None:
        self._ensure(room, user)
        loc_suffix = self._location_suffix(user)
        if custom:
            self._messages[room][user] = [{"role": "system", "content": custom + loc_suffix}]
        else:
            p = persona if (persona is not None and persona != "") else self.personality
            self._messages[room][user] = [
                {"role": "system", "content": f"{self.prompt_prefix}{p}{self._full_suffix()}{loc_suffix}"}
            ]
        self._save()

    def add(self, room: str, user: str, role: str, content: str) -> None:
        self._ensure(room, user)
        self._messages[room][user].append({"role": role, "content": content})
        self._trim(room, user)
        self._save()

    def get(self, room: str, user: str) -> List[Dict[str, str]]:
        self._ensure(room, user)
        return list(self._messages[room][user])

    def reset(self, room: str, user: str, stock: bool = False) -> None:
        if room not in self._messages:
            self._messages[room] = {}
        self._messages[room][user] = []
        if not stock:
            self.init_prompt(room, user, persona=self.personality)
        self._save()

    def clear(self, room: str, user: str) -> None:
        self.reset(room, user, stock=True)

    def clear_all(self) -> None:
        self._messages.clear()
        # Locations are user preferences, not conversation state — preserve them
        self._save()

    def set_location(self, user: str, location: str) -> None:
        """Set or clear a user's location. Updates system prompts in all existing threads."""
        old_suffix = self._location_suffix(user)
        if location:
            self._locations[user] = location
        else:
            self._locations.pop(user, None)
        new_suffix = self._location_suffix(user)

        # Update system prompts in all existing threads for this user
        for room in self._messages:
            if user in self._messages[room]:
                msgs = self._messages[room][user]
                if msgs and msgs[0].get("role") == "system":
                    content = msgs[0]["content"]
                    if old_suffix:
                        content = content.replace(old_suffix, "")
                    content = content + new_suffix
                    msgs[0]["content"] = content
        self._save()

    def get_location(self, user: str) -> Optional[str]:
        return self._locations.get(user) or None

    def _trim(self, room: str, user: str) -> None:
        msgs = self._messages[room][user]
        while len(msgs) > self.max_items:
            if msgs and msgs[0].get("role") == "system":
                if len(msgs) > 1:
                    msgs.pop(1)
                else:
                    break
            else:
                msgs.pop(0)

    def _save(self) -> None:
        if not self._fernet or not self._store_file:
            return
        try:
            data = json.dumps({
                "messages": self._messages,
                "locations": self._locations,
            })
            encrypted = self._fernet.encrypt(data.encode())
            self._store_file.write_bytes(encrypted)
        except Exception:
            log.exception("Failed to save encrypted history")

    def _load(self) -> None:
        if not self._fernet or not self._store_file or not self._store_file.exists():
            return
        try:
            encrypted = self._store_file.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode())
            if isinstance(data, dict):
                if "messages" in data:
                    self._messages = data["messages"]
                    self._locations = data.get("locations", {})
                else:
                    # Old format: bare messages dict
                    self._messages = data
        except Exception:
            log.exception("Failed to load encrypted history (wrong key?), starting fresh")
            self._messages = {}
            self._locations = {}
