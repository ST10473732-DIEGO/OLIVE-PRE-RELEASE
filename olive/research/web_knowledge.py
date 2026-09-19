"""Explicitly approved web material indexed through the existing RAG architecture."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from ..knowledge.source import KnowledgeSource, SourceProvenance
from ..models import DocumentRef
from ..storage.json_store import JsonStore
from ..services.document_service import ExtractedDocument
from ..utils.chunking import TextPage, chunk_pages
from .models import PageObservation, timestamp
from .urls import normalize_url
from .extraction import content_hash


def namespace(project_id=None):
    return "web:project:" + project_id if project_id else "web:global"


class WebKnowledgeService:
    def __init__(self, sources, learning, rag, data_dir, project_repository=None):
        self.sources, self.learning, self.rag = sources, learning, rag
        self.pages = JsonStore(Path(data_dir) / "web_knowledge.json")
        self.projects = project_repository
        for source in self.sources.load_all().values():
            if source.source_type == "web" and source.metadata.get("index_state") == "indexing":
                source.metadata["index_state"] = "requires_reindex"
                self.sources.save(source)

    def list(self, project_id=None):
        return [
            source
            for source in self.sources.load_all().values()
            if source.source_type == "web" and (project_id is None or source.project_id in {None, project_id})
        ]

    def page(self, source_id):
        value = self.pages.read({"schema_version": 1, "pages": {}})["pages"].get(source_id)
        return PageObservation(**value) if value else None

    async def ingest(self, page, approved=False, project_id=None, collection="", session_id=None):
        if not approved:
            raise PermissionError("Permanent web learning requires explicit approval")
        if not page.text.strip():
            raise ValueError("Source has no usable content")
        if content_hash(page.text) != page.content_hash:
            raise ValueError("Source content hash does not match its text")
        url = normalize_url(page.url)
        if project_id and (not self.projects or project_id not in self.projects.load_all()):
            raise ValueError("Unknown project")
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url + "|" + str(project_id) + "|" + collection))
        existing = self.sources.load_all().get(source_id)
        source = (
            deepcopy(existing)
            if existing
            else KnowledgeSource(
                "web",
                page.title,
                SourceProvenance("research", url, trust_label="untrusted_web"),
                "",
                id=source_id,
                url=url,
                project_id=project_id,
                collection=collection,
            )
        )
        source.metadata["last_checked"] = timestamp()
        if (
            existing
            and source.content_hash == page.content_hash
            and source.metadata.get("index_state") == "ready"
            and source.id in self.rag.store.document_ids()
        ):
            source.metadata["refresh_state"] = "unchanged"
            source.retrieved_at = page.retrieved_at
            source.provenance.retrieved_at = page.retrieved_at
            values = self.pages.read({"schema_version": 1, "pages": {}})
            values["pages"][source.id] = page.to_dict()
            self.pages.write(values)
            self.learning.add_approved_source(source, approved=True)
            return {"status": "unchanged", "source": source.to_dict()}
        source.metadata["index_state"] = "indexing"
        self.learning.add_approved_source(source, approved=True)
        text_pages = [TextPage(page.text, origin_type="web_source")]
        chunks = chunk_pages(text_pages)
        rows = [
            {
                "chat_id": namespace(project_id),
                "document_name": page.title,
                "chunk_index": chunk.chunk_index,
                "page_number": None,
                "content": chunk.text,
                "origin_type": "web_source",
                "ocr_confidence": None,
            }
            for chunk in chunks
        ]
        ref = DocumentRef(source.id, page.title, kind="web", content_hash=page.content_hash)
        try:
            ref = await self.rag.index(ExtractedDocument(ref, text_pages, rows))
            if existing and existing.content_hash != page.content_hash:
                history = source.metadata.setdefault("history", [])
                history.append(
                    {
                        "content_hash": existing.content_hash,
                        "retrieved_at": existing.retrieved_at,
                        "title": existing.title,
                        "publication_date": existing.publication_date,
                        "updated_date": existing.updated_date,
                        "superseded_at": timestamp(),
                    }
                )
            source.title, source.content_hash = page.title, page.content_hash
            source.version_hash = page.content_hash
            source.url, source.canonical_url, source.domain = url, page.canonical_url, urlsplit(url).hostname
            for key in ("author", "publication_date", "updated_date", "retrieved_at", "content_type"):
                setattr(source, key, getattr(page, key))
            source.research_session_id = session_id
            source.provenance.retrieved_at = page.retrieved_at
            source.provenance.reliability_notes = (
                "User-approved source material; webpage claims are not verified facts"
            )
            source.chunk_ids = [f"{source.id}:{chunk.chunk_index}" for chunk in chunks]
            source.metadata.update(
                index_state="ready",
                embedding_indexed=ref.embedding_indexed,
                chunk_count=ref.chunk_count,
                refresh_state="updated" if existing else "saved",
            )
            values = self.pages.read({"schema_version": 1, "pages": {}})
            values["pages"][source.id] = page.to_dict()
            self.pages.write(values)
            self.learning.add_approved_source(source, approved=True)
            if project_id:
                project = self.projects.load_all()[project_id]
                if source.id not in project.knowledge_ids:
                    project.knowledge_ids.append(source.id)
                    self.projects.save(project)
            return {"status": source.metadata["refresh_state"], "source": source.to_dict()}
        except BaseException:
            # Also mark cancellation; never leave a partially replaced index presented as ready.
            source.metadata["index_state"] = "requires_reindex"
            self.sources.save(source)
            raise

    async def retrieve(self, query, project_id=None, limit=6):
        sources = {source.id: source for source in self.list(project_id)}
        results = []
        for scope in [namespace()] + ([namespace(project_id)] if project_id else []):
            for hit in await self.rag.retrieve(scope, query, limit):
                source = sources.get(hit.document_id)
                if source and source.metadata.get("index_state") == "ready":
                    results.append(
                        {
                            "source": source.to_dict(),
                            "text": hit.content,
                            "score": hit.score,
                            "chunk_index": hit.chunk_index,
                            "trust_label": "untrusted_web",
                        }
                    )
        return sorted(results, key=lambda hit: -hit["score"])[:limit]

    async def reusable_pages(self, query, project_id=None, max_age=3600, limit=4):
        if max_age <= 0:
            return []
        result, seen = [], set()
        for hit in await self.retrieve(query, project_id, limit):
            source_id = hit["source"]["id"]
            if source_id in seen:
                continue
            page = self.page(source_id)
            if page:
                try:
                    age = (
                        datetime.now(timezone.utc) - datetime.fromisoformat(page.retrieved_at)
                    ).total_seconds()
                except (ValueError, TypeError):
                    continue
                if 0 <= age <= max_age:
                    result.append((hit["source"], page))
                    seen.add(source_id)
        return result

    def remove(self, source_id, approved=False):
        if not approved:
            raise PermissionError("Removing web Knowledge requires approval")
        source = self.sources.load_all().get(source_id)
        if not source or source.source_type != "web":
            raise ValueError("Unknown web source")
        self.rag.delete_document(source_id)
        # Keep provenance history, mark removed, and stop presenting it as active Knowledge.
        source.metadata.update(index_state="removed", removed_at=timestamp())
        self.sources.save(source)
        values = self.pages.read({"schema_version": 1, "pages": {}})
        values["pages"].pop(source_id, None)
        self.pages.write(values)
