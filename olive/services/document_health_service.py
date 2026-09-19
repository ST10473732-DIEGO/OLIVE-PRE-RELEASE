from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..utils.files import content_hash


@dataclass(slots=True)
class DocumentHealth:
    state: str
    detail: str
    current_hash: str | None = None


class DocumentHealthService:
    _extensions = {".pdf", ".txt", ".md", ".markdown", ".py", ".json", ".csv", ".docx"}

    def inspect(self, ref, *, verify_hash: bool = False) -> DocumentHealth:
        if not ref.original_path:
            cached = Path(ref.stored_path) if ref.stored_path else None
            return DocumentHealth("legacy", "Original path was not recorded") if cached and cached.exists() \
                else DocumentHealth("cache_missing", "Cached document is unavailable")
        path = Path(ref.original_path)
        if not path.exists():
            return DocumentHealth("original_missing", "Original file was moved or deleted; existing index is preserved")
        stat = path.stat()
        metadata_changed = ref.source_size != stat.st_size or ref.source_mtime_ns != stat.st_mtime_ns
        if not metadata_changed and not verify_hash:
            return DocumentHealth("healthy", "Source metadata matches")
        current = content_hash(path)
        if ref.content_hash and current != ref.content_hash:
            return DocumentHealth("changed", "Original file changed after indexing", current)
        return DocumentHealth("healthy", "Content is unchanged", current)

    def relink(self, ref, path: Path) -> DocumentHealth:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in self._extensions:
            raise ValueError("Unsupported document type")
        new_hash = content_hash(path)
        changed = bool(ref.content_hash and new_hash != ref.content_hash)
        stat = path.stat()
        ref.original_path = str(path)
        if not changed:
            ref.content_hash = new_hash
        ref.source_size = stat.st_size
        ref.source_mtime_ns = stat.st_mtime_ns
        return DocumentHealth("changed" if changed else "healthy",
                              "Replacement differs; re-indexing is recommended" if changed else "Document relinked",
                              new_hash)
