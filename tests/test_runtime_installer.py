"""First-run installer against local fixture servers: plans, space, downloads, pulls, repair, uninstall."""
import asyncio
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from olive.services import runtime_manifest
from olive.services.runtime_discovery import RuntimeDiscovery
from olive.services.runtime_installer import MARKER, InstallError, RuntimeInstaller
from olive.storage.runtime_config_repository import RuntimeConfigRepository
from olive.storage.setup_state_repository import SetupStateRepository
from tests.setup_installer_fixture import FakeOllama, FileServer, approve, fixture_manifest, tar_bytes, zip_bytes

OLLAMA_SCRIPT = b'#!/bin/sh\necho fixture\n'
TARGET = 'linux-x86_64'


class Disk:
    def __init__(self, free):
        self.free = free

    def __call__(self, path):
        return type('Usage', (), {'free': self.free, 'total': self.free * 2, 'used': 0})()


class InstallerTestCase(unittest.IsolatedAsyncioTestCase):
    wheels = None

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.profile = self.root / 'profile'
        self.home.mkdir()
        self.profile.mkdir()
        self.env = {'XDG_DATA_HOME': str(self.root / 'xdg'), 'OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP': '1'}
        self.files = FileServer().__enter__()
        self.ollama = FakeOllama().__enter__()
        self.archive = tar_bytes({'bin/ollama': OLLAMA_SCRIPT, 'lib/ollama/libggml.so.0': b'elf'},
                                 links={'lib/ollama/libggml.so': 'libggml.so.0'},
                                 executable={'bin/ollama', 'lib/ollama/libggml.so.0'})
        self.manifest_value = fixture_manifest(self.files, self.ollama, self.archive, wheels=self.wheels)
        self.manifest_path = self.root / 'manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.disk = Disk(10 ** 12)
        self.registered = []
        self.installer = self.make()

    def make(self):
        discovery = RuntimeDiscovery(self.profile, environ=self.env, platform='linux', home=self.home,
                                     install_root=self.root / 'install', which=lambda name: None)
        manifest = runtime_manifest.load(environ=self.env, path=self.manifest_path)
        installer = RuntimeInstaller(self.profile, discovery, ollama_host=self.ollama.base, environ=self.env,
                                     platform='linux', home=self.home, target=TARGET, manifest=manifest,
                                     disk_usage=self.disk, runtime_registered=lambda n, l: self.registered.append((n, l)))
        installer.module_available = lambda name: False
        return installer

    async def asyncTearDown(self):
        await self.installer.close()
        await asyncio.to_thread(self.files.__exit__, None, None, None)
        await asyncio.to_thread(self.ollama.__exit__, None, None, None)
        self.temp.cleanup()

    @property
    def data_root(self):
        return self.root / 'xdg' / 'olive'

    async def run_job(self, profile='core', entries=None):
        if entries is None:
            entries = (await self.installer.plan(profile))['default']
        job = await self.installer.start(profile, entries)
        await self.installer.jobs[job['job_id']].task
        return self.installer.progress(job['job_id'])


class PlanTests(InstallerTestCase):
    async def test_core_plan_comes_from_the_manifest(self):
        plan = await self.installer.plan('core')
        states = {f['id']: f['state'] for f in plan['features']}
        self.assertEqual(states['fast'], 'installable')
        self.assertEqual(states['notes'], 'ready')
        self.assertEqual(states['connect_world'], 'ready')
        self.assertNotIn('reimagine', states)
        self.assertEqual(set(plan['default']), {'fixture-ollama', 'fixture-model-fast', 'fixture-model-normal',
                                                'fixture-model-now', 'fixture-model-embedding'})
        self.assertEqual(plan['totals']['download_bytes'], len(self.archive) + 4 * 500)
        self.assertFalse(plan['some_unavailable'])
        self.assertTrue(plan['totals']['enough_space'])

    async def test_creator_and_complete_report_components_not_in_this_build(self):
        creator = await self.installer.plan('creator')
        states = {f['id']: f['state'] for f in creator['features']}
        for feature in ('reimagine', 'audio', 'video', 'image_to_video', 'long_video'):
            self.assertIn(states[feature], {'not_in_build', 'external'}, feature)
        self.assertTrue(creator['some_unavailable'])
        self.assertEqual(states['fast'], 'installable')  # Creator includes Core.
        complete = await self.installer.plan('complete')
        states = {f['id']: f['state'] for f in complete['features']}
        self.assertEqual(states['max'], 'not_in_build')
        self.assertEqual(states['uncensored'], 'not_in_build')
        # Nothing unavailable is ever offered for installation.
        offered = {row['entry']['id'] for row in complete['items'] if row['action'] == 'install'}
        self.assertTrue(all(i.startswith('fixture-') for i in offered))

    async def test_existing_models_are_reported_and_never_replaced(self):
        model = self.manifest_value['entries'][1]
        self.ollama.models['qwen3:8b'] = model['ollama']['manifest_digest']
        self.ollama.models['gpt-oss:20b'] = 'f' * 64
        plan = await self.installer.plan('core')
        actions = {row['slot']: row['action'] for row in plan['items']}
        self.assertEqual(actions['model-fast'], 'present')
        self.assertEqual(actions['model-normal'], 'different_build')
        self.assertNotIn('fixture-model-fast', plan['default'])
        self.assertNotIn('fixture-model-normal', plan['default'])

    async def test_disk_space_refusal(self):
        self.disk.free = 1000
        plan = await self.installer.plan('core')
        self.assertFalse(plan['totals']['enough_space'])
        with self.assertRaises(InstallError) as caught:
            await self.installer.start('core', plan['default'])
        self.assertEqual(caught.exception.code, 'insufficient_space')
        self.assertFalse((self.data_root / 'runtime').exists())

    async def test_only_offered_entries_can_be_started(self):
        for bad in (['release-flux2-klein-9b'], ['nonexistent'], ['release-max-qwen3.8-27b-uncensored']):
            with self.assertRaises((InstallError, ValueError)):
                await self.installer.start('complete', bad)
        with self.assertRaises(InstallError):
            await self.installer.start('core', [])

    async def test_ollama_host_must_be_local(self):
        self.installer.ollama_host = 'http://192.0.2.10:11434'
        self.assertIsNone(await self.installer.model_tags())


