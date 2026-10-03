"""runtime_manifest/1.0.0.json: real, verified entries only; everything else disabled with a reason.
Nothing is offered without an owner release approval bound to the entry's exact pins."""
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

    def approved(self, *ids, manifest=None):
        """A copy of the manifest with owner approvals for ids, as the approvals file would record them."""
        manifest = copy.deepcopy(manifest or self.manifest)
        manifest['_approvals'] = {i: {'id': i, 'fingerprint': runtime_manifest.fingerprint(self.by_id(i, manifest)),
                                      'scope': 'public-release', 'approved_by': 'test', 'date': '2026-10-03',
                                      'product_version': manifest['product_version']} for i in ids}
        return manifest

    def engineering_ready(self, target):
        return {e['id'] for e in self.manifest['entries']
                if e['enabled'] and target in e['platforms'] and runtime_manifest.complete(e, target)}

    def test_installable_entries_per_platform(self):
        models = {'qwen3-8b', 'gpt-oss-20b', 'qwen3.5-9b', 'qwen3-embedding-0.6b', 'qwen3-vl-8b', 'qwen3-coder-30b',
                  'playwright-1.63.0'}
        creator = {'flux2-klein-4b'}
        self.assertEqual(self.engineering_ready('linux-x86_64'), models | creator | {'ollama-0.34.2-linux-x86_64'})
        self.assertEqual(self.engineering_ready('windows-x86_64'), models | creator | {'ollama-0.34.2-windows-x86_64'})
        # macOS: no bundled Ollama until validated on a Mac; the official app is used instead.
        self.assertEqual(self.engineering_ready('macos-arm64'), models)
        self.assertEqual(self.by_id('ollama-macos-app')['kind'], 'external')
        # The shipped build records no owner release approval yet, so setup offers nothing.
        for target in runtime_manifest.TARGETS:
            self.assertEqual(runtime_manifest.installable(target, environ={}), [], target)
        everything = self.approved(*self.engineering_ready('linux-x86_64'))
        self.assertEqual({e['id'] for e in runtime_manifest.installable('linux-x86_64', manifest=everything)},
                         self.engineering_ready('linux-x86_64'))

    def test_engineering_evidence_alone_never_enters_an_install_plan(self):
        entry = self.by_id('qwen3-8b')
        self.assertTrue(entry['licence']['identified'] and entry['licence']['engineering_reviewed'])
        self.assertEqual(runtime_manifest.release_state(entry, self.manifest), 'engineering_reviewed')
        self.assertFalse(runtime_manifest.offerable(entry, 'linux-x86_64', self.manifest))
        self.assertNotIn('qwen3-8b', {e['id'] for e in runtime_manifest.installable('linux-x86_64', manifest=self.manifest)})
        public = runtime_manifest.public_entry(entry, 'linux-x86_64', manifest=self.manifest)
        self.assertFalse(public['installable'])
        self.assertEqual(public['release_state'], 'engineering_reviewed')
        self.assertEqual(public['reason'], runtime_manifest.AWAITING_APPROVAL)
        approved = self.approved('qwen3-8b')
        self.assertEqual(runtime_manifest.release_state(self.by_id('qwen3-8b', approved), approved), 'release_approved')
        self.assertTrue(runtime_manifest.offerable(self.by_id('qwen3-8b', approved), 'linux-x86_64', approved))

    def test_an_approval_is_bound_to_the_exact_pins(self):
        approved = self.approved('qwen3-8b', 'flux2-klein-4b')
        changed = copy.deepcopy(approved)
        self.by_id('qwen3-8b', changed)['ollama']['manifest_digest'] = 'f' * 64
        self.by_id('flux2-klein-4b', changed)['files']['any'][0]['sha256'] = 'e' * 64
        for identifier in ('qwen3-8b', 'flux2-klein-4b'):
            self.assertFalse(runtime_manifest.offerable(self.by_id(identifier, changed), 'linux-x86_64', changed), identifier)
            self.assertEqual(runtime_manifest.release_state(self.by_id(identifier, changed), changed), 'engineering_reviewed')
        relicensed = copy.deepcopy(approved)
        self.by_id('qwen3-8b', relicensed)['licence']['spdx'] = 'LicenseRef-Other'
        self.assertFalse(runtime_manifest.release_approved(self.by_id('qwen3-8b', relicensed), relicensed))
        other_release = copy.deepcopy(approved)
        other_release['_approvals']['qwen3-8b']['product_version'] = '1.0.1'
        self.assertFalse(runtime_manifest.release_approved(self.by_id('qwen3-8b', other_release), other_release))

    def test_an_approval_never_bypasses_missing_evidence(self):
        for identifier in ('comfyui-0.35.0-image-linux', 'ltx-2.3-video', 'max-qwen3.8-27b-uncensored', 'omnivoice'):
            approved = self.approved(identifier)
            entry = self.by_id(identifier, approved)
            self.assertFalse(runtime_manifest.offerable(entry, 'linux-x86_64', approved), identifier)
        unreviewed = self.approved('qwen3-8b')
        self.by_id('qwen3-8b', unreviewed)['licence']['engineering_reviewed'] = False
        self.assertFalse(runtime_manifest.offerable(self.by_id('qwen3-8b', unreviewed), 'linux-x86_64', unreviewed))
        self.assertTrue(runtime_manifest.validate(unreviewed))  # Enabled without engineering review is invalid.
        unidentified = copy.deepcopy(self.manifest)
        self.by_id('qwen3-8b', unidentified)['licence']['identified'] = False
        self.assertIn('qwen3-8b is engineering-reviewed without an identified licence', runtime_manifest.validate(unidentified))
        self.assertEqual(runtime_manifest.release_state(self.by_id('qwen3-8b', unidentified)), 'unidentified')

    def test_approvals_live_outside_the_manifest(self):
        approvals = json.loads(runtime_manifest.approvals_path('1.0.0').read_text())
        self.assertEqual(runtime_manifest.validate_approvals(approvals), [])
        self.assertEqual(approvals['approvals'], [])  # No owner approval has been recorded yet.
        self.assertEqual(self.manifest['_approvals'], {})
        raw = json.loads((runtime_manifest.DIRECTORY / '1.0.0.json').read_text())
        raw['release_approvals'] = []
        self.assertTrue(runtime_manifest.validate(raw, release=True))
        self.assertIn('only fixture manifests may carry inline release approvals', runtime_manifest.validate(raw))
        ambiguous = copy.deepcopy(raw)
        del ambiguous['release_approvals']
        ambiguous['entries'][0]['licence']['reviewed'] = True
        self.assertTrue(any('ambiguous licence flag' in p for p in runtime_manifest.validate(ambiguous)))
        bad = {'schema': runtime_manifest.APPROVALS_SCHEMA, 'approvals': [{'id': 'qwen3-8b', 'fingerprint': 'x'}]}
        self.assertTrue(runtime_manifest.validate_approvals(bad))

    def test_every_enabled_entry_is_https_pinned_and_licence_reviewed(self):
        for entry in self.manifest['entries']:
            self.assertNotIn('reviewed', entry['licence'], entry['id'])
            if not entry['enabled']:
                self.assertTrue(entry['reason'], entry['id'])
                continue
            licence = entry['licence']
            self.assertTrue(licence['identified'] and licence['engineering_reviewed'] and licence['spdx'], entry['id'])
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
                if entry['id'] == 'flux2-klein-4b':
                    continue  # The one Creator model with complete evidence (still unapproved).
                self.assertFalse(entry['enabled'], entry['id'])
                self.assertTrue(entry['reason'], entry['id'])
        # No engine is installable, so no Creator feature can be offered even with every approval.
        everything = self.approved(*self.engineering_ready('linux-x86_64'))
        for slot in ('image-engine', 'video-engine', 'audio-engine'):
            self.assertFalse([e for e in runtime_manifest.providers(everything, slot, 'linux-x86_64')
                              if runtime_manifest.offerable(e, 'linux-x86_64', everything)], slot)

    def test_distributable_image_path_is_flux2_klein_4b(self):
        from olive.services.media_workflows import WORKFLOWS
        entry = self.by_id('flux2-klein-4b')
        self.assertEqual(entry['licence']['spdx'], 'Apache-2.0')
        self.assertFalse(entry['licence']['acceptance_required'])
        files = entry['files']['any']
        self.assertEqual(sum(f['size_bytes'] for f in files), entry['install']['installed_bytes'])
        for item in files:
            self.assertRegex(item['url'], r'^https://huggingface\.co/[^/]+/[^/]+/resolve/[0-9a-f]{40}/')
            self.assertTrue(runtime_manifest.url_allowed(item['url'], entry['source']['hosts']))
        workflow = WORKFLOWS['flux2-klein-4b']
        # Each file lands in the ComfyUI folder its loader searches, under the exact name the workflow names.
        self.assertEqual({f['path'] for f in files}, {'diffusion_models/' + workflow.files[('UNETLoader', 'unet_name')],
                                                       'text_encoders/' + workflow.files[('CLIPLoader', 'clip_name')],
                                                       'vae/' + workflow.files[('VAELoader', 'vae_name')]})
        self.assertEqual(self.by_id('flux2-klein-9b')['licence']['distribution'], 'user-supplied')
        self.assertFalse(self.by_id('flux2-klein-9b')['enabled'])

    def test_non_commercial_and_community_creator_files_are_never_offered(self):
        for identifier in ('flux2-klein-9b', 'ltx-2.3-video', 'omnivoice', 'voicestudio'):
            entry = self.by_id(identifier)
            approved = self.approved(identifier)
            self.assertFalse(runtime_manifest.offerable(self.by_id(identifier, approved), 'linux-x86_64', approved), identifier)
            self.assertTrue(entry['reason'], identifier)
        self.assertIn('CC-BY-NC', self.by_id('omnivoice')['licence']['spdx'])
        self.assertEqual(self.by_id('voicestudio')['kind'], 'external')
        official = self.by_id('ltx-2.3-official-fp8')
        self.assertTrue(official['licence']['acceptance_required'])
        self.assertNotIn('abliterated', json.dumps(official['files']))

    def test_private_and_excluded_models_never_enter_a_profile(self):
        text = json.dumps([e for e in self.manifest['entries'] if e['enabled']])
        self.assertNotRegex(text, r'olive-(uncensored|eval)')
        self.assertNotIn('qwen_image', text.lower())
        self.assertNotIn('qwen-image', text.lower())
        bad = copy.deepcopy(self.manifest)
        self.by_id('qwen3-8b', bad)['ollama']['model'] = 'olive-uncensored-qwen38-hauhau:latest'
        self.assertIn('qwen3-8b names a private olive-* Ollama tag', runtime_manifest.validate(bad))

    def test_enabling_an_unresolved_entry_is_rejected(self):
        for identifier in ('flux2-klein-9b', 'voicestudio', 'max-qwen3.8-27b-uncensored', 'comfyui-0.35.0-image-linux',
                           'ltx-2.3-video'):
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
        approved = self.approved('ollama-0.34.2-windows-x86_64')
        public = runtime_manifest.public_entry(self.by_id('ollama-0.34.2-windows-x86_64', approved), 'windows-x86_64',
                                               manifest=approved)
        self.assertTrue(public['installable'])
        self.assertFalse(public['validated'])

    def test_recorded_sources_agree_with_repository_records(self):
        spec = importlib.util.spec_from_file_location('install_approved_media', ROOT / 'scripts/install_approved_media.py')
        media = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(media)
        recorded = {name: (size, sha) for name, size, sha, _ in media.ARTIFACTS.values()}
        compared = 0
        for entry in self.manifest['entries']:
            name = (entry['source'].get('url') or '').rsplit('/', 1)[-1]
            if name in recorded and entry.get('sha256'):
                self.assertEqual((entry['size_bytes'], entry['sha256']), recorded[name], entry['id'])
                compared += 1
        self.assertEqual(compared, 2)

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
