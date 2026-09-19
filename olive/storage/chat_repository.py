from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import CHATS_FILE
from ..models import Chat
from .json_store import JsonStore


class ChatRepository:
    def __init__(self, path: Path = CHATS_FILE):
        self.store = JsonStore(path)

    def load_all(self) -> dict[str, Chat]:
        raw = self.store.read({"chats": []})
        chats: dict[str, Chat] = {}
        for item in raw.get("chats", []):
            try:
                chat = Chat.from_dict(item)
                chats[chat.id] = chat
            except Exception:
                # One malformed conversation should not prevent the rest from loading.
                continue
        return chats

    def save_all(self, chats: Iterable[Chat]) -> None:
        self.store.write({"schema_version": 2, "chats": [c.to_dict() for c in chats]})
