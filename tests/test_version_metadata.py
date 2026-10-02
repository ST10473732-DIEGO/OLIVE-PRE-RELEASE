"""One product version across Python, desktop and Studio metadata.

The iPhone app's MARKETING_VERSION is versioned separately (it moves with the iOS
release phase, together with its bundle identity) and is deliberately not checked.
Backup and protocol format versions are independent of the product version.
"""
import json
from pathlib import Path
import re
import tomllib
import unittest

from olive import identity
from olive.services import backup_service
from olive.studio_tooling import lsp

ROOT = Path(__file__).resolve().parents[1]


class VersionMetadataTests(unittest.TestCase):
    def test_python_desktop_and_lockfile_share_the_identity_version(self):
        version = identity.APP_VERSION
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertEqual(tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version'], version)
        package = json.loads((ROOT / 'desktop/package.json').read_text(encoding='utf-8'))
        lock = json.loads((ROOT / 'desktop/package-lock.json').read_text(encoding='utf-8'))
        self.assertEqual(package['version'], version)
        self.assertEqual((lock['name'], lock['version']), (package['name'], version))
        self.assertEqual(lock['packages']['']['version'], version)

    def test_studio_language_client_reports_the_identity_version(self):
        self.assertIs(lsp.APP_VERSION, identity.APP_VERSION)
        source = Path(lsp.__file__).read_text(encoding='utf-8')
        self.assertIn('"clientInfo": {"name": "OLIVE Studio", "version": APP_VERSION}', source)
        self.assertIsNone(re.search(r'"clientInfo":\s*\{[^}]*"version":\s*"', source))

    def test_backup_format_is_not_tied_to_the_product_version(self):
        self.assertEqual(backup_service.BACKUP_FORMAT_VERSION, 1)


if __name__ == '__main__':
    unittest.main()
