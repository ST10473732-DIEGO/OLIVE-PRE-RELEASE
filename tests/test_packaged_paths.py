"""Packaged-mode path authority: writable state never lands inside the installation."""
import json
import os
from pathlib import Path, PureWindowsPath, PurePosixPath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from olive import app_paths


def packaged_root(directory):
    root = Path(directory) / 'resources' / 'backend'
    (root / 'olive').mkdir(parents=True)
    (root / app_paths.BACKEND_MANIFEST).write_text(json.dumps({'schema': 'olive-backend/1'}))
    return root


class UserDataRootTests(unittest.TestCase):
    def test_platform_roots(self):
        self.assertEqual(app_paths.user_data_root({'XDG_DATA_HOME': '/x/data'}, 'linux', '/home/u'), PurePosixPath('/x/data/olive'))
        self.assertEqual(app_paths.user_data_root({'XDG_DATA_HOME': 'relative'}, 'linux', '/home/u'),
                         PurePosixPath('/home/u/.local/share/olive'))
        self.assertEqual(app_paths.user_data_root({}, 'darwin', '/Users/u'),
                         PurePosixPath('/Users/u/Library/Application Support/OLIVE'))
        self.assertEqual(app_paths.user_data_root({'LOCALAPPDATA': r'C:\Users\u\AppData\Local'}, 'win32', r'C:\Users\u'),
                         PureWindowsPath(r'C:\Users\u\AppData\Local\OLIVE'))
        self.assertEqual(app_paths.user_data_root({}, 'win32', r'C:\Users\u'), PureWindowsPath(r'C:\Users\u\AppData\Local\OLIVE'))

    def test_runtime_models_toolchains_and_locks(self):
        env = {'XDG_DATA_HOME': '/d', 'XDG_RUNTIME_DIR': '/run/user/1'}
        self.assertEqual(str(app_paths.runtime_root(env, 'linux', '/h')), '/d/olive/runtime')
        self.assertEqual(str(app_paths.media_models_root(env, 'linux', '/h')), '/d/olive/models')
        self.assertEqual(str(app_paths.toolchains_root(env, 'linux', '/h')), '/d/olive/toolchains')
        self.assertEqual(str(app_paths.lock_directory(env, 'linux', '/h')), '/run/user/1')
        self.assertEqual(str(app_paths.lock_directory({}, 'linux', '/h')), '/h/.cache/olive')
        self.assertEqual(app_paths.runtime_root({'LOCALAPPDATA': r'C:\L'}, 'win32', r'C:\U'), PureWindowsPath(r'C:\L\OLIVE\runtime'))
        self.assertEqual(str(app_paths.lock_directory({}, 'darwin', '/Users/u')), '/Users/u/Library/Application Support/OLIVE/locks')

    def test_existing_linux_locations_are_the_ones_the_launcher_used(self):
        # run_olive.sh exported these paths before PASS 2B; nothing on an existing machine moves.
        home = '/home/u'
        self.assertEqual(str(app_paths.runtime_root({}, 'linux', home)), home + '/.local/share/olive/runtime')
        self.assertEqual(str(app_paths.media_models_root({}, 'linux', home)), home + '/.local/share/olive/models')


class PackagedDetectionTests(unittest.TestCase):
    def test_manifest_marks_a_packaged_backend_and_installation_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = packaged_root(directory)
            self.assertTrue(app_paths.packaged(root))
            self.assertIsNone(app_paths.source_toolchains(root))
            with self.assertRaises(PermissionError):
                app_paths.require_writable_location(root / 'olive' / 'cache.json', root)
            outside = Path(directory) / 'profile' / 'x.json'
            self.assertEqual(app_paths.require_writable_location(outside, root), outside)
            self.assertEqual(app_paths.toolchain_directories({'XDG_DATA_HOME': directory}, 'linux', directory, root),
                             [Path(directory) / 'olive' / 'toolchains'])

    def test_source_checkout_keeps_repository_toolchains_as_fallback(self):
        self.assertFalse(app_paths.packaged())  # The test suite runs from a checkout.
        dirs = app_paths.toolchain_directories()
        self.assertEqual(dirs[-1], app_paths.INSTALL_ROOT / '.toolchains')
        self.assertNotEqual(dirs[0], app_paths.INSTALL_ROOT / '.toolchains')

    def test_studio_toolchain_lookup_never_uses_the_installation_when_packaged(self):
        from olive.studio_tooling import toolchain
        with tempfile.TemporaryDirectory() as directory:
            root = packaged_root(directory)
            with patch.object(toolchain, 'REPOSITORY', root), patch.dict(os.environ, {'XDG_DATA_HOME': directory}):
                self.assertNotIn(root / '.toolchains', toolchain.toolchain_roots())

    def test_user_projects_do_not_get_the_bundled_interpreter(self):
        from olive.services.build_test_service import BuildAndTestService
        with tempfile.TemporaryDirectory() as directory, patch('olive.app_paths.packaged', return_value=True), \
                patch('shutil.which', side_effect=lambda name: '/usr/bin/python3' if name == 'python3' else None):
            self.assertEqual(BuildAndTestService.python_executable(Path(directory)), '/usr/bin/python3')


