"""Document ingestion and scheduler coordination, shared by all views."""

import asyncio
import base64
from pathlib import Path

from ..utils.files import cache_file, stable_file_id


class KnowledgeController:
    def __init__(self, services):
        self.s = services
        self.scheduler_lock = asyncio.Lock()
        self.upgrade_task = None
        self.upgrade_state = {'state':'idle','completed':0,'total':0,'summary':'No index upgrade has run in this runtime.'}

    def list(self):
        return [
            dict(
                ref.to_dict(),
                chat_id=chat.id,
                chat_title=chat.title,
                health=self.s.document_health.inspect(ref).state,
            )
            for chat in self.s.chats.values()
            for ref in chat.documents
        ]

    async def attach(self, chat_id, paths, permanent=False):
        for value in paths:
            path = Path(value)
            if self.s.documents.is_image(path):
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError("Image attachments must be smaller than 20 MB")
                stored = await asyncio.to_thread(
                    cache_file, path, f"img-{stable_file_id(path)}", self.s.data_dir / "attachments"
                )
                data = base64.b64encode(await asyncio.to_thread(stored.read_bytes)).decode("ascii")
                self.s.chat.images.setdefault(chat_id, []).append((path.name, data))
            else:
                extracted = await asyncio.to_thread(self.s.documents.extract, path, chat_id)
                extracted.ref.temporary = not permanent
                chat = self.s.chats[chat_id]
                if not any(ref.id == extracted.ref.id for ref in chat.documents):
                    chat.documents.append(extracted.ref)
                self.s.indexing_jobs.enqueue(
                    chat_id,
                    extracted.ref.id,
                    extracted.ref.name,
                    "index",
                    extracted.ref.content_hash or extracted.ref.id,
                )
                self.s.save_chats()
        self.s.publish("chat", self.s.chat.get(chat_id))
        await self.resume_pending()
        return self.list()

    async def resume_pending(self):
        async with self.scheduler_lock:
            await self.s.indexing_scheduler.run_pending()

    async def execute_job(self, job):
        chat = self.s.chats.get(job.chat_id)
        ref = next((ref for ref in chat.documents if ref.id == job.document_id), None) if chat else None
        if not ref or not ref.stored_path:
            self.s.indexing_jobs.transition(job.id, "failed", error="Cached document unavailable")
            return
        self.s.indexing_jobs.transition(job.id, "running", progress=2)
        try:
            extracted = await asyncio.to_thread(self.s.documents.extract, Path(ref.stored_path), job.chat_id)
            extracted.ref.id, extracted.ref.name, extracted.ref.temporary = ref.id, ref.name, ref.temporary
            for chunk in extracted.chunks:
                chunk['document_name']=ref.name
            # Re-indexing reads our cache, but provenance still names the user's source.
            extracted.ref.original_path = ref.original_path
            if not extracted.chunks:
                chat.documents = [extracted.ref if value.id == ref.id else value for value in chat.documents]
                self.s.indexing_jobs.transition(job.id, "completed", progress=100, semantic=False)
                self.s.save_chats()
                self.s.publish("chat", self.s.chat.get(chat.id))
                return  # Retained PDF pages are available to explicit DEEP vision, not text retrieval.

            def progress(done, total):
                self.s.indexing_jobs.transition(job.id, "running", progress=5 + 90 * done / max(1, total))
                self.s.publish("indexing", self.jobs())

            def keep_going():
                return self.s.indexing_jobs.get(job.id).state == "running"

            indexed = await self.s.rag.index(extracted, progress=progress, should_continue=keep_going)
            chat.documents = [indexed if value.id == ref.id else value for value in chat.documents]
            self.s.indexing_jobs.transition(
                job.id, "completed", progress=100, semantic=indexed.embedding_indexed
            )
            self.s.save_chats()
        except InterruptedError:
            self.s.publish(
                "notification",
                {"kind": "info", "message": "Indexing paused or cancelled; previous index retained"},
            )
        except Exception as exc:
            self.s.indexing_jobs.transition(job.id, "failed", error=str(exc)[:300])
            raise
        finally:
            self.s.publish("indexing", self.jobs())
            self.s.publish("knowledge", self.list())

    def jobs(self):
        return [job.to_dict() for job in self.s.indexing_jobs.list_all()]

    async def job_action(self, job_id, action):
        if action not in {"pause", "resume", "cancel", "retry"}:
            raise ValueError("Unknown indexing action")
        getattr(self.s.indexing_jobs, action)(job_id)
        self.s.publish("indexing", self.jobs())
        if action in {"resume", "retry"}:
            await self.resume_pending()
        return self.jobs()

    async def reindex(self, chat_id, document_id):
        ref = next(ref for ref in self.s.chats[chat_id].documents if ref.id == document_id)
        self.s.indexing_jobs.enqueue(chat_id, ref.id, ref.name, "reindex", ref.content_hash or ref.id)
        await self.resume_pending()
        return self.list()

    async def relink(self, chat_id, document_id, path):
        ref = next(ref for ref in self.s.chats[chat_id].documents if ref.id == document_id)
        result = await asyncio.to_thread(self.s.document_health.relink, ref, Path(path))
        self.s.save_chats()
        return result.detail

    def remove(self, chat_id, document_id):
        for job in self.s.indexing_jobs.list_all():
            if job.document_id == document_id and job.state in {"queued", "running", "paused"}:
                self.s.indexing_jobs.cancel(job.id)
        chat = self.s.chats[chat_id]
        chat.documents = [ref for ref in chat.documents if ref.id != document_id]
        self.s.rag.delete_document(document_id)
        self.s.save_chats()
        return self.list()

    async def retrieve(self, chat_id, query):
        values = await self.s.rag.retrieve(chat_id, query, limit=10)
        return [
            dict(
                item.source_dict(), score=item.score, lexical=item.lexical_score, semantic=item.semantic_score
            )
            for item in values
        ]

    def cancel_upgrade(self):
        if self.upgrade_task and not self.upgrade_task.done():
            self.upgrade_task.cancel()
            return {'cancellation_requested':True}
        return {'cancellation_requested':False}

    async def upgrade(self, *, return_status=False):
        if self.upgrade_task and not self.upgrade_task.done():
            raise ValueError('An index upgrade is already active')
        self.upgrade_task = asyncio.current_task()
        self.upgrade_state = {'state':'running','completed':0,'total':0,'summary':'Checking the configured local embedding model.'}
        self.s.publish('knowledge.upgrade',dict(self.upgrade_state))
        def progress(done,total):
            self.upgrade_state.update(completed=done,total=total,summary=f'Indexed {done} of {total} chunks.')
            self.s.publish('knowledge.upgrade',dict(self.upgrade_state))
            self.s.publish('notification', {'kind':'info','message':f'Embeddings {done}/{total}'})
        try:
            done,total=await self.s.rag.reembed_missing(progress=progress)
            self.upgrade_state.update(completed=done,total=total,state='completed' if done==total else 'partial' if done else 'blocked',
                                      summary=f'Indexed {done} of {total} chunks.' if done==total else f'Indexed {done} of {total} chunks; semantic indexing is unavailable for the remaining chunks. Earlier batches are retained; existing lexical search remains available.')
        except asyncio.CancelledError:
            self.upgrade_state.update(state='cancelled',summary='Index upgrade cancelled. Earlier completed batches are retained.')
        except Exception:
            self.upgrade_state.update(state='failed',summary='Index upgrade failed. Earlier completed batches are retained; lexical search remains available.')
            raise
        finally:
            self.upgrade_task=None
            self.s.publish('knowledge.upgrade',dict(self.upgrade_state))
            self.s.publish('knowledge',self.list())
        return dict(self.upgrade_state) if return_status else self.list()
