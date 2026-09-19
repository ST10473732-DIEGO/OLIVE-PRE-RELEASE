import tempfile
import unittest
from pathlib import Path

from olive.services.indexing_job_service import IndexingJobService
from olive.storage.indexing_job_repository import IndexingJobRepository


class IndexingJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = IndexingJobService(IndexingJobRepository(Path(self.temp.name) / "jobs.json"))
    def tearDown(self): self.temp.cleanup()

    def test_persistence_duplicate_prevention_and_retry(self):
        first = self.service.enqueue("chat", "doc", "guide.pdf", "index", "hash-1")
        duplicate = self.service.enqueue("chat", "doc", "guide.pdf", "index", "hash-1")
        self.assertEqual(first.id, duplicate.id)
        self.service.transition(first.id, "failed", error="failure")
        retried = self.service.retry(first.id)
        self.assertEqual(retried.state, "queued")
        self.assertIsNone(retried.error)

    def test_running_job_recovers_as_queued(self):
        job = self.service.enqueue("chat", "doc", "guide.pdf", "index", "hash")
        self.service.transition(job.id, "running", progress=25)
        recovered = self.service.recover_interrupted()
        self.assertEqual(recovered[0].state, "queued")

    def test_pause_resume_cancel(self):
        job = self.service.enqueue("chat", "doc", "guide.pdf", "index", "hash")
        self.assertEqual(self.service.pause(job.id).state, "paused")
        self.assertEqual(self.service.resume(job.id).state, "queued")
        self.assertEqual(self.service.cancel(job.id).state, "cancelled")
        self.assertEqual(self.service.get(job.id).state, "cancelled")


if __name__ == "__main__": unittest.main()