class InstallTests(InstallerTestCase):
    async def test_core_install_end_to_end(self):
        job = await self.run_job()
        self.assertEqual(job['state'], 'done', job)
        self.assertEqual({i['state'] for i in job['items']}, {'done'})
        executable = self.data_root / 'runtime/ollama/bin/ollama'
        self.assertEqual(executable.read_bytes(), OLLAMA_SCRIPT)
        self.assertEqual(stat.S_IMODE(executable.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.data_root / 'runtime/ollama/lib/ollama/libggml.so.0').stat().st_mode), 0o644)
        self.assertTrue((self.data_root / 'runtime/ollama' / MARKER).is_file())
        stored, _ = RuntimeConfigRepository(self.profile).load()
        self.assertEqual(stored['ollama'], {'paths': {'executable': str(executable)}, 'origin': 'olive-owned',
                                            'adopted': False})
        self.assertEqual(self.registered[0][0], 'ollama')
        state, _ = SetupStateRepository(self.profile).load()
        self.assertEqual(set(state['installed']), {'fixture-ollama', 'fixture-model-fast', 'fixture-model-normal',
                                                   'fixture-model-now', 'fixture-model-embedding'})
        self.assertTrue(state['installed']['fixture-model-fast']['installed_by_olive'])
        self.assertEqual(set(self.ollama.models), {'qwen3:8b', 'gpt-oss:20b', 'qwen3.5:9b', 'qwen3-embedding:0.6b'})
        # Temporary files are cleaned: no archive, no partial, no staging.
        leftovers = [p for p in (self.data_root / 'temp').rglob('*') if p.is_file()]
        self.assertEqual(leftovers, [])
        # Running again installs nothing new.
        plan = await self.installer.plan('core')
        self.assertEqual(plan['default'], [])
        self.assertTrue(all(f['state'] == 'ready' for f in plan['features']))

    async def test_archive_checksum_mismatch_installs_nothing(self):
        self.manifest_value['entries'][0]['sha256'] = '0' * 64
        approve(self.manifest_value, ['fixture-ollama'])  # Changed pins need a fresh fixture approval.
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()
        job = await self.run_job(entries=['fixture-ollama'])
        self.assertEqual(job['items'][0]['state'], 'failed')
        self.assertEqual(job['items'][0]['error'], 'checksum_mismatch')
        self.assertFalse((self.data_root / 'runtime/ollama').exists())
        self.assertFalse(RuntimeConfigRepository(self.profile).path.exists())

    async def test_malicious_archive_is_refused_atomically(self):
        evil = tar_bytes({'bin/ollama': OLLAMA_SCRIPT}, links={'lib': '../../../../etc'})
        self.manifest_value['entries'][0].update(sha256=__import__('hashlib').sha256(evil).hexdigest(), size_bytes=len(evil))
        self.files.files['/ollama-fixture.tar.gz'] = evil
        approve(self.manifest_value, ['fixture-ollama'])  # Changed pins need a fresh fixture approval.
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()
        job = await self.run_job(entries=['fixture-ollama'])
        self.assertEqual(job['items'][0]['error'], 'unsafe_archive')
        self.assertFalse((self.data_root / 'runtime/ollama').exists())
        self.assertEqual([p.name for p in (self.data_root / 'runtime').iterdir()], [])  # No staging left behind.

    async def test_never_replaces_a_folder_it_did_not_create(self):
        existing = self.data_root / 'runtime/ollama'
        existing.mkdir(parents=True)
        (existing / 'mine.txt').write_text('user data')
        plan = await self.installer.plan('core')
        self.assertEqual(next(r for r in plan['items'] if r['slot'] == 'ollama-runtime')['action'], 'choose')
        self.assertNotIn('fixture-ollama', plan['offered'])
        with self.assertRaises(InstallError):
            await self.installer.start('core', ['fixture-ollama'])
        self.assertEqual((existing / 'mine.txt').read_text(), 'user data')

    async def test_cancel_then_retry_resumes_the_download(self):
        import olive.services.secure_download as sd
        big = os.urandom(2 * 1024 * 1024)
        archive = tar_bytes({'bin/ollama': OLLAMA_SCRIPT, 'blob': big}, mode='w')
        self.manifest_value['entries'][0].update(sha256=__import__('hashlib').sha256(archive).hexdigest(),
                                                 size_bytes=len(archive), install={
            **self.manifest_value['entries'][0]['install'], 'format': 'tar.gz', 'installed_bytes': len(archive)})
        self.manifest_value['entries'][0]['install']['format'] = 'tar.gz'
        import gzip
        packed = gzip.compress(archive, compresslevel=0)
        self.manifest_value['entries'][0].update(sha256=__import__('hashlib').sha256(packed).hexdigest(), size_bytes=len(packed))
        self.files.files['/ollama-fixture.tar.gz'] = packed
        approve(self.manifest_value, ['fixture-ollama'])  # Changed pins need a fresh fixture approval.
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()
        self.files.slow = 0.01
        with mock.patch.object(sd, 'RANGE', 256 * 1024):
            job = await self.installer.start('core', ['fixture-ollama'])
            for _ in range(500):
                if self.installer.progress(job['job_id'])['done_bytes'] >= 300_000:
                    break
                self.assertEqual(self.installer.progress(job['job_id'])['state'], 'running')
                await asyncio.sleep(0.02)
            self.installer.cancel(job['job_id'])
            await self.installer.jobs[job['job_id']].task
            cancelled = self.installer.progress(job['job_id'])
            self.assertEqual(cancelled['state'], 'cancelled')
            self.assertEqual(cancelled['items'][0]['state'], 'cancelled')
            self.assertTrue(list((self.data_root / 'temp/downloads').glob('*.part')))
            self.files.slow = 0
            self.files.requests.clear()
            await self.installer.retry(job['job_id'])
            await self.installer.jobs[job['job_id']].task
        retried = self.installer.progress(job['job_id'])
        self.assertEqual(retried['state'], 'done')
        first = self.files.requests[0][1]
        self.assertNotEqual(first.split('=')[1].split('-')[0], '0', 'retry must resume, not restart')
        self.assertEqual((self.data_root / 'runtime/ollama/blob').read_bytes(), big)

    async def test_stale_runtime_is_repaired_by_installing(self):
        RuntimeConfigRepository(self.profile).save({'ollama': {'paths': {'executable': str(self.root / 'gone/ollama')},
                                                               'origin': 'configured'}})
        plan = await self.installer.plan('core')
        self.assertEqual(next(r for r in plan['items'] if r['slot'] == 'ollama-runtime')['action'], 'install')
        job = await self.run_job(entries=['fixture-ollama'])
        self.assertEqual(job['state'], 'done')
        located = self.installer.discovery.resolve()['ollama']
        self.assertTrue(located.found)
        self.assertEqual(located.origin, 'olive-owned')


