"""runtime_manifest/1.0.0.json: an API boundary only; nothing unresolved is installable."""
import copy
import importlib.util
from pathlib import Path
import unittest

from olive.services import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = runtime_manifest.load('1.0.0')

    def test_nothing_is_installable_yet(self):
        self.assertFalse([e['id'] for e in self.manifest['entries'] if e['enabled']])
        for target in ('linux-x86_64', 'windows-x86_64', 'macos-arm64'):
            self.assertEqual(runtime_manifest.installable(target), [])

    def test_enabling_an_unresolved_entry_is_rejected(self):
        broken = copy.deepcopy(self.manifest)
        broken['entries'][0]['enabled'] = True
        self.assertTrue(runtime_manifest.validate(broken))
        complete = copy.deepcopy(self.manifest)
        sdxl = next(e for e in complete['entries'] if e['id'] == 'sdxl-base-1.0')
        sdxl['enabled'] = True
        self.assertIn('sdxl-base-1.0 is enabled without source, checksum, size and reviewed licence',
                      runtime_manifest.validate(complete))  # Licence not reviewed yet.

    def test_recorded_sources_come_from_repository_records(self):
        spec = importlib.util.spec_from_file_location('install_approved_media', ROOT / 'scripts/install_approved_media.py')
        media = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(media)
        recorded = {url: (size, sha) for _, size, sha, url in media.ARTIFACTS.values()}
        for entry in self.manifest['entries']:
            url = entry['source']['url']
            if url is None:
                self.assertIsNone(entry['sha256'])
                continue
            self.assertIn(url, recorded, entry['id'])
            self.assertEqual((entry['size_bytes'], entry['sha256']), recorded[url])

    def test_private_tags_never_enter_a_profile(self):
        for entry in self.manifest['entries']:
            self.assertNotRegex(entry['install'].get('relative_path', ''), r'olive-[a-z]')
        bad = copy.deepcopy(self.manifest)
        bad['entries'][-1]['install']['relative_path'] = 'ollama:olive-uncensored-9b'
        self.assertIn('qwen3-embedding-0.6b names a private olive-* Ollama tag', runtime_manifest.validate(bad))
        for members in self.manifest['profiles'].values():
            self.assertTrue(set(members) <= {e['id'] for e in self.manifest['entries']})

    def test_schema_file_names_the_same_schema(self):
        import json
        schema = json.loads((runtime_manifest.DIRECTORY / 'schema.json').read_text())
        self.assertEqual(schema['$id'], runtime_manifest.SCHEMA)


if __name__ == '__main__':
    unittest.main()
