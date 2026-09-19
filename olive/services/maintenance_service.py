from __future__ import annotations

from pathlib import Path


class MaintenanceService:
    def __init__(self, rag_store, jobs, document_health):
        self.rag_store, self.jobs, self.document_health = rag_store, jobs, document_health

    def scan(self, chats: dict) -> dict:
        documents = [ref for chat in chats.values() for ref in chat.documents]
        known = {ref.id for ref in documents}
        counts = self.rag_store.aggregate_counts(None)
        stale = [ref.id for ref in documents if self.document_health.inspect(ref).state != "healthy"]
        indexed_ids = set(self.rag_store.document_ids()) if hasattr(self.rag_store, "document_ids") else set()
        jobs = self.jobs.list_all()
        return {"integrity": self.rag_store.integrity_check(), "stale_documents": stale,
                "orphan_document_indexes": sorted(indexed_ids - known),
                "incomplete_jobs": [job.id for job in jobs if job.state in {"queued", "running", "paused"}],
                "missing_embeddings": counts["missing_embeddings"]}

    def cleanup_completed_jobs(self, *, confirmed: bool) -> int:
        if not confirmed: raise PermissionError("Explicit confirmation is required")
        return self.jobs.cleanup_completed()
