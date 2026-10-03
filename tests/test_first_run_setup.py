"""First-run state, resume, existing users, preferred name, verification, repair and bridge contracts."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from olive.application.service_container import ServiceContainer
from olive.bridge import contracts, setup_routes
from olive.services import first_run, runtime_manifest
from olive.services.first_run import FirstRunService
from olive.services.runtime_discovery import RuntimeDiscovery
from olive.services.runtime_installer import RuntimeInstaller
from olive.storage.setup_state_repository import SetupStateRepository
from tests.setup_installer_fixture import FakeOllama, FileServer, fixture_manifest, tar_bytes


class SetupStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name) / 'profile'

    def test_new_profile_is_a_first_launch(self):
        state = first_run.initialise(self.profile)
        self.assertEqual((state['state'], state['origin']), ('not_started', 'new'))
        self.assertTrue((self.profile / 'setup.json').is_file())

    def test_profile_in_use_is_an_existing_user_and_decided_once(self):
        self.profile.mkdir()
        (self.profile / 'chats.json').write_text('{"chats": []}')
        self.assertEqual(first_run.initialise(self.profile)['state'], 'existing')
        # A later start never re-decides, even though the profile now has more files.
        (self.profile / 'settings.json').write_text('{}')
        self.assertEqual(first_run.initialise(self.profile)['state'], 'existing')

    def test_electron_shell_folder_alone_is_not_user_data(self):
        (self.profile / 'electron-shell').mkdir(parents=True)
        self.assertEqual(first_run.initialise(self.profile)['state'], 'not_started')

    def test_stored_state_is_validated_and_never_holds_secrets(self):
        repository = SetupStateRepository(self.profile)
        state = repository.default('in_progress')
        state['installed'] = {'x-model': {'kind': 'ollama-model', 'token': 'secret', 'model': 'x'},
                              '../evil': {'kind': 'archive'}}
        repository.save(state)
        stored = json.loads((self.profile / 'setup.json').read_text())
        self.assertEqual(stored['installed'], {'x-model': {'kind': 'ollama-model', 'model': 'x'}})
        with self.assertRaises(ValueError):
            repository.save({**state, 'state': 'pwned'})

    def test_unreadable_state_is_reported_not_replaced(self):
        self.profile.mkdir()
        (self.profile / 'setup.json').write_text('{broken')
        _, readable = SetupStateRepository(self.profile).load()
        self.assertFalse(readable)
        first_run.initialise(self.profile)
        self.assertEqual((self.profile / 'setup.json').read_text(), '{broken')


class FirstRunServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = self.root / 'profile'
        self.home = self.root / 'home'
        self.home.mkdir()
        self.env = {'XDG_DATA_HOME': str(self.root / 'xdg'), 'OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP': '1'}
        self.files = FileServer().__enter__()
        self.ollama = FakeOllama().__enter__()
        archive = tar_bytes({'bin/ollama': b'#!/bin/sh\n'}, executable={'bin/ollama'})
        self.manifest_path = self.root / 'manifest.json'
        self.manifest_path.write_text(json.dumps(fixture_manifest(self.files, self.ollama, archive)))
        self.services = []

    async def asyncTearDown(self):
        for services in self.services:
            await services.runtime_installer.close()
            await services.shutdown()
        await asyncio.to_thread(self.files.__exit__, None, None, None)
        await asyncio.to_thread(self.ollama.__exit__, None, None, None)
        self.temp.cleanup()

    def container(self):
        services = ServiceContainer(lambda *a: None, None, data_dir=self.profile, migrate=False)
        self.services.append(services)
        services.runtime_discovery = RuntimeDiscovery(self.profile, environ=self.env, platform='linux', home=self.home,
                                                      install_root=self.root / 'install', which=lambda n: None)
        services.ollama.host = self.ollama.base
        manifest = runtime_manifest.load(environ=self.env, path=self.manifest_path)
        services.runtime_installer = RuntimeInstaller(self.profile, services.runtime_discovery,
                                                      ollama_host=self.ollama.base, environ=self.env, platform='linux',
                                                      home=self.home, target='linux-x86_64', manifest=manifest,
                                                      runtime_registered=services._runtime_registered)
        services.runtime_installer.module_available = lambda name: False

        async def refresh():
            return True
        services.refresh_model_inventory = refresh
        services.publish_model_state = lambda: None
        services._ensure_ollama = refresh
        services.first_run = FirstRunService(services, services.runtime_installer)
        return services

    async def install_core(self, services):
        plan = await services.runtime_installer.plan('core')
        job = await services.runtime_installer.start('core', plan['default'])
        await services.runtime_installer.jobs[job['job_id']].task
        return services.runtime_installer.progress(job['job_id'])

    async def test_first_launch_then_resume_after_restart(self):
        services = self.container()
        status = await services.first_run.status()
        self.assertEqual(status['state'], 'first_launch')
        self.assertEqual(status['preferred_name'], '')
        services.first_run.update(step='package', profile='creator')
        self.assertEqual((await services.first_run.status())['state'], 'incomplete')
        await services.shutdown()
        self.services.remove(services)
        again = self.container()
        status = await again.first_run.status()
        self.assertEqual((status['state'], status['step'], status['profile']), ('incomplete', 'package', 'creator'))

    async def test_skip_is_remembered(self):
        services = self.container()
        services.first_run.update(action='skip')
        self.assertEqual((await services.first_run.status())['state'], 'skipped')
        services.first_run.update(action='resume', step='welcome')
        self.assertEqual((await services.first_run.status())['state'], 'incomplete')

    async def test_existing_user_is_not_forced_and_keeps_their_name(self):
        self.profile.mkdir()
        (self.profile / 'settings.json').write_text(json.dumps({'preferred_name': 'Sam'}))
        services = self.container()
        status = await services.first_run.status()
        self.assertEqual(status['state'], 'existing')
        self.assertEqual(status['preferred_name'], 'Sam')
        # Opening setup later and leaving the name as it is never rewrites it.
        before = (self.profile / 'settings.json').stat().st_mtime_ns
        services.first_run.update(step='name', preferred_name='Sam')
        self.assertEqual(json.loads((self.profile / 'settings.json').read_text())['preferred_name'], 'Sam')
        self.assertEqual(before, (self.profile / 'settings.json').stat().st_mtime_ns)

    async def test_preferred_name_is_optional_and_bounded(self):
        services = self.container()
        services.first_run.update(step='name', preferred_name='  Ada   Lovelace ')
        self.assertEqual(services.settings['preferred_name'], 'Ada Lovelace')
        self.assertEqual(json.loads((self.profile / 'settings.json').read_text())['preferred_name'], 'Ada Lovelace')
        services.first_run.update(preferred_name='')
        self.assertEqual(services.settings['preferred_name'], '')
        with self.assertRaises(ValueError):
            services.first_run.update(preferred_name='x' * 121)

    async def test_setup_completes_only_after_verification(self):
        services = self.container()
        services.first_run.update(step='models', profile='core')
        result = await services.first_run.verify('core')
        self.assertFalse(result['ok'])
        self.assertEqual((await services.first_run.status())['state'], 'incomplete')
        job = await self.install_core(services)
        self.assertEqual(job['state'], 'done', job)
        # Downloads finished, but setup is still not complete until verify passes.
        self.assertEqual((await services.first_run.status())['state'], 'incomplete')
        result = await services.first_run.verify('core')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['fast']['state'], 'passed')
        self.assertEqual(self.ollama.generated, ['qwen3:8b'])
        status = await services.first_run.status()
        self.assertEqual(status['state'], 'complete')
        self.assertIn('fast', status['verified_features'])
        states = {f['id']: (f['state'], f['detail']) for f in result['features']}
        self.assertEqual(states['notes'][0], 'built_in')
        self.assertEqual(states['connect_world'], ('built_in', 'Needs a relay you run yourself.'))

    async def test_revisiting_setup_keeps_it_complete_until_the_package_changes(self):
        services = self.container()
        await self.install_core(services)
        self.assertTrue((await services.first_run.verify('core'))['ok'])
        services.first_run.update(action='resume', step='welcome')  # Settings › Open setup.
        services.first_run.update(step='models')
        services.first_run.update(action='skip')
        self.assertEqual((await services.first_run.status())['state'], 'complete')
        services.first_run.update(step='package', profile='complete')
        self.assertEqual((await services.first_run.status())['state'], 'incomplete')

    async def test_failed_fast_answer_blocks_completion(self):
        services = self.container()
        await self.install_core(services)
        self.ollama.answer = ''
        result = await services.first_run.verify('core')
        self.assertFalse(result['ok'])
        fast = next(f for f in result['features'] if f['id'] == 'fast')
        self.assertEqual(fast['state'], 'failed')
        self.assertNotEqual((await services.first_run.status())['state'], 'complete')

    async def test_creator_verifies_with_unavailable_components_reported_truthfully(self):
        services = self.container()
        await self.install_core(services)
        result = await services.first_run.verify('creator', media_smoke=True)
        states = {f['id']: f['state'] for f in result['features']}
        self.assertEqual(states['reimagine'], 'not_in_build')
        self.assertTrue(result['some_unavailable'])
        self.assertEqual(result['media']['state'], 'not_run')
        self.assertTrue(result['ok'])  # Everything this build can provide works.

    async def test_missing_model_after_completion_requires_repair(self):
        services = self.container()
        await self.install_core(services)
        self.assertTrue((await services.first_run.verify('core'))['ok'])
        self.ollama.models.pop('qwen3:8b')
        status = await services.first_run.status()
        self.assertEqual(status['state'], 'requires_repair')
        self.assertIn('fast', {r['feature'] for r in status['repairs']})

    async def test_removed_runtime_after_completion_requires_repair(self):
        services = self.container()
        await self.install_core(services)
        self.assertTrue((await services.first_run.verify('core'))['ok'])
        import shutil
        shutil.rmtree(self.root / 'xdg/olive/runtime/ollama')
        status = await services.first_run.status()
        self.assertEqual(status['state'], 'requires_repair')
        self.assertIn('ollama-runtime', {r['slot'] for r in status['repairs']})

    async def test_unreadable_state_requires_repair_and_reset_keeps_the_file(self):
        services = self.container()
        (self.profile / 'setup.json').write_text('{broken')
        status = await services.first_run.status()
        self.assertEqual((status['state'], status['reason']), ('requires_repair', 'unreadable_state'))
        with self.assertRaises(ValueError):
            services.first_run.update(step='name')
        services.first_run.update(action='reset')
        self.assertEqual((await services.first_run.status())['state'], 'incomplete')
        kept = list(self.profile.glob('setup.json.unreadable-*'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(), '{broken')

    async def test_choose_and_forget_runtime_through_the_bridge(self):
        services = self.container()
        folder = self.root / 'my-ollama'
        (folder / 'bin').mkdir(parents=True)
        (folder / 'bin/ollama').write_text('#!/bin/sh\n')
        os.chmod(folder / 'bin/ollama', 0o755)
        chosen = await setup_routes.call(services, 'runtime.choose', {'name': 'ollama', 'folder': str(folder)})
        self.assertEqual(chosen['runtime']['state'], 'found')
        self.assertEqual(chosen['runtime']['origin'], 'configured')
        self.assertEqual(services.local_ollama_runtime.executable, str(folder / 'bin/ollama'))
        forgotten = await setup_routes.call(services, 'runtime.forget', {'name': 'ollama'})
        self.assertEqual(forgotten['runtime']['state'], 'needs_setup')
        with self.assertRaises(ValueError):
            await setup_routes.call(services, 'runtime.choose', {'name': 'ollama', 'folder': str(self.root)})

    async def test_installer_is_not_a_model_tool(self):
        services = self.container()
        tools = services.tool_registry._tools
        names = set(tools)
        # Studio's package install and the quarantined web download tools predate setup and are unrelated.
        self.assertFalse({n for n in names if n.split('.')[0] in {'runtime', 'setup', 'ollama', 'models'}}, names)
        modules = {type(tool).__module__ for tool in tools.values()}
        self.assertFalse({m for m in modules if m.endswith(('runtime_installer', 'setup_routes', 'secure_download',
                                                              'first_run'))}, modules)


class SetupContractTests(unittest.TestCase):
    def call(self, method, args):
        return contracts.validate({'v': 1, 'id': 'a1', 'method': method, 'args': args})

    def test_every_setup_operation_is_registered(self):
        for method in ('runtime.setup_status', 'runtime.manifest', 'runtime.install_plan', 'runtime.install_start',
                       'runtime.install_progress', 'runtime.install_cancel', 'runtime.install_retry',
                       'runtime.choose', 'runtime.forget', 'runtime.verify', 'runtime.setup_update',
                       'runtime.system_check', 'runtime.uninstall'):
            self.assertIn(method, contracts.METHODS)

    def test_strict_arguments(self):
        self.call('runtime.install_start', {'profile': 'core', 'entries': ['qwen3-8b', 'ollama-0.34.2-linux-x86_64']})
        bad = [
            ('runtime.install_start', {'profile': 'core', 'entries': ['https://evil.example/x.tgz']}),
            ('runtime.install_start', {'profile': 'core', 'entries': []}),
            ('runtime.install_start', {'profile': 'pro', 'entries': ['qwen3-8b']}),
            ('runtime.install_start', {'profile': 'core', 'entries': ['qwen3-8b'], 'url': 'https://x'}),
            ('runtime.install_start', {'profile': 'core', 'entries': 'qwen3-8b'}),
            ('runtime.install_progress', {'job_id': '../../etc'}),
            ('runtime.choose', {'name': 'ollama', 'paths': {'command': 'rm -rf /'}}),
            ('runtime.choose', {'name': 'ollama', 'paths': {'executable': '/x'}, 'folder': '/y'}),
            ('runtime.choose', {'name': 'bash', 'folder': '/y'}),
            ('runtime.setup_update', {'step': 'admin'}),
            ('runtime.setup_update', {'preferred_name': 'x' * 121}),
            ('runtime.setup_update', {'action': 'delete'}),
            ('runtime.verify', {'profile': 'core', 'run_fast': 'yes'}),
        ]
        for method, args in bad:
            with self.assertRaises(ValueError, msg=(method, args)):
                self.call(method, args)

    def test_polled_operations_stay_out_of_the_replay_ledger(self):
        self.assertTrue({'runtime.install_progress', 'runtime.setup_status', 'runtime.install_plan'}
                        <= setup_routes.READ_ONLY)
        self.assertFalse({'runtime.install_start', 'runtime.verify', 'runtime.choose'} & setup_routes.READ_ONLY)


if __name__ == '__main__':
    unittest.main()