class ModelPullTests(InstallerTestCase):
    async def test_registry_digest_change_blocks_the_pull(self):
        path = self.ollama.paths['qwen3:8b']
        self.ollama.registry[path] = self.ollama.registry[path] + b' '
        job = await self.run_job(entries=['fixture-model-fast'])
        self.assertEqual(job['items'][0]['error'], 'registry_changed')
        self.assertEqual(self.ollama.pulls, [])

    async def test_pulled_digest_mismatch_is_removed(self):
        self.ollama.serve_digest['qwen3:8b'] = 'e' * 64
        job = await self.run_job(entries=['fixture-model-fast'])
        self.assertEqual(job['items'][0]['error'], 'digest_mismatch')
        self.assertEqual(self.ollama.deleted, ['qwen3:8b'])
        state, _ = SetupStateRepository(self.profile).load()
        self.assertNotIn('fixture-model-fast', state['installed'])

    async def test_pull_error_then_retry(self):
        self.ollama.pull_error = 'pull model manifest: network unreachable'
        job = await self.run_job(entries=['fixture-model-fast'])
        self.assertEqual(job['items'][0]['error'], 'pull_failed')
        self.ollama.pull_error = None
        await self.installer.retry(job['job_id'])
        await self.installer.jobs[job['job_id']].task
        self.assertEqual(self.installer.progress(job['job_id'])['state'], 'done')

    async def test_cancel_a_model_pull(self):
        self.ollama.pull_delay = 0.2
        job = await self.installer.start('core', ['fixture-model-fast'])
        for _ in range(250):
            if self.ollama.pulls:
                break
            await asyncio.sleep(0.02)
        self.installer.cancel(job['job_id'])
        await self.installer.jobs[job['job_id']].task
        self.assertEqual(self.installer.progress(job['job_id'])['items'][0]['state'], 'cancelled')

    async def test_no_ollama_means_a_truthful_failure(self):
        self.installer.ollama_host = 'http://127.0.0.1:9'
        job = await self.run_job(entries=['fixture-model-fast'])
        self.assertEqual(job['items'][0]['error'], 'ollama_unavailable')

    async def test_uninstall_removes_only_models_olive_installed(self):
        await self.run_job(entries=['fixture-model-fast'])
        self.ollama.models['gpt-oss:20b'] = 'f' * 64  # The person's own model.
        with self.assertRaises(InstallError):
            await self.installer.uninstall('fixture-model-normal')
        await self.installer.uninstall('fixture-model-fast')
        self.assertEqual(self.ollama.deleted, ['qwen3:8b'])
        self.assertIn('gpt-oss:20b', self.ollama.models)


