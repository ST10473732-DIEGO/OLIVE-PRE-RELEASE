from datetime import datetime, timezone
import hashlib
from pathlib import Path
from ..storage.json_store import JsonStore
from .models import PageObservation
from .urls import normalize_url


class ResearchCache:
    def __init__(self, directory, max_entries=64, max_bytes=20 * 1024 * 1024):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_entries, self.max_bytes = max_entries, max_bytes

    def path(self, url):
        key = hashlib.sha256(normalize_url(url).encode()).hexdigest()
        return self.directory / (key + ".json")

    def get(self, url, max_age=3600):
        if max_age <= 0:
            return None
        value = JsonStore(self.path(url)).read(None)
        if not value:
            return None
        try:
            page = PageObservation(**value)
            if hashlib.sha256(page.text.encode("utf-8")).hexdigest() != page.content_hash:
                return None
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(page.retrieved_at)).total_seconds()
        except (ValueError, TypeError):
            return None
        return page if 0 <= age <= max_age else None

    def put(self, page):
        JsonStore(self.path(page.url)).write(page.to_dict())
        self.cleanup()

    def cleanup(self, clear=False):
        entries = sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        total = 0
        removed = 0
        for index, path in enumerate(entries):
            total += path.stat().st_size
            if clear or index >= self.max_entries or total > self.max_bytes:
                path.unlink()
                removed += 1
        return removed

    def status(self):
        files = list(self.directory.glob("*.json"))
        return {"entries": len(files), "bytes": sum(p.stat().st_size for p in files)}
