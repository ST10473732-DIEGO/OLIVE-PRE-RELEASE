from __future__ import annotations


class LearningService:
    """Coordinates explicitly approved knowledge; it never retrains model weights."""
    def __init__(self, source_repository): self.sources = source_repository
    def add_approved_source(self, source, *, approved: bool):
        if not approved: raise PermissionError("Knowledge ingestion requires approval")
        return self.sources.save(source)
    def is_stale(self, source, current_hash: str) -> bool: return source.content_hash != current_hash
