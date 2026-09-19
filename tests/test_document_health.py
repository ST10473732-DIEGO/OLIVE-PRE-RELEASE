import tempfile
import unittest
from pathlib import Path

from olive.models import DocumentRef
from olive.services.document_health_service import DocumentHealthService
from olive.utils.files import content_hash


class DocumentHealthTests(unittest.TestCase):
    def test_detects_changed_and_missing_original_without_removing_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.txt"; path.write_text("original", encoding="utf-8")
            stat = path.stat()
            ref = DocumentRef("d", "doc.txt", original_path=str(path), content_hash=content_hash(path),
                              source_size=stat.st_size, source_mtime_ns=stat.st_mtime_ns, indexed=True)
            self.assertEqual(DocumentHealthService().inspect(ref).state, "healthy")
            path.write_text("changed content", encoding="utf-8")
            self.assertEqual(DocumentHealthService().inspect(ref).state, "changed")
            path.unlink()
            self.assertEqual(DocumentHealthService().inspect(ref).state, "original_missing")
            self.assertTrue(ref.indexed)

    def test_hash_is_content_based_and_relink_updates_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.txt"; b = Path(tmp) / "b.txt"
            a.write_text("same", encoding="utf-8"); b.write_text("same", encoding="utf-8")
            self.assertEqual(content_hash(a), content_hash(b))
            ref = DocumentRef("d", "a.txt")
            DocumentHealthService().relink(ref, b)
            self.assertEqual(ref.original_path, str(b.resolve()))

    def test_relink_changed_file_preserves_old_identity_until_reindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old.txt"; new = Path(tmp) / "new.txt"
            old.write_text("old", encoding="utf-8"); new.write_text("new", encoding="utf-8")
            ref = DocumentRef("d", "old.txt", content_hash=content_hash(old), indexed=True)
            health = DocumentHealthService().relink(ref, new)
            self.assertEqual(health.state, "changed")
            self.assertEqual(ref.content_hash, content_hash(old))
            self.assertTrue(ref.indexed)


if __name__ == "__main__": unittest.main()
