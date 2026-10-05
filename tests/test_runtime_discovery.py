"""Persisted runtime discovery: deterministic precedence, truthful Needs setup, no relocation."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from olive.services.runtime_discovery import NAMES, RuntimeDiscovery


def touch(path, executable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('')
    if executable:
        path.chmod(0o755)
    return path


class DiscoveryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.home, self.data, self.profile, self.checkout = base / 'home', base / 'data', base / 'profile', base / 'checkout'
        for path in (self.home, self.data, self.profile, self.checkout):
            path.mkdir()
        self.env = {'XDG_DATA_HOME': str(self.data), 'HOME': str(self.home)}
        self.runtime = self.data / 'olive' / 'runtime'

    def discovery(self, env=None, platform='linux', which=lambda _: None, install_root=None):
        return RuntimeDiscovery(self.profile, env or self.env, platform, self.home,
                                install_root or self.checkout, which)

    def install_linux_runtimes(self):
        touch(self.runtime / 'ollama/bin/ollama', True)
        for folder in ('comfy', 'video-comfy'):
            touch(self.runtime / folder / 'ComfyUI/main.py')
            touch(self.runtime / folder / 'comfy-venv/bin/python', True)
        touch(self.runtime / 'voicestudio/backend/main.py')
        touch(self.runtime / 'voicestudio/.venv/bin/python', True)
        (self.data / 'olive/models/comfy').mkdir(parents=True)


class RuntimeDiscoveryTests(DiscoveryFixture):
    def test_fresh_profile_reports_needs_setup_and_writes_nothing(self):
        located = self.discovery().resolve(adopt=True)
        self.assertEqual({k: (v.state, v.reason) for k, v in located.items()},
                         {name: ('needs_setup', 'missing') for name in NAMES})
        self.assertFalse((self.profile / 'runtimes.json').exists())

    def test_existing_linux_runtimes_are_adopted_in_place_and_survive_restart(self):
        self.install_linux_runtimes()
        before = sorted(p.relative_to(self.data) for p in self.data.rglob('*'))
        located = self.discovery().resolve(adopt=True)
        self.assertTrue(all(v.found and v.source == 'settings' and v.origin == 'olive-owned' for v in located.values()))
        self.assertEqual(located['comfy'].paths, {'root': str(self.runtime / 'comfy/ComfyUI'),
                                                  'python': str(self.runtime / 'comfy/comfy-venv/bin/python')})
        self.assertEqual(located['voicestudio'].paths['url'], 'http://127.0.0.1:3900')
        self.assertEqual(sorted(p.relative_to(self.data) for p in self.data.rglob('*')), before)  # Nothing moved.
        stored = json.loads((self.profile / 'runtimes.json').read_text())
        self.assertEqual(stored['schema'], 'olive-runtimes/1')
        self.assertEqual(set(stored['runtimes']), set(NAMES))
        # Restart: a new process resolves from the persisted settings alone.
        again = self.discovery(which=lambda _: '/usr/bin/ollama').resolve(adopt=True)
        self.assertEqual({k: (v.state, v.source) for k, v in again.items()}, {n: ('found', 'settings') for n in NAMES})
        self.assertEqual(again['ollama'].paths['executable'], str(self.runtime / 'ollama/bin/ollama'))

    def test_stale_persisted_location_is_needs_setup_without_silent_fallback(self):
        self.install_linux_runtimes()
        (self.profile / 'runtimes.json').write_text(json.dumps({'schema': 'olive-runtimes/1', 'runtimes': {
            'comfy': {'paths': {'root': '/gone/ComfyUI', 'python': '/gone/python'}, 'origin': 'configured'}}}))
        located = self.discovery().resolve(adopt=True)
        comfy = located['comfy']
        self.assertEqual((comfy.state, comfy.reason, comfy.source), ('needs_setup', 'stale', 'settings'))
        self.assertEqual(comfy.get('root'), '')
        self.assertEqual(comfy.also_found[0]['paths']['root'], str(self.runtime / 'comfy/ComfyUI'))
        stored = json.loads((self.profile / 'runtimes.json').read_text())
        self.assertEqual(stored['runtimes']['comfy']['paths']['root'], '/gone/ComfyUI')  # Not silently replaced.

    def test_environment_override_wins_and_invalid_override_is_reported(self):
        self.install_linux_runtimes()
        self.discovery().resolve(adopt=True)
        other = Path(self.temp.name) / 'other'
        touch(other / 'ComfyUI/main.py')
        touch(other / 'python', True)
        env = dict(self.env, OLIVE_COMFY_ROOT=str(other / 'ComfyUI'), OLIVE_COMFY_PYTHON=str(other / 'python'))
        comfy = self.discovery(env).resolve()['comfy']
        self.assertEqual((comfy.source, comfy.paths['root'], comfy.overrides_settings), ('environment', str(other / 'ComfyUI'), True))
        bad = self.discovery(dict(self.env, OLIVE_VIDEO_COMFY_ROOT='/missing', OLIVE_VIDEO_COMFY_PYTHON='/missing/python')).resolve()
        self.assertEqual((bad['video_comfy'].state, bad['video_comfy'].reason), ('needs_setup', 'invalid_override'))
        # A URL-only override is an externally managed VoiceStudio service.
        url = self.discovery(dict(self.env, OLIVE_VOICESTUDIO_URL='http://127.0.0.1:3999')).resolve()['voicestudio']
        self.assertEqual((url.state, url.paths), ('found', {'url': 'http://127.0.0.1:3999'}))

    def test_two_installations_in_one_tier_need_an_explicit_choice(self):
        local = self.data / 'Local'
        env = {'LOCALAPPDATA': str(local)}
        base = local / 'OLIVE/runtime/comfy'
        touch(base / 'ComfyUI_windows_portable/ComfyUI/main.py')
        touch(base / 'ComfyUI_windows_portable/python_embeded/python.exe')
        touch(base / 'ComfyUI/main.py')
        touch(base / 'comfy-venv/Scripts/python.exe')
        discovery = self.discovery(env, 'win32')
        comfy = discovery.resolve(adopt=True)['comfy']
        self.assertEqual((comfy.state, comfy.reason), ('needs_setup', 'conflict'))
        self.assertEqual(len(comfy.also_found), 2)
        self.assertFalse((self.profile / 'runtimes.json').exists())
        chosen = discovery.choose('comfy', comfy.also_found[1]['paths'])
        self.assertEqual((chosen.state, chosen.source, chosen.origin), ('found', 'settings', 'configured'))
        with self.assertRaisesRegex(ValueError, 'expected runtime files'):
            discovery.choose('comfy', {'root': '/nope', 'python': '/nope'})
        discovery.forget('comfy')
        self.assertEqual(discovery.resolve()['comfy'].reason, 'conflict')

    def test_repository_runtimes_are_a_source_checkout_fallback_only(self):
        touch(self.checkout / '.toolchains/ComfyUI/main.py')
        touch(self.checkout / '.toolchains/comfy-venv/bin/python', True)
        comfy = self.discovery().resolve(adopt=True)['comfy']
        self.assertEqual((comfy.state, comfy.origin, comfy.source), ('found', 'source-checkout', 'discovered'))
        self.assertFalse((self.profile / 'runtimes.json').exists())  # Never adopted into the profile.
        (self.checkout / 'olive-backend.json').write_text('{}')  # The same tree as a packaged backend.
        self.assertEqual(self.discovery().resolve()['comfy'].reason, 'missing')

    def test_owned_runtime_precedes_repository_and_system_copies(self):
        self.install_linux_runtimes()
        touch(self.checkout / '.toolchains/ollama/bin/ollama', True)
        ollama = self.discovery(which=lambda _: '/usr/bin/ollama').resolve()['ollama']
        self.assertEqual(ollama.origin, 'olive-owned')
        self.assertEqual({a['origin'] for a in ollama.also_found}, {'source-checkout'})

    def test_system_ollama_is_used_but_never_persisted(self):
        system = touch(Path(self.temp.name) / 'bin/ollama', True)
        ollama = self.discovery(which=lambda _: str(system)).resolve(adopt=True)['ollama']
        self.assertEqual((ollama.state, ollama.origin, ollama.source), ('found', 'system', 'discovered'))
        self.assertFalse((self.profile / 'runtimes.json').exists())

    def test_unreadable_settings_are_reported_and_never_overwritten(self):
        self.install_linux_runtimes()
        (self.profile / 'runtimes.json').write_text('{not json')
        located = self.discovery().resolve(adopt=True)
        self.assertTrue(all(v.reason == 'unreadable_settings' for v in located.values()))
        self.assertEqual((self.profile / 'runtimes.json').read_text(), '{not json')

    def test_only_location_fields_are_kept(self):
        self.install_linux_runtimes()
        (self.profile / 'runtimes.json').write_text(json.dumps({'schema': 'olive-runtimes/1', 'runtimes': {
            'ollama': {'paths': {'executable': str(self.runtime / 'ollama/bin/ollama'), 'token': 'secret'}}}}))
        located = self.discovery().resolve(adopt=True)
        self.assertNotIn('token', located['ollama'].paths)
        self.assertNotIn('secret', (self.profile / 'runtimes.json').read_text())

    def test_platform_specific_owned_candidates(self):
        local = Path(self.temp.name) / 'Local'
        win = RuntimeDiscovery(self.profile, {'LOCALAPPDATA': str(local)}, 'win32', self.home, self.checkout, lambda _: None)
        self.assertIn(('olive-owned', {'executable': str(local / 'OLIVE/runtime/ollama/ollama.exe')}), win.candidates('ollama'))
        self.assertIn(('system', {'executable': str(local / 'Programs/Ollama/ollama.exe')}), win.candidates('ollama'))
        mac = RuntimeDiscovery(self.profile, {}, 'darwin', self.home, self.checkout, lambda _: None)
        support = self.home / 'Library/Application Support/OLIVE'
        self.assertEqual(mac.candidates('comfy')[0][1]['root'], str(support / 'runtime/comfy/ComfyUI'))
        self.assertIn('/Applications/Ollama.app/Contents/Resources/ollama',
                      [p['executable'] for _, p in mac.candidates('ollama')])
        snapshot = mac.snapshot()
        self.assertFalse(snapshot['runtimes']['comfy']['validated_on_platform'])  # Creator not claimed on macOS.



class ServiceContainerDiscoveryTests(DiscoveryFixture, unittest.IsolatedAsyncioTestCase):
    async def test_service_container_resolves_runtimes_for_the_backend(self):
        from olive.application.service_container import ServiceContainer
        self.install_linux_runtimes()
        with patch.dict(os.environ, self.env):
            services = ServiceContainer(lambda *_: None, None, data_dir=self.profile, migrate=False)
        try:
            self.assertEqual(services.local_ollama_runtime.resolve_executable(), str(self.runtime / 'ollama/bin/ollama'))
            self.assertEqual(services.media.engines.video.runtime.root, str(self.runtime / 'video-comfy/ComfyUI'))
            self.assertEqual(services.chat_media.voice.runtime.root, str(self.runtime / 'voicestudio'))
            self.assertTrue((self.profile / 'runtimes.json').exists())
            snapshot = services.runtime_discovery.snapshot()
            self.assertEqual(snapshot['runtimes']['comfy']['state'], 'found')
        finally:
            await services.shutdown()

if __name__ == '__main__':
    unittest.main()