class LinuxLaunchAtLoginTests(unittest.TestCase):
    def test_packaged_autostart_starts_the_appimage_file_not_its_mount(self):
        from olive.services.linux_startup import configure
        with tempfile.TemporaryDirectory() as directory, patch('sys.platform', 'linux'):
            appimage = Path(directory) / 'Apps dir' / 'OLIVE-1.0.0.AppImage'
            appimage.parent.mkdir()
            appimage.write_text('')
            target = configure(True, Path(directory) / 'no-checkout', Path(directory) / 'profile', directory, executable=str(appimage))
            body = target.read_text()
            self.assertIn('OLIVE-1.0.0.AppImage', body)
            self.assertNotIn('run_olive.sh', body)
            with self.assertRaisesRegex(ValueError, 'mount'):
                configure(True, directory, directory, directory, executable='/tmp/.mount_OLIVEab12/olive')


class OwnedProcessDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_platform_uses_its_owned_process_adapter(self):
        from olive.runtime import processes
        with patch('sys.platform', 'linux'), patch('olive.studio_tooling.posix_process.start_owned_process', new_callable=AsyncMock) as linux:
            await processes.start_owned_process(['x'], cwd='/')
            linux.assert_awaited_once()
        windows_module = type(sys)('olive.studio_tooling.windows_process')
        windows_module.start_owned_process = AsyncMock()
        with patch('sys.platform', 'win32'), patch.dict(sys.modules, {'olive.studio_tooling.windows_process': windows_module}):
            await processes.start_owned_process(['x'])
            self.assertEqual(windows_module.start_owned_process.await_args.kwargs['creationflags'] & processes.CREATE_NO_WINDOW,
                             processes.CREATE_NO_WINDOW)
        with patch('sys.platform', 'darwin'), patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as spawn:
            owned = await processes.start_owned_process(['x'])
            self.assertTrue(spawn.await_args.kwargs['start_new_session'])
            self.assertIsInstance(owned, processes.SessionProcess)
        from olive.platform_support import PlatformUnavailable
        with patch('sys.platform', 'freebsd14'), self.assertRaises(PlatformUnavailable):
            await processes.start_owned_process(['x'])

    async def test_start_lock_is_exclusive(self):
        from olive.runtime.processes import StartLock
        with tempfile.TemporaryDirectory() as directory:
            first = StartLock(Path(directory) / 'a.lock').open()
            second = StartLock(Path(directory) / 'a.lock').open()
            try:
                self.assertTrue(first.try_acquire())
                self.assertFalse(second.try_acquire())
                with self.assertRaises(TimeoutError):
                    await second.acquire(2, 'busy')
            finally:
                first.close()
                second.close()


class RuntimeLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def test_owned_ollama_uses_the_discovered_executable_models_and_shared_lock(self):
        from olive.services.local_ollama_runtime import LocalOllamaRuntime
        with tempfile.TemporaryDirectory() as directory:
            runtime = LocalOllamaRuntime('http://127.0.0.1:11434', executable='/owned/ollama', models='/models')
            started = AsyncMock()
            started.return_value.returncode = None
            ready = AsyncMock(side_effect=[False, False, True])
            env = {k: v for k, v in os.environ.items() if k != 'OLLAMA_MODELS'}
            env.update(OLIVE_START_OLLAMA='1', XDG_RUNTIME_DIR=directory)
            with patch.dict(os.environ, env, clear=True), patch('sys.platform', 'linux'), patch.object(runtime, 'ready', ready), \
                    patch('olive.studio_tooling.posix_process.start_owned_process', started), patch('psutil.Process'), \
                    patch('shutil.which', return_value='/path/ollama'):
                await runtime.start()
            command = started.await_args.args[0]
            self.assertEqual(command, ['/owned/ollama', 'serve'])
            self.assertEqual(started.await_args.kwargs['env']['OLLAMA_MODELS'], '/models')
            self.assertTrue((Path(directory) / 'olive-ollama-start.lock').exists())

    def test_linux_comfy_arguments_are_unchanged_and_windows_adds_portable_flags(self):
        from olive.services.local_comfy_runtime import LocalComfyRuntime
        video = LocalComfyRuntime('http://127.0.0.1:8190', '/v/ComfyUI', '/v/python', custom_nodes=('ComfyUI-GGUF-Loader',), allocator=())
        with patch('sys.platform', 'linux'):
            self.assertEqual(video.arguments(), ['/v/python', str(Path('/v/ComfyUI') / 'main.py'), '--listen', '127.0.0.1',
                                                 '--port', '8190', '--disable-auto-launch', '--disable-all-custom-nodes',
                                                 '--disable-api-nodes', '--cache-none',
                                                 '--whitelist-custom-nodes', 'ComfyUI-GGUF-Loader'])
        with patch('sys.platform', 'win32'):
            args = video.arguments()
            self.assertEqual(args[1], '-s')
            self.assertIn('--windows-standalone-build', args)
            # LTX's loader is never disabled on Windows (PASS 1 blocker B10).
            self.assertEqual(args[args.index('--whitelist-custom-nodes') + 1], 'ComfyUI-GGUF-Loader')
            self.assertTrue(video.manages('http://127.0.0.1:8190'))
        with patch('sys.platform', 'darwin'):
            self.assertTrue(video.manages('http://127.0.0.1:8190'))
        with patch('sys.platform', 'freebsd14'):
            self.assertFalse(video.manages('http://127.0.0.1:8190'))

    def test_voicestudio_uses_the_platform_venv_layout(self):
        from olive.services.voicestudio import LocalVoiceStudioRuntime
        runtime = LocalVoiceStudioRuntime('http://127.0.0.1:3900', '/vs')
        with patch('sys.platform', 'win32'):
            self.assertTrue(runtime.python.replace('\\', '/').endswith('/vs/.venv/Scripts/python.exe'))
        with patch('sys.platform', 'linux'):
            self.assertEqual(runtime.python, str(Path('/vs/.venv/bin/python')))

    def test_media_engines_take_locations_from_discovery_not_the_launcher(self):
        from olive.services.media_engines import MediaEngines
        from olive.services.runtime_discovery import Located
        located = {
            'comfy': Located('comfy', 'found', paths={'root': '/i/ComfyUI', 'python': '/i/py'}),
            'video_comfy': Located('video_comfy', 'needs_setup', 'missing'),
            'media_models': Located('media_models', 'found', paths={'path': '/m'}),
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'OLIVE_VIDEO_COMFY_ROOT': '/ignored'}):
            engines = MediaEngines(directory, located)
        self.assertEqual((engines.image.runtime.root, engines.image.runtime.python), ('/i/ComfyUI', '/i/py'))
        self.assertEqual((engines.video.runtime.root, engines.video.runtime.python), ('', ''))
        self.assertFalse(engines.video.runtime.installed())


if __name__ == '__main__':
    unittest.main()


class OptionalBrowserComponentTests(unittest.IsolatedAsyncioTestCase):
    """Packaged backends ship without Playwright; nothing may fail with ModuleNotFoundError."""

    async def test_research_without_playwright_reports_and_stays_on_http(self):
        from olive.research import browser
        with patch.object(browser.PlaywrightBrowserProvider, 'installed', staticmethod(lambda: False)):
            availability = browser.PlaywrightBrowserProvider.availability()
            self.assertEqual((availability['installed'], availability['driver']), (False, False))
            service = browser.BrowserService('auto')
            short_page = SimpleNamespace(text='tiny', url='https://example.test/')  # Below the 200-character threshold.
            service.http.open = AsyncMock(return_value=short_page)
            service.rendered.open = AsyncMock()
            service.remember = lambda page: page
            self.assertIs(await service.open('https://example.test/'), short_page)
            service.rendered.open.assert_not_awaited()
            with self.assertRaisesRegex(RuntimeError, 'optional OLIVE component and is not installed'):
                await browser.PlaywrightBrowserProvider().ensure_started()

    async def test_interactive_browser_without_playwright_is_a_truthful_platform_state(self):
        from olive.desktop.interactive_browser import InteractiveBrowserProvider
        from olive.platform_support import PlatformUnavailable
        import threading
        with tempfile.TemporaryDirectory() as directory, patch('importlib.util.find_spec', return_value=None):
            provider = InteractiveBrowserProvider(directory, threading.Event())
            with self.assertRaisesRegex(PlatformUnavailable, 'optional Playwright component'):
                await provider.launch('chrome')
