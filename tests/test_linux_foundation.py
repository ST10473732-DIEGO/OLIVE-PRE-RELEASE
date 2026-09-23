"""Portable platform boundaries, tested against synthetic profiles only."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olive.identity import resolve_profile
from olive.platform_support import PlatformUnavailable, require_windows, venv_python, open_path
from olive.services.credential_vault import CredentialVault
from olive.bridge.public_errors import public_error


class LinuxFoundationTests(unittest.TestCase):
    def test_xdg_continuity_conflict_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            xdg = home / 'data'
            env = {'XDG_DATA_HOME': str(xdg)}
            self.assertEqual(resolve_profile(env, home, 'linux'), xdg / 'olive')
            self.assertEqual(resolve_profile({'XDG_DATA_HOME': 'relative'}, home, 'linux'), home / '.local/share/olive')
            old = home / '.olive'
            old.mkdir()
            (old / 'settings.json').write_text('{}')
            self.assertEqual(resolve_profile(env, home, 'linux'), old)
            (xdg / 'olive').mkdir(parents=True)
            (xdg / 'olive' / 'settings.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Multiple OLIVE'):
                resolve_profile(env, home, 'linux')
            self.assertEqual(resolve_profile({**env, 'OLIVE_DATA_DIR': str(old)}, home, 'linux'), old)
            self.assertEqual((old / 'settings.json').read_text(), '{}')

    @unittest.skipUnless(sys.platform == 'linux', 'Linux Secret Service boundary')
    def test_linux_native_features_fail_before_loading_windows_modules(self):
        with patch('sys.platform', 'linux'), patch('secretstorage.dbus_init', side_effect=OSError('unavailable')), tempfile.TemporaryDirectory() as directory:
            vault = CredentialVault(directory)
            for operation in (lambda: vault.put('discord-bot', 'synthetic'),
                              lambda: vault.read_for_provider('discord-bot'),
                              lambda: vault.remove('discord-bot')):
                with self.assertRaises(PlatformUnavailable) as raised:
                    operation()
                self.assertIn('No plaintext fallback', public_error(raised.exception)['message'])
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(venv_python(), '.venv/bin/python')
        with patch('sys.platform', 'win32'):
            require_windows('Desktop Control')
            self.assertEqual(venv_python(), '.venv/Scripts/python.exe')

    def test_conpty_rejection_does_not_create_a_session(self):
        import asyncio
        from olive.studio_tooling.pty import TerminalServices
        async def run():
            service = TerminalServices(lambda *_: None)
            with patch('sys.platform', 'linux'), self.assertRaisesRegex(ValueError, "Linux shell"):
                service.create('workspace', tempfile.gettempdir(), 'powershell', {})
            self.assertEqual(service.sessions, {})
        asyncio.run(run())
        # The shared Agent tool boundary wraps unsuccessful runs in PermissionError.
        message = 'Studio interactive terminal for Linux is not available in this build yet.'
        self.assertEqual(public_error(PermissionError(message))['message'], message)

    def test_local_path_uses_argument_array_and_missing_opener_is_explicit(self):
        with patch('sys.platform', 'linux'), patch('shutil.which', return_value='/usr/bin/xdg-open'), patch('subprocess.run') as run:
            open_path(Path('/tmp/a file;literal.txt'))
            self.assertEqual(run.call_args.args[0], ['/usr/bin/xdg-open', '/tmp/a file;literal.txt'])
            self.assertTrue(run.call_args.kwargs['check'])
        with patch('sys.platform', 'linux'), patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(PlatformUnavailable, 'xdg-open'):
                open_path(Path('/tmp/example'))


class LinuxBridgeBoundaryTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(sys.platform == 'linux', 'Linux Secret Service boundary')
    async def test_native_routes_reject_and_clear_transient_secret(self):
        from olive.application.service_container import ServiceContainer
        from olive.bridge.host import Host
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as directory:
            host = Host(lambda *_: None)
            host.services = ServiceContainer(host.publish, host.confirm, directory, migrate=False)
            try:
                with patch('sys.platform', 'linux'), patch('secretstorage.dbus_init', side_effect=OSError('unavailable')):
                    host.services.desktop.perform = AsyncMock()
                    with self.assertRaises(PermissionError):
                        await host.execute('desktop.perform', {})
                    host.services.desktop.perform.assert_not_awaited()
                    # Native Linux support is capability-probed. Portable CI must
                    # not depend on whichever portal happens to run on its host.
                    native = host.services.desktop.linux
                    native.capabilities = {}
                    with patch.object(native, 'probe', AsyncMock()):
                        self.assertFalse((await host.execute('desktop.status', {}))['available'])
                    host.services.desktop.configure({'enabled': True})
                    with self.assertRaises(PlatformUnavailable):
                        await host.execute('desktop.perform', {})
                    host.services.desktop.perform.assert_not_awaited()
                    connection = host.services.mail.connections.save({'name': 'Synthetic', 'smtp': {'host': '127.0.0.1', 'port': 465, 'tls': 'tls'}})
                    args = {'record_id': connection['id'], 'revision': connection['revision'], 'secret': 'synthetic-only'}
                    with self.assertRaises(PlatformUnavailable) as raised:
                        await host.services.mail.call('mail.credential_store', args, manual=True)
                    self.assertIsNone(raised.exception.__context__)
                    self.assertEqual(args['secret'], '')
                    self.assertIsNone(host.services.mail.connections.get(connection['id'])['credential_ref'])
                    discord = {'token': 'synthetic-only'}
                    with self.assertRaises(PlatformUnavailable) as raised:
                        await host.execute('connections.discord_configure', discord)
                    self.assertIsNone(raised.exception.__context__)
                    self.assertEqual(discord['token'], '')
            finally:
                await host.shutdown()
