import asyncio
import tempfile
import unittest
from pathlib import Path

from olive.services.indexing_job_service import IndexingJobService
from olive.services.indexing_scheduler import IndexingScheduler
from olive.storage.indexing_job_repository import IndexingJobRepository


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrency_is_bounded_and_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = IndexingJobService(IndexingJobRepository(Path(tmp) / "jobs.json"))
            for i in range(5): jobs.enqueue("c", f"d{i}", f"{i}.txt", "index", str(i))
            active = peak = 0
            async def execute(job):
                nonlocal active, peak
                jobs.transition(job.id, "running"); active += 1; peak = max(peak, active)
                await asyncio.sleep(0); active -= 1; jobs.transition(job.id, "completed", progress=100)
            scheduler = IndexingScheduler(jobs, execute, max_workers=2)
            await scheduler.run_pending()
            self.assertEqual(peak, 2)
            self.assertTrue(all(job.state == "completed" for job in jobs.list_all()))
            self.assertEqual(IndexingScheduler(jobs, execute, 99).max_workers, 3)

    async def test_shutdown_recovers_running_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = IndexingJobService(IndexingJobRepository(Path(tmp) / "jobs.json"))
            job = jobs.enqueue("c", "d", "d.txt", "index", "v"); jobs.transition(job.id, "running")
            scheduler = IndexingScheduler(jobs, lambda job: None)
            await scheduler.shutdown()
            self.assertEqual(jobs.get(job.id).state, "queued")


if __name__ == "__main__": unittest.main()
