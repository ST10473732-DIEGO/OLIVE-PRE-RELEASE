from __future__ import annotations

from pathlib import Path
from typing import Iterable
import hashlib
import json
import uuid

from ..config import CHATS_FILE
from ..models import Chat
from .json_store import JsonStore


class ChatRepository:
    def __init__(self, path: Path = CHATS_FILE):
        self.store = JsonStore(path)

    def load_all(self) -> dict[str, Chat]:
        raw = self.store.read({"chats": []})
        chats: dict[str, Chat] = {}
        for position, item in enumerate(raw.get("chats", [])):
            try:
                # Deterministic additive IDs for legacy records until the next
                # ordinary save persists them. No path, title or row ID is used
                # alone as cross-device identity; existing UUIDs are unchanged.
                if not item.get("id"):
                    seed = json.dumps(item, sort_keys=True, ensure_ascii=False)
                    item["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "olive-legacy-chat:" + str(position) + ":" + hashlib.sha256(seed.encode()).hexdigest()))
                for index, message in enumerate(item.get("messages", [])):
                    if not message.get("id"):
                        seed = json.dumps(message, sort_keys=True, ensure_ascii=False)
                        message["id"] = str(uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, "olive-chat:" + item["id"]), "message:" + str(index) + ":" + hashlib.sha256(seed.encode()).hexdigest()))
                chat = Chat.from_dict(item)
                chats[chat.id] = chat
            except Exception:
                # One malformed conversation should not prevent the rest from loading.
                continue
        return chats

    def save_all(self, chats: Iterable[Chat]) -> None:
        self.store.write({"schema_version": 2, "chats": [c.to_dict() for c in chats]})
