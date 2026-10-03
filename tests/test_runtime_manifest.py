"""runtime_manifest/1.0.0.json: real, verified entries only; everything else disabled with a reason."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from olive.services import runtime_manifest
from olive.services.model_policy import DEFAULT_EMBEDDING_MODEL, CANDIDATES
from olive.services.presets import PRESETS

ROOT = Path(__file__).resolve().parents[1]


class RuntimeManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = runtime_manifest.load('1.0.0', environ={})

    def by_id(self, identifier, manifest=None):
        return next(e for e in (manifest or self.manifest)['entries'] if e['id'] == identifier)

    def test_installable_entries_per_platform(self):
        models = {'qwen3-8b', 'gpt-oss-20b', 'qwen3.5-9b', 'qwen3-embedding-0.6b', 'qwen3-vl-8b', 'qwen3-coder-30b',
                  'playwright-1.63.0'}
        self.assertEqual({e['id'] for e in runtime_manifest.installable('linux-x86_64', environ={})},
                         models | {'ollama-0.34.2-linux-x86_64'})
        self.assertEqual({e['id'] for e in runtime_manifest.installable('windows-x86_64', environ={})},
                         models | {'ollama-0.34.2-windows-x86_64'})
        # macOS: no bundled Ollama until validated on a Mac; the official app is used instead.
        self.assertEqual({e['id'] for e in runtime_manifest.installable('macos-arm64', environ={})}, models)
        self.assertEqual(self.by_id('ollama-macos-app')['kind'], 'external')

    def test_every_enabled_entry_is_https_pinned_and_licence_reviewed(self):
        for entry in self.manifest['entries']:
            if not entry['enabled']:
                self.assertTrue(entry['reason'], entry['id'])
                continue
            self.assertTrue(entry['licence']['reviewed'] and entry['licence']['spdx'], entry['id'])
            self.assertFalse(entry['licence']['acceptance_required'], entry['id'])
            for target in entry['platforms']:
                for item in runtime_manifest.files_for(entry, target):
                    self.assertTrue(item['url'].startswith('https://'), item)
                    self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')
            if entry['kind'] == 'ollama-model':
                self.assertTrue(entry['source']['url'].startswith('https://registry.ollama.ai/v2/'))
                self.assertRegex(entry['ollama']['manifest_digest'], r'^[0-9a-f]{64}$')

    def test_presets_and_manifest_name_the_same_models(self):
        model = lambda slot: next(e['ollama']['model'] for e in self.manifest['entries']
                                  if e['provides'] == slot and e.get('ollama'))
        self.assertEqual(model('model-fast'), PRESETS['fast']['model'])
        self.assertEqual(model('model-normal'), PRESETS['normal']['model'])
        self.assertEqual(model('model-normal'), PRESETS['deep']['model'])
        self.assertEqual(model('model-now'), PRESETS['now']['model'])
        self.assertEqual(model('model-embedding'), DEFAULT_EMBEDDING_MODEL)
        self.assertEqual(model('model-vision'), CANDIDATES['vision'][0])
        self.assertEqual(model('model-coding'), CANDIDATES['coding'][0])
        max_entry = self.by_id('max-qwen3.8-27b-uncensored')
        self.assertEqual(max_entry['ollama']['model'], PRESETS['max']['model'])
        self.assertEqual(max_entry['ollama']['manifest_digest'], PRESETS['max']['pinned_digest'])
        self.assertFalse(max_entry['enabled'])

    def test_profiles_derive_from_features(self):
        core = {f['id'] for f in runtime_manifest.profile_features(self.manifest, 'core')}
        creator = {f['id'] for f in runtime_manifest.profile_features(self.manifest, 'creator')}
        complete = {f['id'] for f in runtime_manifest.profile_features(self.manifest, 'complete')}
        self.assertEqual(core, {'fast', 'normal', 'now', 'deep', 'agent_workspace', 'notes', 'draw', 'connect',
                                'connect_world'})
        self.assertEqual(creator - core, {'reimagine', 'audio', 'video', 'image_to_video', 'long_video'})
        self.assertEqual(complete - creator, {'max', 'uncensored', 'vision', 'advanced_coding', 'browser_automation'})
        with self.assertRaises(ValueError):
            runtime_manifest.profile_features(self.manifest, 'pro')

    def test_creator_components_stay_disabled_until_proven(self):
        for slot in ('image-engine', 'video-engine', 'audio-engine', 'image-model', 'video-model', 'audio-model',
                     'video-gguf-loader', 'ffmpeg', 'model-max', 'model-uncensored'):
            for entry in runtime_manifest.providers(self.manifest, slot, None):
                self.assertFalse(entry['enabled'], entry['id'])
                self.assertTrue(entry['reason'], entry['id'])

    def test_private_and_excluded_models_never_enter_a_profile(self):
        text = json.dumps([e for e in self.manifest['entries'] if e['enabled']])
        self.assertNotRegex(text, r'olive-(uncensored|eval)')
        self.assertNotIn('qwen_image', text.lower())
        self.assertNotIn('qwen-image', text.lower())
        bad = copy.deepcopy(self.manifest)
        self.by_id('qwen3-8b', bad)['ollama']['model'] = 'olive-uncensored-qwen38-hauhau:latest'
        self.assertIn('qwen3-8b names a private olive-* Ollama tag', runtime_manifest.validate(bad))

    def test_enabling_an_unresolved_entry_is_rejected(self):
        for identifier in ('sdxl-base-1.0', 'flux2-klein-9b', 'voicestudio', 'max-qwen3.8-27b-uncensored'):
            broken = copy.deepcopy(self.manifest)
            self.by_id(identifier, broken)['enabled'] = True
            self.assertTrue(runtime_manifest.validate(broken), identifier)
        external = copy.deepcopy(self.manifest)
        self.by_id('ffmpeg-system', external)['enabled'] = True
        self.assertIn('ffmpeg-system is external and cannot be enabled', runtime_manifest.validate(external))

    def test_source_policy(self):
        bad = copy.deepcopy(self.manifest)
        entry = self.by_id('ollama-0.34.2-linux-x86_64', bad)
        entry['source']['url'] = entry['source']['url'].replace('https://', 'http://')
        self.assertTrue(runtime_manifest.validate(bad))
        hosts = copy.deepcopy(self.manifest)
        self.by_id('ollama-0.34.2-linux-x86_64', hosts)['source']['hosts'] = ['example.com']
        self.assertTrue(runtime_manifest.validate(hosts))
        outside = copy.deepcopy(self.manifest)
        self.by_id('ollama-0.34.2-linux-x86_64', outside)['install']['destination'] = '../../.bashrc.d'
        self.assertTrue(runtime_manifest.validate(outside))
        self.assertFalse(runtime_manifest.url_allowed('http://127.0.0.1:8000/x', ['127.0.0.1']))
        self.assertTrue(runtime_manifest.url_allowed('http://127.0.0.1:8000/x', [], allow_loopback_http=True))
        self.assertFalse(runtime_manifest.url_allowed('http://192.0.2.1/x', [], allow_loopback_http=True))

    def test_loopback_fixtures_need_both_the_manifest_flag_and_the_environment(self):
        fixture = {'fixture': True}
        self.assertFalse(runtime_manifest.loopback_allowed(fixture, {}))
        self.assertFalse(runtime_manifest.loopback_allowed({}, {runtime_manifest.LOOPBACK_VARIABLE: '1'}))
        self.assertTrue(runtime_manifest.loopback_allowed(fixture, {runtime_manifest.LOOPBACK_VARIABLE: '1'}))
        self.assertEqual(self.manifest['_source'], 'release')
        self.assertNotIn('fixture', self.manifest)

    def test_playwright_is_optional_and_only_its_driver_is_executable(self):
        playwright = self.by_id('playwright-1.63.0')
        self.assertEqual(playwright['install']['executables'], ['playwright/driver/node'])
        feature = next(f for f in self.manifest['features'] if f['id'] == 'browser_automation')
        self.assertTrue(feature['optional_component'])
        self.assertEqual(feature['profile'], 'complete')
        core_slots = {s for f in runtime_manifest.profile_features(self.manifest, 'core') for s in f['requires']}
        self.assertNotIn('playwright', core_slots)

    def test_windows_runtime_is_installable_but_not_claimed_validated(self):
        self.assertEqual(self.by_id('ollama-0.34.2-windows-x86_64')['validated_platforms'], [])
        public = runtime_manifest.public_entry(self.by_id('ollama-0.34.2-windows-x86_64'), 'windows-x86_64')
        self.assertTrue(public['installable'])
        self.assertFalse(public['validated'])

    def test_recorded_sources_agree_with_repository_records(self):
        spec = importlib.util.spec_from_file_location('install_approved_media', ROOT / 'scripts/install_approved_media.py')
        media = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(media)
        recorded = {url: (size, sha) for _, size, sha, url in media.ARTIFACTS.values()}
        for entry in self.manifest['entries']:
            url = entry['source'].get('url')
            if url in recorded:
                self.assertEqual((entry['size_bytes'], entry['sha256']), recorded[url], entry['id'])

    def test_platform_targets(self):
        self.assertEqual(runtime_manifest.platform_target('linux', 'x86_64'), 'linux-x86_64')
        self.assertEqual(runtime_manifest.platform_target('win32', 'AMD64'), 'windows-x86_64')
        self.assertEqual(runtime_manifest.platform_target('darwin', 'arm64'), 'macos-arm64')
        self.assertIsNone(runtime_manifest.platform_target('darwin', 'x86_64'))  # Intel Macs are unsupported.
        self.assertIsNone(runtime_manifest.platform_target('linux', 'aarch64'))

    def test_schema_file_names_the_same_schema(self):
        schema = json.loads((runtime_manifest.DIRECTORY / 'schema.json').read_text())
        self.assertEqual(schema['$id'], runtime_manifest.SCHEMA)


if __name__ == '__main__':
    unittest.main()
