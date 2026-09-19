from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class IndexingScheduler:
    def __init__(self, jobs, executor, max_workers: int = 1):
        self.jobs = jobs
        self.executor = executor
        self.max_workers = min(3, max(1, int(max_workers)))
        self._shutdown = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    async def run_pending(self) -> None:
        semaphore = asyncio.Semaphore(self.max_workers)
        queued = [job for job in reversed(self.jobs.list_all()) if job.state == "queued"]
        async def run(job):
            async with semaphore:
                if self._shutdown.is_set() or (self.jobs.get(job.id) or job).state != "queued": return
                try:
                    await self.executor(job)
                except Exception:
                    logger.exception("Indexing scheduler job failed: %s", job.id)
                    current = self.jobs.get(job.id)
                    if current and current.state not in {"cancelled", "paused"}:
                        self.jobs.transition(job.id, "failed", error="Scheduled indexing failed")
        self._tasks = {asyncio.create_task(run(job)) for job in queued}
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def shutdown(self) -> None:
        self._shutdown.set()
        for job in self.jobs.list_all():
            if job.state == "running": self.jobs.transition(job.id, "queued", error="Paused during shutdown")
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