class ComponentTests(InstallerTestCase):
    wheels = {
        'fixturecomponent-1.0-py3-none-any.whl': zip_bytes({
            'olive_fixture_component/__init__.py': b'VALUE = 42\n',
            'olive_fixture_component-1.0.dist-info/METADATA': b'Name: olive-fixture-component\n'}),
        'fixturehelper-1.0-py3-none-any.whl': zip_bytes({'olive_fixture_helper.py': b'X = 1\n'}),
    }

    async def asyncTearDown(self):
        import sys
        for name in ('olive_fixture_component', 'olive_fixture_helper'):
            sys.modules.pop(name, None)
        sys.path[:] = [p for p in sys.path if 'fixture-playwright' not in p]
        await super().asyncTearDown()

    async def test_optional_component_is_offered_not_preselected(self):
        plan = await self.installer.plan('complete')
        self.assertIn('fixture-playwright', plan['offered'])
        self.assertNotIn('fixture-playwright', plan['default'])
        core = await self.installer.plan('core')
        self.assertNotIn('fixture-playwright', core['offered'])

    async def test_install_activates_and_uninstall_removes_it(self):
        job = await self.run_job('complete', ['fixture-playwright'])
        self.assertEqual(job['state'], 'done', job)
        destination = self.data_root / 'components/fixture-playwright'
        import importlib
        self.assertEqual(importlib.import_module('olive_fixture_component').VALUE, 42)
        from olive.services.optional_components import activate
        self.assertEqual(activate(self.profile, self.env), ['fixture-playwright'])
        plan = await self.installer.plan('complete')
        self.assertEqual(next(r for r in plan['items'] if r['slot'] == 'playwright')['action'], 'present')
        await self.installer.uninstall('fixture-playwright')
        self.assertFalse(destination.exists())
        self.assertEqual(activate(self.profile, self.env), [])

    async def test_uninstall_refuses_a_folder_without_its_marker(self):
        await self.run_job('complete', ['fixture-playwright'])
        destination = self.data_root / 'components/fixture-playwright'
        (destination / MARKER).write_text('{"id": "someone-else"}')
        with self.assertRaises(InstallError):
            await self.installer.uninstall('fixture-playwright')
        self.assertTrue(destination.exists())

    async def test_uninstall_refuses_what_setup_did_not_install(self):
        with self.assertRaises(InstallError):
            await self.installer.uninstall('fixture-ollama')


class ReleaseGateTests(InstallerTestCase):
    """identified + engineering_reviewed + no release approval => never in an install plan."""

    async def test_unapproved_entry_never_enters_the_plan(self):
        self.manifest_value['release_approvals'] = [r for r in self.manifest_value['release_approvals']
                                                    if r['id'] != 'fixture-model-fast']
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()
        entry = self.installer.entry('fixture-model-fast')
        self.assertTrue(entry['licence']['identified'] and entry['licence']['engineering_reviewed'])
        plan = await self.installer.plan('core')
        row = next(r for r in plan['items'] if r['slot'] == 'model-fast')
        self.assertEqual((row['action'], row['detail']), ('unavailable', runtime_manifest.AWAITING_APPROVAL))
        self.assertEqual(row['entry']['release_state'], 'engineering_reviewed')
        self.assertFalse(row['entry']['installable'])
        self.assertNotIn('fixture-model-fast', plan['offered'] + plan['default'])
        self.assertEqual({f['id']: f['state'] for f in plan['features']}['fast'], 'not_in_build')
        with self.assertRaises(InstallError) as caught:
            await self.installer.start('core', ['fixture-model-fast'])
        self.assertEqual(caught.exception.code, 'not_installable')
        self.assertEqual(self.ollama.pulls, [])

    async def test_a_changed_pin_voids_the_approval(self):
        self.manifest_value['entries'][0]['sha256'] = 'a' * 64  # Approved for other bytes.
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()
        plan = await self.installer.plan('core')
        self.assertNotIn('fixture-ollama', plan['offered'])
        self.assertEqual(self.files.requests, [])

    async def test_hand_pointed_test_manifest_cannot_approve_itself(self):
        unflagged = dict(self.manifest_value)
        unflagged.pop('fixture')
        self.manifest_path.write_text(json.dumps(unflagged))
        with self.assertRaises(ValueError):
            self.make()
        unflagged.pop('release_approvals')
        self.manifest_path.write_text(json.dumps({**unflagged, 'entries': [
            e for e in unflagged['entries'] if not e['source'].get('url', '') or not e['source']['url'].startswith('http://')]
            + [dict(e, enabled=False, reason='fixture') for e in unflagged['entries']
               if (e['source'].get('url') or '').startswith('http://')]}))
        self.installer = self.make()
        self.assertEqual((await self.installer.plan('core'))['offered'], [])


