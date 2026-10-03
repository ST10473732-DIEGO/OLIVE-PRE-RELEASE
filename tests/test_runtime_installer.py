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
from tests.setup_installer_fixture import FakeOllama, FileServer, fixture_manifest, tar_bytes, zip_bytes

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
        self.manifest_path.write_text(json.dumps(self.manifest_value))
        self.installer = self.make()
        job = await self.run_job(entries=['fixture-ollama'])
        self.assertEqual(job['items'][0]['error'], 'unsafe_archive')
        self.assertFalse((self.data_root / 'runtime/ollama').exists())
        self.assertEqual(list((self.data_root / 'temp/staging').iterdir()), [])

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


if __name__ == '__main__':
    unittest.main()
