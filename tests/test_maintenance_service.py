import unittest
from types import SimpleNamespace
from olive.services.maintenance_service import MaintenanceService

class Store:
    def integrity_check(self): return {"ok": True}
    def aggregate_counts(self, chat_id): return {"missing_embeddings": 2}
    def document_ids(self): return ["known", "orphan"]
class Jobs:
    def list_all(self): return [SimpleNamespace(id="j", state="paused")]
    def cleanup_completed(self): return 3
class Health:
    def inspect(self, ref): return SimpleNamespace(state="healthy" if ref.id == "known" else "changed")

class MaintenanceTests(unittest.TestCase):
    def test_scan_reports_integrity_orphans_jobs_and_embeddings(self):
        chat = SimpleNamespace(documents=[SimpleNamespace(id="known"), SimpleNamespace(id="stale")])
        result = MaintenanceService(Store(), Jobs(), Health()).scan({"c": chat})
        self.assertEqual(result["orphan_document_indexes"], ["orphan"])
        self.assertEqual(result["stale_documents"], ["stale"])
        self.assertEqual(result["missing_embeddings"], 2)
    def test_cleanup_requires_confirmation(self):
        service = MaintenanceService(Store(), Jobs(), Health())
        with self.assertRaises(PermissionError): service.cleanup_completed_jobs(confirmed=False)
        self.assertEqual(service.cleanup_completed_jobs(confirmed=True), 3)

if __name__ == "__main__": unittest.main()