class ShippedManifestPlanTests(unittest.IsolatedAsyncioTestCase):
    """Install plans over the real shipped manifest. Release approval, platform and dependency
    rules are separate: an approved model is still not chosen when its engine cannot be installed."""

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'home').mkdir()
        (self.root / 'profile').mkdir()
        self.env = {'XDG_DATA_HOME': str(self.root / 'xdg')}
        self.ollama = FakeOllama().__enter__()
        self.installers = []

    async def asyncTearDown(self):
        for installer in self.installers:
            await installer.close()
        await asyncio.to_thread(self.ollama.__exit__, None, None, None)
        self.temp.cleanup()

    def make(self, target, manifest=None):
        manifest = manifest if manifest is not None else runtime_manifest.load('1.0.0', environ={})
        self.assertEqual(manifest['_source'], 'release')
        discovery = RuntimeDiscovery(self.root / 'profile', environ=self.env, platform='linux', home=self.root / 'home',
                                     install_root=self.root / 'install', which=lambda name: None)
        installer = RuntimeInstaller(self.root / 'profile', discovery, ollama_host=self.ollama.base, environ=self.env,
                                     platform='linux', home=self.root / 'home', target=target, manifest=manifest,
                                     disk_usage=Disk(10 ** 12))
        installer.module_available = lambda name: False
        self.installers.append(installer)
        return installer

    async def test_engineering_evidence_alone_is_refused_by_setup(self):
        bare = runtime_manifest.load('1.0.0', environ={})
        bare['_approvals'] = {}  # Isolated from the owner's approvals file.
        installer = self.make(TARGET, bare)
        plan = await installer.plan('complete')
        self.assertEqual((plan['offered'], plan['default']), ([], []))
        row = next(r for r in plan['items'] if r['slot'] == 'model-fast')
        self.assertEqual(row['entry']['id'], 'qwen3-8b')
        self.assertEqual(row['entry']['release_state'], 'engineering_reviewed')
        self.assertEqual((row['action'], row['detail']), ('unavailable', runtime_manifest.AWAITING_APPROVAL))
        for entry_id in ('qwen3-8b', 'ollama-0.34.2-linux-x86_64'):
            with self.assertRaises(InstallError) as caught:
                await installer.start('core', [entry_id])
            self.assertEqual(caught.exception.code, 'not_installable')
        self.assertEqual(self.ollama.pulls, [])

    async def test_linux_core_offers_the_approved_runtime_and_models(self):
        installer = self.make(TARGET)
        plan = await installer.plan('core')
        self.assertEqual(set(plan['default']), {'ollama-0.34.2-linux-x86_64', 'qwen3-8b', 'gpt-oss-20b', 'qwen3.5-9b',
                                                'qwen3-embedding-0.6b'})
        self.assertEqual(set(plan['offered']), set(plan['default']))
        states = {f['id']: f['state'] for f in plan['features']}
        for feature in ('fast', 'normal', 'now', 'deep', 'agent_workspace'):
            self.assertEqual(states[feature], 'installable', feature)

    async def test_unapproved_components_stay_out_of_the_shipped_plan(self):
        installer = self.make(TARGET)
        plan = await installer.plan('complete')
        rows = {r['slot']: r for r in plan['items']}
        for slot, entry_id in (('model-vision', 'qwen3-vl-8b'), ('model-coding', 'qwen3-coder-30b'),
                               ('playwright', 'playwright-1.63.0')):
            self.assertEqual(rows[slot]['entry']['id'], entry_id)
            self.assertEqual((rows[slot]['action'], rows[slot]['detail']), ('unavailable', runtime_manifest.AWAITING_APPROVAL))
        for slot in ('video-engine', 'audio-engine', 'video-model', 'model-max', 'model-uncensored'):
            self.assertIn(rows[slot]['action'], ('unavailable', 'external'), slot)
        states = {f['id']: f['state'] for f in plan['features']}
        for feature in ('vision', 'advanced_coding', 'browser_automation', 'audio', 'video',
                        'image_to_video', 'long_video', 'max', 'uncensored'):
            self.assertNotIn(states[feature], ('ready', 'installable'), feature)
        # Only the owner-approved Linux image engine and its FLUX.2 4B model are offered from Creator.
        self.assertEqual(states['reimagine'], 'installable')
        self.assertEqual(set(plan['offered']), {'ollama-0.34.2-linux-x86_64', 'qwen3-8b', 'gpt-oss-20b', 'qwen3.5-9b',
                                                'qwen3-embedding-0.6b', 'comfyui-0.35.0-image-linux', 'flux2-klein-4b'})
        with self.assertRaises(InstallError) as caught:
            await installer.start('complete', ['qwen3-vl-8b'])
        self.assertEqual(caught.exception.code, 'not_installable')

    async def test_dependencies_are_separate_from_release_approval(self):
        # Windows: the models are approved for every platform, but the Windows runtime is not,
        # so no feature can become ready there and nothing is chosen by default.
        plan = await self.make('windows-x86_64').plan('core')
        self.assertEqual(set(plan['offered']), {'qwen3-8b', 'gpt-oss-20b', 'qwen3.5-9b', 'qwen3-embedding-0.6b'})
        self.assertEqual(plan['default'], [])
        runtime = next(r for r in plan['items'] if r['slot'] == 'ollama-runtime')
        self.assertEqual(runtime['entry']['id'], 'ollama-0.34.2-windows-x86_64')
        self.assertEqual(runtime['detail'], runtime_manifest.AWAITING_APPROVAL)
        self.assertEqual({f['id']: f['state'] for f in plan['features']}['fast'], 'not_in_build')
        # The FLUX.2 4B model is approved for Windows too, but no Windows image engine is: the model is
        # offered there, never chosen, and REIMAGINE cannot become ready.
        plan = await self.make('windows-x86_64').plan('creator')
        rows = {r['slot']: r for r in plan['items']}
        self.assertEqual(rows['image-model']['entry']['id'], 'flux2-klein-4b')
        self.assertTrue(rows['image-model']['entry']['installable'])
        self.assertIn('flux2-klein-4b', plan['offered'])
        self.assertNotIn('flux2-klein-4b', plan['default'])
        self.assertEqual(rows['image-engine']['entry']['id'], 'comfyui-windows-portable-0.35.0')
        self.assertFalse(rows['image-engine']['entry']['installable'])
        self.assertIn(rows['image-engine']['action'], ('unavailable', 'external'))
        reimagine = next(f for f in plan['features'] if f['id'] == 'reimagine')
        self.assertEqual(reimagine['state'], 'not_in_build')
        self.assertIn('image-engine', reimagine['missing'])
        # Linux: the published image engine has its own approval, so engine and model are both chosen.
        plan = await self.make(TARGET).plan('creator')
        rows = {r['slot']: r for r in plan['items']}
        model = rows['image-model']
        self.assertEqual(model['entry']['id'], 'flux2-klein-4b')
        self.assertEqual(model['entry']['release_state'], 'release_approved')
        self.assertEqual(model['action'], 'install')
        engine = rows['image-engine']
        self.assertEqual(engine['entry']['id'], 'comfyui-0.35.0-image-linux')
        self.assertEqual(engine['entry']['release_state'], 'release_approved')
        self.assertTrue(engine['entry']['installable'])
        self.assertEqual(engine['action'], 'install')
        self.assertTrue({'comfyui-0.35.0-image-linux', 'flux2-klein-4b'} <= set(plan['default']))
        self.assertEqual(next(f for f in plan['features'] if f['id'] == 'reimagine')['state'], 'installable')
        # No other Creator engine is offered or preselected without its own approval.
        manifest = runtime_manifest.load('1.0.0', environ={})
        engines = {e['id'] for e in manifest['entries'] if e['provides'] in ('image-engine', 'video-engine', 'audio-engine')}
        self.assertIn('comfyui-0.35.0-video-linux', engines)
        self.assertEqual(engines & set(plan['offered']), {'comfyui-0.35.0-image-linux'})
        self.assertEqual(engines & set(plan['default']), {'comfyui-0.35.0-image-linux'})


