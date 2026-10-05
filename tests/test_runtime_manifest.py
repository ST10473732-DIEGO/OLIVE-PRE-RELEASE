"""runtime_manifest/1.0.0.json: real, verified entries only; everything else disabled with a reason.
Nothing is offered without an owner release approval bound to the entry's exact pins."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from olive.services import runtime_manifest
from olive.services.model_policy import DEFAULT_EMBEDDING_MODEL, CANDIDATES
from olive.services.presets import PRESETS

ROOT = Path(__file__).resolve().parents[1]


class RuntimeManifestTests(unittest.TestCase):
    # The owner's current decisions in release-approvals-1.0.0.json. Change this only together with
    # that file; generic gate tests never depend on it and build their own approval state.
    SHIPPED_APPROVALS = {'ollama-0.34.2-linux-x86_64', 'qwen3-8b', 'gpt-oss-20b', 'qwen3.5-9b', 'qwen3-embedding-0.6b',
                         'flux2-klein-4b', 'comfyui-0.35.0-image-linux'}

    def setUp(self):
        self.manifest = runtime_manifest.load('1.0.0', environ={})

    def by_id(self, identifier, manifest=None):
        return next(e for e in (manifest or self.manifest)['entries'] if e['id'] == identifier)

    def unapproved(self, manifest=None):
        """A copy of the manifest with no owner approvals: engineering evidence alone."""
        manifest = copy.deepcopy(manifest or self.manifest)
        manifest['_approvals'] = {}
        return manifest

    def approved(self, *ids, manifest=None):
        """A copy of the manifest with owner approvals for exactly ids (replacing any others), as the
        approvals file would record them."""
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
        image_engine = {'comfyui-0.35.0-image-linux'}  # Published for Linux only.
        self.assertEqual(self.engineering_ready('linux-x86_64'),
                         models | creator | image_engine | {'ollama-0.34.2-linux-x86_64'})
        self.assertEqual(self.engineering_ready('windows-x86_64'), models | creator | {'ollama-0.34.2-windows-x86_64'})
        # macOS: no bundled Ollama until validated on a Mac; the official app is used instead.
        self.assertEqual(self.engineering_ready('macos-arm64'), models)
        self.assertEqual(self.by_id('ollama-macos-app')['kind'], 'external')
        # Engineering evidence alone offers nothing anywhere.
        bare = self.unapproved()
        for target in runtime_manifest.TARGETS:
            self.assertEqual(runtime_manifest.installable(target, manifest=bare), [], target)
        everything = self.approved(*self.engineering_ready('linux-x86_64'))
        self.assertEqual({e['id'] for e in runtime_manifest.installable('linux-x86_64', manifest=everything)},
                         self.engineering_ready('linux-x86_64'))

    def test_engineering_evidence_alone_never_enters_an_install_plan(self):
        bare = self.unapproved()
        entry = self.by_id('qwen3-8b', bare)
        self.assertTrue(entry['enabled'] and entry['licence']['identified'] and entry['licence']['engineering_reviewed'])
        self.assertEqual(runtime_manifest.release_state(entry, bare), 'engineering_reviewed')
        self.assertFalse(runtime_manifest.release_approved(entry, bare))
        for target in entry['platforms']:
            self.assertTrue(runtime_manifest.complete(entry, target), target)
            self.assertFalse(runtime_manifest.offerable(entry, target, bare), target)
            self.assertNotIn('qwen3-8b', {e['id'] for e in runtime_manifest.installable(target, manifest=bare)}, target)
            public = runtime_manifest.public_entry(entry, target, manifest=bare)
            self.assertFalse(public['installable'])
            self.assertEqual(public['release_state'], 'engineering_reviewed')
            self.assertEqual(public['reason'], runtime_manifest.AWAITING_APPROVAL)
        approved = self.approved('qwen3-8b', manifest=bare)
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
        next_release = copy.deepcopy(approved)
        next_release['product_version'] = '1.0.1'  # An approval for 1.0.0 does not carry into another release.
        self.assertFalse(runtime_manifest.release_approved(self.by_id('qwen3-8b', next_release), next_release))

    def test_an_approval_never_bypasses_missing_evidence(self):
        for identifier in ('comfyui-0.35.0-video-linux', 'ltx-2.3-video', 'max-qwen3.8-27b-uncensored', 'omnivoice'):
            approved = self.approved(identifier)
            entry = self.by_id(identifier, approved)
            self.assertFalse(runtime_manifest.offerable(entry, 'linux-x86_64', approved), identifier)
        unhosted = copy.deepcopy(self.manifest)  # Approved archive whose download URL is gone.
        self.by_id('comfyui-0.35.0-image-linux', unhosted)['source']['url'] = None
        unhosted = self.approved('comfyui-0.35.0-image-linux', manifest=unhosted)
        self.assertFalse(runtime_manifest.offerable(self.by_id('comfyui-0.35.0-image-linux', unhosted), 'linux-x86_64',
                                                    unhosted))
        unreviewed = self.approved('qwen3-8b')
        self.by_id('qwen3-8b', unreviewed)['licence']['engineering_reviewed'] = False
        self.assertFalse(runtime_manifest.offerable(self.by_id('qwen3-8b', unreviewed), 'linux-x86_64', unreviewed))
        self.assertTrue(runtime_manifest.validate(unreviewed))  # Enabled without engineering review is invalid.
        unidentified = copy.deepcopy(self.manifest)
        self.by_id('qwen3-8b', unidentified)['licence']['identified'] = False
        self.assertIn('qwen3-8b is engineering-reviewed without an identified licence', runtime_manifest.validate(unidentified))
        self.assertEqual(runtime_manifest.release_state(self.by_id('qwen3-8b', unidentified)), 'unidentified')

    def test_approvals_live_outside_the_manifest(self):
        path = runtime_manifest.approvals_path('1.0.0')
        self.assertEqual(path, runtime_manifest.DIRECTORY / 'release-approvals-1.0.0.json')
        document = json.loads(path.read_text())
        self.assertEqual(runtime_manifest.validate_approvals(document), [])
        self.assertEqual(document['schema'], runtime_manifest.APPROVALS_SCHEMA)
        self.assertEqual(document['product_version'], self.manifest['product_version'])
        records = document['approvals']
        ids = [r['id'] for r in records]
        self.assertEqual(len(ids), len(set(ids)))
        # The shipped manifest takes its approvals from that file and nowhere else.
        self.assertEqual(self.manifest['_approvals'], {r['id']: r for r in records})
        self.assertEqual(runtime_manifest.load('1.0.0', environ={runtime_manifest.LOOPBACK_VARIABLE: '1'})['_approvals'],
                         self.manifest['_approvals'])
        for record in records:  # Every recorded approval is current: a real entry, its exact pins, this release.
            entry = next((e for e in self.manifest['entries'] if e['id'] == record['id']), None)
            self.assertIsNotNone(entry, record['id'])
            self.assertEqual(record['fingerprint'], runtime_manifest.fingerprint(entry), record['id'])
            self.assertEqual(record['product_version'], self.manifest['product_version'], record['id'])
            self.assertTrue(entry['enabled'] and runtime_manifest.complete(entry), record['id'])
            self.assertEqual(runtime_manifest.release_state(entry, self.manifest), 'release_approved', record['id'])
        # A duplicate approval is rejected, by validation and when loading.
        record = {'id': 'qwen3-8b', 'fingerprint': runtime_manifest.fingerprint(self.by_id('qwen3-8b')),
                  'scope': 'public-release', 'approved_by': 'test', 'date': '2026-10-03', 'product_version': '1.0.0'}
        duplicated = {**document, 'approvals': records + [record, dict(record)]}
        self.assertIn('duplicate approval for qwen3-8b', runtime_manifest.validate_approvals(duplicated))
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / 'release-approvals-1.0.0.json'
            copied.write_text(json.dumps(duplicated))
            with self.assertRaises(ValueError):
                runtime_manifest.load_approvals('1.0.0', path=copied)
        # Stale fingerprints count for nothing.
        stale = copy.deepcopy(self.manifest)
        for each in stale['_approvals'].values():
            each['fingerprint'] = 'f' * 64
        for target in runtime_manifest.TARGETS:
            self.assertEqual(runtime_manifest.installable(target, manifest=stale), [], target)
        # The shipped manifest can never approve itself, even when flagged as a fixture.
        raw = json.loads((runtime_manifest.DIRECTORY / '1.0.0.json').read_text())
        self.assertNotIn('release_approvals', raw)
        self.assertNotIn('fixture', raw)
        for entry in raw['entries']:
            self.assertNotIn('release_approved', entry, entry['id'])
            self.assertNotIn('release_approved', entry['licence'], entry['id'])
        self_approved = {**raw, 'fixture': True, 'release_approvals': [record]}
        self.assertIn('the shipped manifest cannot approve itself or be a fixture; approvals live in '
                      'release-approvals-<version>.json', runtime_manifest.validate(self_approved, release=True))
        raw['release_approvals'] = []
        self.assertTrue(runtime_manifest.validate(raw, release=True))
        self.assertIn('only fixture manifests may carry inline release approvals', runtime_manifest.validate(raw))
        ambiguous = copy.deepcopy(raw)
        del ambiguous['release_approvals']
        ambiguous['entries'][0]['licence']['reviewed'] = True
        self.assertTrue(any('ambiguous licence flag' in p for p in runtime_manifest.validate(ambiguous)))
        bad = {'schema': runtime_manifest.APPROVALS_SCHEMA, 'approvals': [{'id': 'qwen3-8b', 'fingerprint': 'x'}]}
        self.assertTrue(runtime_manifest.validate_approvals(bad))

    def test_shipped_release_offers_exactly_the_owner_approved_entries(self):
        approved = {e['id'] for e in self.manifest['entries'] if runtime_manifest.release_approved(e, self.manifest)}
        self.assertEqual(approved, self.SHIPPED_APPROVALS)
        self.assertEqual(set(self.manifest['_approvals']), self.SHIPPED_APPROVALS)
        # Where an approved entry is offered comes from the entry's own platforms, not from the approval.
        for target in runtime_manifest.TARGETS:
            expected = {i for i in self.SHIPPED_APPROVALS if target in self.by_id(i)['platforms']}
            self.assertEqual({e['id'] for e in runtime_manifest.installable(target, environ={})}, expected, target)
        self.assertEqual(self.by_id('ollama-0.34.2-linux-x86_64')['platforms'], ['linux-x86_64'])
        self.assertEqual(self.by_id('flux2-klein-4b')['platforms'], ['linux-x86_64', 'windows-x86_64'])
        self.assertEqual(self.by_id('comfyui-0.35.0-image-linux')['platforms'], ['linux-x86_64'])
        for identifier in self.SHIPPED_APPROVALS - {'ollama-0.34.2-linux-x86_64'}:
            entry = self.by_id(identifier)
            if identifier not in ('flux2-klein-4b', 'comfyui-0.35.0-image-linux'):
                self.assertEqual(set(entry['platforms']), set(runtime_manifest.TARGETS), identifier)
            for target in entry['platforms']:
                public = runtime_manifest.public_entry(entry, target, manifest=self.manifest)
                self.assertTrue(public['installable'], (identifier, target))
                self.assertEqual(public['release_state'], 'release_approved')
                # Release authorisation is not platform validation.
                self.assertEqual(public['validated'], target in entry['validated_platforms'], (identifier, target))
        self.assertFalse(runtime_manifest.public_entry(self.by_id('qwen3-8b'), 'windows-x86_64',
                                                       manifest=self.manifest)['validated'])
        # Everything else stays unapproved and is never offered on any platform.
        unapproved = {'ollama-0.34.2-windows-x86_64', 'qwen3-vl-8b', 'qwen3-coder-30b', 'playwright-1.63.0',
                      'voicestudio', 'omnivoice'}
        unapproved |= {e['id'] for e in self.manifest['entries']
                       if e['id'].startswith('ltx-') or e['provides'] in {
                           'image-engine', 'video-engine', 'audio-engine', 'video-gguf-loader', 'ffmpeg',
                           'model-max', 'model-uncensored'}}
        unapproved -= {'comfyui-0.35.0-image-linux'}  # The one approved engine (Linux image runtime).
        self.assertTrue({'comfyui-0.35.0-video-linux', 'comfyui-windows-portable-0.35.0',
                         'comfyui-gguf-loader', 'ltx-2.3-video', 'ltx-2.3-official-fp8', 'max-qwen3.8-27b-uncensored',
                         'uncensored-routing-set'} <= unapproved)
        for identifier in sorted(unapproved):
            entry = self.by_id(identifier)
            self.assertNotIn(identifier, self.manifest['_approvals'])
            self.assertFalse(runtime_manifest.release_approved(entry, self.manifest), identifier)
            self.assertNotEqual(runtime_manifest.release_state(entry, self.manifest), 'release_approved', identifier)
            for target in runtime_manifest.TARGETS:
                self.assertFalse(runtime_manifest.offerable(entry, target, self.manifest), (identifier, target))
        # A pin change voids a real owner approval just as it voids a fixture one.
        repinned = copy.deepcopy(self.manifest)
        self.by_id('qwen3-8b', repinned)['ollama']['manifest_digest'] = 'f' * 64
        self.assertEqual(runtime_manifest.release_state(self.by_id('qwen3-8b', repinned), repinned), 'engineering_reviewed')
        self.assertNotIn('qwen3-8b', {e['id'] for e in runtime_manifest.installable('linux-x86_64', manifest=repinned)})

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
                if entry['id'] in ('flux2-klein-4b', 'comfyui-0.35.0-image-linux'):
                    continue  # The published Linux image engine and its model.
                self.assertFalse(entry['enabled'], entry['id'])
                self.assertTrue(entry['reason'], entry['id'])
        # Only the Linux image engine is installable; no video or audio engine is, even with every approval.
        everything = self.approved(*(self.engineering_ready('linux-x86_64') | self.engineering_ready('windows-x86_64')))
        offered = lambda slot, target: {e['id'] for e in runtime_manifest.providers(everything, slot, target)
                                        if runtime_manifest.offerable(e, target, everything)}
        self.assertEqual(offered('image-engine', 'linux-x86_64'), {'comfyui-0.35.0-image-linux'})
        for target in ('windows-x86_64', 'macos-arm64'):
            self.assertEqual(offered('image-engine', target), set(), target)
        for slot in ('video-engine', 'audio-engine'):
            for target in runtime_manifest.TARGETS:
                self.assertEqual(offered(slot, target), set(), (slot, target))

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
        for identifier in ('flux2-klein-9b', 'voicestudio', 'max-qwen3.8-27b-uncensored', 'comfyui-0.35.0-video-linux',
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
