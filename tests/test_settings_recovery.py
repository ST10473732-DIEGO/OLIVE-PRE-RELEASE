import tempfile
import unittest
from pathlib import Path
from olive.storage.settings_repository import SettingsRepository

class SettingsRecoveryTests(unittest.TestCase):
    def test_corrupt_optional_settings_do_not_block_startup_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); settings = root / "settings.json"; settings.write_text("{broken")
            repo = SettingsRepository(settings, root/"defaults.json", root/"aliases.json")
            values = repo.load()
            self.assertEqual(values["max_indexing_workers"], 1)
            self.assertFalse(values["auto_memory_approval"])

if __name__ == "__main__": unittest.main()