def model_entry(files: FileServer, data: dict[str, bytes], identifier='fixture-image-model') -> dict:
    listed = [{'name': name.rsplit('/', 1)[-1], 'path': name, 'url': files.add('/m/' + name, body),
               'sha256': __import__('hashlib').sha256(body).hexdigest(), 'size_bytes': len(body)}
              for name, body in data.items()]
    return {'id': identifier, 'kind': 'file', 'provides': 'image-model', 'name': 'Fixture image model', 'version': '0',
            'platforms': [TARGET], 'validated_platforms': [], 'enabled': True,
            'source': {'publisher': 'fixture', 'url': None, 'hosts': ['127.0.0.1']}, 'sha256': None, 'size_bytes': None,
            'files': {'any': listed},
            'install': {'destination': 'models/comfy', 'format': 'file', 'installed_bytes': sum(map(len, data.values()))},
            'licence': {'spdx': 'Apache-2.0', 'name': 'Apache-2.0', 'url': None, 'acceptance_required': False,
                        'distribution': 'download-at-first-run', 'identified': True, 'engineering_reviewed': True},
            'reason': None}


class ModelFileTests(InstallerTestCase):
    DATA = {'diffusion_models/fixture-unet.safetensors': os.urandom(4096), 'vae/fixture-vae.safetensors': b'v' * 1000}

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.manifest_value['entries'] = [e for e in self.manifest_value['entries'] if e['provides'] != 'image-model']
        self.manifest_value['entries'].append(model_entry(self.files, self.DATA))
        approve(self.manifest_value, ['fixture-image-model'])
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()

    async def test_a_model_is_not_preselected_without_an_installable_engine(self):
        plan = await self.installer.plan('creator')
        self.assertIn('fixture-image-model', plan['offered'])
        self.assertNotIn('fixture-image-model', plan['default'])  # REIMAGINE's engine is not in this build.
        self.assertEqual({f['id']: f['state'] for f in plan['features']}['reimagine'], 'not_in_build')

    async def test_install_places_verified_files_and_uninstall_removes_only_them(self):
        job = await self.run_job('creator', ['fixture-image-model'])
        self.assertEqual(job['items'][0]['state'], 'done', job)
        for name, body in self.DATA.items():
            path = self.data_root / 'models/comfy' / name
            self.assertEqual(path.read_bytes(), body)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual([p.name for p in (self.data_root / 'models/comfy/vae').iterdir()], ['fixture-vae.safetensors'])
        record = SetupStateRepository(self.profile).load()[0]['installed']['fixture-image-model']
        self.assertEqual(len(record['files']), 2)
        row = next(r for r in (await self.installer.plan('creator'))['items'] if r['slot'] == 'image-model')
        self.assertEqual(row['action'], 'present')
        # A file changed after installation is the person's now: kept on uninstall.
        (self.data_root / 'models/comfy/vae/fixture-vae.safetensors').write_bytes(b'edited')
        await self.installer.uninstall('fixture-image-model')
        self.assertFalse((self.data_root / 'models/comfy/diffusion_models/fixture-unet.safetensors').exists())
        self.assertEqual((self.data_root / 'models/comfy/vae/fixture-vae.safetensors').read_bytes(), b'edited')

    async def test_an_existing_different_file_is_never_replaced(self):
        mine = self.data_root / 'models/comfy/vae/fixture-vae.safetensors'
        mine.parent.mkdir(parents=True)
        mine.write_bytes(b'my own vae')
        job = await self.run_job('creator', ['fixture-image-model'])
        self.assertEqual((job['items'][0]['state'], job['items'][0]['error']), ('failed', 'destination_exists'))
        self.assertEqual(mine.read_bytes(), b'my own vae')
        self.assertFalse((self.data_root / 'models/comfy/diffusion_models/fixture-unet.safetensors').exists())
        self.assertEqual(self.files.requests, [])  # Refused before downloading anything.

    async def test_identical_existing_files_are_kept_not_downloaded(self):
        for name, body in self.DATA.items():
            path = self.data_root / 'models/comfy' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        plan = await self.installer.plan('creator')
        row = next(r for r in plan['items'] if r['slot'] == 'image-model')
        self.assertEqual(row['action'], 'present')
        self.assertNotIn('fixture-image-model', plan['offered'])
        self.assertEqual(self.files.requests, [])
        self.assertNotIn('fixture-image-model', SetupStateRepository(self.profile).load()[0]['installed'])
        # Even when started directly (a stale plan), identical files are kept and nothing is fetched.
        item = __import__('olive.services.runtime_installer', fromlist=['Item']).Item('fixture-image-model', 'x', 'file', 0)
        self.assertIsNone(await asyncio.to_thread(self.installer._install_model_files,
                                                  self.installer.entry('fixture-image-model'), item, None))
        self.assertEqual(item.state, 'present')
        self.assertEqual(self.files.requests, [])

    async def test_checksum_mismatch_places_nothing(self):
        self.files.files['/m/vae/fixture-vae.safetensors'] = b'x' * 1000
        job = await self.run_job('creator', ['fixture-image-model'])
        self.assertEqual(job['items'][0]['error'], 'checksum_mismatch')
        self.assertFalse((self.data_root / 'models/comfy/diffusion_models/fixture-unet.safetensors').exists())


