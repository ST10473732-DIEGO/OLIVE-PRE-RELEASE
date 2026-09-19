from __future__ import annotations

from ..indexing_job import IndexingJob, JOB_STATES
from ..models import now_iso


class IndexingJobService:
    def __init__(self, repository):
        self.repository = repository

    def recover_interrupted(self) -> list[IndexingJob]:
        jobs = self.repository.load_all()
        recovered = []
        for job in jobs.values():
            if job.state == "running":
                job.state, job.error, job.updated_at = "queued", "Recovered after interrupted shutdown", now_iso()
                recovered.append(job)
        if recovered:
            self.repository.save_all(jobs.values())
        return recovered

    def enqueue(self, chat_id: str, document_id: str, filename: str, job_type: str, version: str) -> IndexingJob:
        jobs = self.repository.load_all()
        for job in jobs.values():
            if (job.document_id, job.job_type, job.version) == (document_id, job_type, version) and job.state in {
                "queued", "running", "paused", "completed"
            }:
                return job
        job = IndexingJob(chat_id, document_id, filename, job_type, version)
        jobs[job.id] = job
        self.repository.save_all(jobs.values())
        return job

    def list_all(self) -> list[IndexingJob]:
        return sorted(self.repository.load_all().values(), key=lambda job: job.created_at, reverse=True)

    def get(self, job_id: str) -> IndexingJob | None:
        return self.repository.load_all().get(job_id)

    def transition(self, job_id: str, state: str, *, progress: float | None = None,
                   error: str | None = None, semantic: bool | None = None) -> IndexingJob:
        if state not in JOB_STATES:
            raise ValueError(f"Invalid indexing state: {state}")
        jobs = self.repository.load_all()
        if job_id not in jobs:
            raise KeyError(job_id)
        job = jobs[job_id]
        job.state, job.updated_at, job.error = state, now_iso(), error
        if progress is not None: job.progress = min(100.0, max(0.0, progress))
        if semantic is not None: job.semantic = semantic
        self.repository.save_all(jobs.values())
        return job

    def pause(self, job_id: str): return self.transition(job_id, "paused")
    def resume(self, job_id: str): return self.transition(job_id, "queued")
    def cancel(self, job_id: str): return self.transition(job_id, "cancelled")
    def retry(self, job_id: str):
        job = self.transition(job_id, "queued", progress=0.0)
        job.error = None
        jobs = self.repository.load_all(); jobs[job.id] = job; self.repository.save_all(jobs.values())
        return job

    def cleanup_completed(self) -> int:
        jobs = self.repository.load_all()
        ids = [job_id for job_id, job in jobs.items() if job.state == "completed"]
        for job_id in ids: del jobs[job_id]
        if ids: self.repository.save_all(jobs.values())
        return len(ids)
