from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import INDEXING_JOBS_FILE
from ..indexing_job import IndexingJob
from .json_store import JsonStore


class IndexingJobRepository:
    def __init__(self, path: Path = INDEXING_JOBS_FILE):
        self.store = JsonStore(path)

    def load_all(self) -> dict[str, IndexingJob]:
        payload = self.store.read({"jobs": []})
        jobs = [IndexingJob.from_dict(item) for item in payload.get("jobs", []) if isinstance(item, dict)]
        return {job.id: job for job in jobs}

    def save_all(self, jobs: Iterable[IndexingJob]) -> None:
        self.store.write({"schema_version": 1, "jobs": [job.to_dict() for job in jobs]})