class StorageVolumeTests(InstallerTestCase):
    """Runtime, models, downloads and the profile may live on different filesystems."""

    def volumes(self, mounts, free):
        """mounts: {folder: filesystem id}; free: {filesystem id: free bytes}."""
        table = sorted(((os.path.realpath(path), device) for path, device in mounts.items()),
                       key=lambda row: len(row[0]), reverse=True)
        for path in mounts:
            Path(path).mkdir(parents=True, exist_ok=True)
        self.installer.mounts = lambda: table
        owner = {os.path.realpath(p): d for p, d in mounts.items()}

        def usage(path):
            real = os.path.realpath(path)
            device = next(d for point, d in table if real == point or real.startswith(point + '/'))
            return type('Usage', (), {'free': free[device]})()
        self.installer.disk_usage = usage
        return owner

    async def test_each_byte_is_charged_to_the_filesystem_it_lands_on(self):
        root = str(self.root)
        self.volumes({root: 'root', str(self.data_root / 'runtime'): 'data', str(self.home / '.ollama/models'): 'models'},
                     {'root': 10 ** 12, 'data': 10 ** 12, 'models': 10 ** 12})
        space = self.installer.space(['fixture-ollama', 'fixture-model-fast'])
        rows = {r['label']: r for r in space['volumes']}
        self.assertEqual(set(rows), {'Downloads', 'OLIVE runtimes', 'Ollama models'})
        margin = __import__('olive.services.runtime_installer', fromlist=['MARGIN']).MARGIN
        self.assertEqual(rows['Downloads']['required_bytes'], margin + len(self.archive))
        self.assertEqual(rows['OLIVE runtimes']['required_bytes'], margin + 4096)
        self.assertEqual(rows['Ollama models']['required_bytes'], margin + 500)

    async def test_a_full_model_volume_refuses_even_when_root_has_room(self):
        root = str(self.root)
        self.volumes({root: 'root', str(self.home / '.ollama/models'): 'models'}, {'root': 10 ** 12, 'models': 100})
        plan = await self.installer.plan('core')
        short = [v for v in plan['totals']['volumes'] if not v['enough']]
        self.assertEqual([v['label'] for v in short], ['Ollama models'])
        with self.assertRaises(InstallError) as caught:
            await self.installer.start('core', plan['default'])
        self.assertIn('Ollama models', str(caught.exception))
        self.assertEqual(self.ollama.pulls, [])

    async def test_bind_mounts_and_subvolumes_of_one_filesystem_are_one_volume(self):
        root = str(self.root)
        # The runtime folder and the Ollama store are two bind mounts of the same filesystem.
        self.volumes({root: 'root', str(self.data_root / 'runtime'): 'olive-data', str(self.home / '.ollama/models'): 'olive-data'},
                     {'root': 10 ** 12, 'olive-data': 10 ** 12})
        space = self.installer.space(['fixture-ollama', 'fixture-model-fast'])
        shared = [v for v in space['volumes'] if 'Ollama models' in v['label']]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]['label'], 'OLIVE runtimes and Ollama models')  # One volume, both needs summed.
        margin = __import__('olive.services.runtime_installer', fromlist=['MARGIN']).MARGIN
        self.assertEqual(shared[0]['required_bytes'], margin + 4096 + 500)
        self.volumes({root: 'root', str(self.data_root / 'runtime'): 'olive-data', str(self.home / '.ollama/models'): 'olive-data'},
                     {'root': 10 ** 12, 'olive-data': margin + 4096 + 499})
        self.assertFalse(self.installer.space(['fixture-ollama', 'fixture-model-fast'])['enough_space'])

    async def test_real_mountinfo_parsing(self):
        from olive.services.runtime_installer import mount_table
        text = ('24 1 0:21 / / rw - ext4 /dev/sda1 rw\n'
                '234 60 0:55 /olive/models /home/u/.local/share/olive/models rw - btrfs /dev/nvme1n1p4 rw,subvolid=5\n'
                '239 60 0:55 /olive/runtime /home/u/.local/share/olive/runtime rw - btrfs /dev/nvme1n1p4 rw\n'
                '240 60 0:56 / /mnt/My\\040Disk rw - btrfs /dev/sdb1 rw\n')
        table = mount_table(text)
        self.assertEqual(table[0][0], '/home/u/.local/share/olive/runtime')
        self.assertIn(('/mnt/My Disk', '0:56'), table)
        from olive.services.runtime_installer import filesystem
        runtime = filesystem('/home/u/.local/share/olive/runtime/comfy', table)[0]
        self.assertEqual(runtime, filesystem('/home/u/.local/share/olive/models/comfy', table)[0])  # Same superblock.
        self.assertEqual(filesystem('/home/u/.local/share/olive/profile', table)[0], 'fs:0:21')
        self.assertEqual(mount_table(''), [])

    def test_system_check_reports_free_space_per_filesystem(self):
        from olive.services import system_check
        data = self.data_root
        mounts = {str(self.root): 'root', str(data / 'runtime'): 'olive-data', str(data / 'models'): 'olive-data'}
        for path in mounts:
            Path(path).mkdir(parents=True, exist_ok=True)
        table = sorted(((os.path.realpath(p), d) for p, d in mounts.items()), key=lambda r: len(r[0]), reverse=True)
        free = {'root': 400, 'olive-data': 80}

        def usage(path):
            real = os.path.realpath(path)
            return type('Usage', (), {'free': free[next(d for pt, d in table if real == pt or real.startswith(pt + '/'))]})()
        with mock.patch('olive.services.runtime_installer.mount_table', lambda: table), \
                mock.patch('olive.services.system_check.shutil.disk_usage', usage):
            rows = system_check.snapshot(environ=self.env, platform='linux', models_path=str(data / 'models/ollama'))['storage']
        self.assertEqual([(r['label'], r['free_bytes']) for r in rows],
                         [('OLIVE data', 400), ('OLIVE runtimes, Creator models and Ollama models', 80)])

    async def test_runtime_is_staged_on_its_own_filesystem(self):
        renames = []
        real_rename = os.rename

        def rename(source, destination):
            renames.append((Path(source), Path(destination)))
            return real_rename(source, destination)
        with mock.patch('olive.services.runtime_installer.os.rename', rename):
            job = await self.run_job('core', ['fixture-ollama'])
        self.assertEqual(job['items'][0]['state'], 'done')
        moved = [(s, d) for s, d in renames if d == self.data_root / 'runtime/ollama']
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0][0].parent, moved[0][1].parent)  # Never a cross-filesystem rename from temp.
        self.assertTrue(moved[0][0].name.startswith('.ollama.olive-staging-'))


if __name__ == '__main__':
    unittest.main()
