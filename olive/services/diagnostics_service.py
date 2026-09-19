from __future__ import annotations

from ..config import APP_VERSION, DATA_DIR, LOGS_DIR


class DiagnosticsService:
    def __init__(self, ollama, registry, rag, memory, jobs=None, ocr=None):
        self.ollama = ollama
        self.registry = registry
        self.rag = rag
        self.memory = memory
        self.jobs = jobs
        self.ocr = ocr

    async def collect(self, chat) -> dict[str, str | int | bool | list[str]]:
        connected = await self.ollama.ping()
        models = sorted(self.registry.models)
        embedding = self.rag.embedding_model or "None"
        embedding_info = self.registry.get(embedding) if embedding != "None" else None
        counts = self.rag.store.aggregate_counts(chat.id)
        jobs = self.jobs.list_all() if self.jobs else []
        ocr = self.ocr.diagnostics() if self.ocr and hasattr(self.ocr, "diagnostics") else {}
        return {
            "olive_version": APP_VERSION,
            "ollama_connected": connected,
            "installed_models": models,
            "active_chat_model": chat.model or "None",
            "active_embedding_model": embedding,
            "semantic_rag_enabled": bool(embedding_info and embedding_info.supports_embeddings),
            "document_count": len(chat.documents),
            "memory_count": len(self.memory.list_all()),
            "ocr_available": bool(self.ocr and self.ocr.available),
            "ocr_provider": ocr.get("provider", "None"),
            "ocr_executable": ocr.get("executable", "Not found"),
            "ocr_version": ocr.get("version", "Unavailable"),
            "ocr_confidence_available": ocr.get("confidence_available", False),
            "rag_schema_version": self.rag.store.schema_version(),
            "memory_schema_version": self.memory.repository.schema_version(),
            "queued_indexing_jobs": sum(job.state in {"queued", "running", "paused"} for job in jobs),
            "failed_indexing_jobs": sum(job.state == "failed" for job in jobs),
            "indexed_chunk_count": counts["chunks"],
            "chunks_missing_embeddings": counts["missing_embeddings"],
            "rag_integrity_ok": bool(self.rag.store.integrity_check()["ok"]),
            "data_directory": str(DATA_DIR),
            "log_directory": str(LOGS_DIR),
        }
