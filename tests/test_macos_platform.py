"""macOS foundations exercised from any OS: Keychain vault, open, truthful states.

Physical validation on a Mac is still required (docs/install/macos.md checklist).
"""
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from olive.platform_support import PlatformUnavailable


class FakeKeychain:
    """Stands in for keyring.backends.macOS.Keyring (Security framework) off macOS."""
    priority = 5

    def __init__(self):
        self.items, self.locked = {}, False

    def _check(self):
        if self.locked:
            raise RuntimeError("Can't get password from keychain: (-25308, 'PRIVATE DETAIL')")

    def set_password(self, service, username, password):
        self._check()
        self.items[(service, username)] = password

    def get_password(self, service, username):
        self._check()
        return self.items.get((service, username))

    def delete_password(self, service, username):
        self._check()
        del self.items[(service, username)]


def fake_keyring(keychain):
    macos = types.ModuleType('keyring.backends.macOS')
    macos.Keyring = MagicMock(return_value=keychain)
    macos.Keyring.priority = 5
    backends = types.ModuleType('keyring.backends')
    backends.macOS = macos
    root = types.ModuleType('keyring')
    root.backends = backends
    return {'keyring': root, 'keyring.backends': backends, 'keyring.backends.macOS': macos}


class MacCredentialVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def vault(self):
        from olive.services.credential_vault import CredentialVault
        with patch('sys.platform', 'darwin'):
            return CredentialVault(self.temp.name)

    def test_keychain_round_trip_without_plaintext_files(self):
        keychain = FakeKeychain()
        vault = self.vault()
        with patch('sys.platform', 'darwin'), patch.dict(sys.modules, fake_keyring(keychain)):
            self.assertTrue(vault.available)
            self.assertFalse(vault.contains('discord-bot'))
            vault.put('discord-bot', 'synthetic-secret')
            self.assertTrue(vault.contains('discord-bot'))
            self.assertEqual(vault.read_for_provider('discord-bot'), 'synthetic-secret')
            vault.remove('discord-bot')
            vault.remove('discord-bot')  # Absent slot: no error.
            self.assertFalse(vault.contains('discord-bot'))
        self.assertTrue(vault.namespace.startswith('OLIVE/'))
        self.assertEqual(keychain.items, {})
        import os
        self.assertEqual(os.listdir(self.temp.name), [])  # Nothing written next to the profile.

    def test_locked_keychain_is_unavailable_and_provider_text_never_leaks(self):
        keychain = FakeKeychain()
        keychain.locked = True
        vault = self.vault()
        with patch('sys.platform', 'darwin'), patch.dict(sys.modules, fake_keyring(keychain)):
            with self.assertRaises(PlatformUnavailable) as caught:
                vault.put('discord-bot', 'synthetic-secret')
        self.assertIn('macOS login keychain', str(caught.exception))
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertNotIn('synthetic-secret', str(caught.exception))

    def test_missing_security_backend_reports_the_macos_message(self):
        vault = self.vault()
        broken = {'keyring': None, 'keyring.backends': None, 'keyring.backends.macOS': None}
        with patch('sys.platform', 'darwin'), patch.dict(sys.modules, broken):
            self.assertFalse(vault.available)
            with self.assertRaisesRegex(PlatformUnavailable, 'macOS login keychain'):
                vault.require_available()

    def test_linux_message_is_unchanged(self):
        from olive.services.credential_vault import CredentialVault
        from olive.services.linux_credentials import UNAVAILABLE
        with patch('sys.platform', 'linux'), patch('olive.services.linux_credentials.available', return_value=False):
            with self.assertRaises(PlatformUnavailable) as caught:
                CredentialVault(self.temp.name).require_available()
        self.assertEqual(str(caught.exception), UNAVAILABLE)


class MacOpenPathTests(unittest.TestCase):
    def test_open_uses_the_system_open_with_an_absolute_path(self):
        from olive import platform_support
        with patch('sys.platform', 'darwin'), patch('os.path.isfile', return_value=True), patch('subprocess.run') as run:
            platform_support.open_path('relative/file.txt')
        command = run.call_args.args[0]
        self.assertEqual(command[0], '/usr/bin/open')
        self.assertTrue(command[1].startswith('/'))
        with patch('sys.platform', 'darwin'), patch('os.path.isfile', return_value=False), patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(PlatformUnavailable, 'macOS'):
                platform_support.open_path('/x')


class MacTruthfulStatesTests(unittest.TestCase):
    def test_creator_runtimes_are_not_claimed_validated_on_macos(self):
        from olive.services.runtime_discovery import Located
        for name in ('comfy', 'video_comfy', 'voicestudio', 'ollama'):
            self.assertFalse(Located(name, 'found').to_dict('darwin')['validated_on_platform'])
            self.assertTrue(Located(name, 'found').to_dict('linux')['validated_on_platform'])

    def test_windows_only_features_name_macos(self):
        from olive.platform_support import require_windows
        with patch('sys.platform', 'darwin'), self.assertRaisesRegex(PlatformUnavailable, 'not available on macOS'):
            require_windows('Native application control')


if __name__ == '__main__':
    unittest.main()


class MacStudioTerminalTests(unittest.TestCase):
    def test_terminal_is_a_truthful_unavailable_state_on_macos_and_without_pywinpty(self):
        import asyncio
        from olive.studio_tooling.pty import TerminalSession
        loop = asyncio.new_event_loop()
        try:
            session = TerminalSession('s', 'w', '/', 'bash', 'Terminal', loop, lambda *a: None)
            with patch('sys.platform', 'darwin'), self.assertRaisesRegex(PlatformUnavailable, 'not available on macOS'):
                session.start({})
            with patch('sys.platform', 'win32'), patch('importlib.util.find_spec', return_value=None), \
                    self.assertRaisesRegex(PlatformUnavailable, 'pywinpty'):
                session.start({})
        finally:
            loop.close()
