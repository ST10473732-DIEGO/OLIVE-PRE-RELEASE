import json
import tempfile
import unittest
from unittest.mock import patch
import shutil
from pathlib import Path

from olive.services.backup_service import BackupError, BackupService


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root / "chats.json").write_text('{"schema_version":2,"chats":[{"id":"original"}]}')
        (self.root / "memories.json").write_text('{"schema_version":1,"memories":[]}')
        self.service = BackupService(self.root, self.root / "backups")
    def tearDown(self): self.temp.cleanup()

    def test_create_manifest_excludes_cache_and_exports_selected(self):
        (self.root / "attachments").mkdir(); (self.root / "attachments" / "temp.bin").write_bytes(b"x")
        path = self.service.create(components={"chats", "memories"})
        manifest = self.service.validate(path)
        self.assertEqual(manifest["backup_format_version"], 1)
        self.assertEqual(set(manifest["included_components"]), {"chats", "memories"})

    def test_invalid_backup_and_unconfirmed_restore_are_rejected(self):
        bad = self.root / "bad.zip"; bad.write_bytes(b"not a zip")
        with self.assertRaises(BackupError): self.service.validate(bad)
        backup = self.service.create()
        with self.assertRaises(PermissionError): self.service.restore(backup)

    def test_restore_creates_safety_backup(self):
        backup = self.service.create()
        (self.root / "chats.json").write_text('{"schema_version":2,"chats":[{"id":"changed"}]}')
        safety = self.service.restore(backup, confirmed=True)
        self.assertTrue(safety.exists())
        self.assertEqual(json.loads((self.root / "chats.json").read_text())["chats"][0]["id"], "original")

    def test_restore_rolls_back_after_partial_replacement(self):
        backup = self.service.create(components={"chats", "memories"})
        (self.root / "chats.json").write_text('{"schema_version":2,"chats":[{"id":"current"}]}')
        original_copy = shutil.copy2
        calls = 0
        def fail_fourth(source, target, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4: raise OSError("simulated write failure")
            return original_copy(source, target, *args, **kwargs)
        with patch("olive.services.backup_service.shutil.copy2", side_effect=fail_fourth):
            with self.assertRaises(OSError): self.service.restore(backup, confirmed=True)
        self.assertEqual(json.loads((self.root / "chats.json").read_text())["chats"][0]["id"], "current")


if __name__ == "__main__": unittest.main()
