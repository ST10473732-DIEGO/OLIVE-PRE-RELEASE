"""Synthetic native-service regressions; live wallet checks are separately opt-in."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from olive.services.credential_vault import CredentialVault
from olive.services.linux_credentials import operate
from olive.services.linux_startup import configure, quote_exec
from olive.platform_support import PlatformUnavailable
from olive.desktop.linux_capabilities import capabilities

@unittest.skipUnless(sys.platform == 'linux', 'Linux native services')
class LinuxServicesTests(unittest.TestCase):
    def test_case_sensitive_profile_scope_and_windows_compatibility(self):
        with patch('sys.platform', 'linux'):
            self.assertNotEqual(CredentialVault('/tmp/Upper').namespace, CredentialVault('/tmp/upper').namespace)
        with patch('sys.platform', 'win32'):
            self.assertEqual(CredentialVault('/tmp/Upper').namespace, CredentialVault('/tmp/upper').namespace)
            self.assertTrue(CredentialVault('/tmp/Upper').namespace.startswith('DMDO/'))

    def test_locked_wallet_fails_closed_and_closes_connection(self):
        connection = MagicMock(); store = MagicMock(); store.is_locked.return_value = True
        with patch('secretstorage.dbus_init', return_value=connection), patch('secretstorage.Collection', return_value=store):
            with self.assertRaises(PlatformUnavailable): operate('put', 'synthetic', 'synthetic secret')
        store.create_item.assert_not_called(); connection.close.assert_called_once()

    def test_plain_dbus_session_refused_and_provider_errors_sanitized(self):
        connection = MagicMock(); store = MagicMock(); store.is_locked.return_value = False
        session = MagicMock(); session.encrypted = False
        with patch('secretstorage.dbus_init', return_value=connection), patch('secretstorage.Collection', return_value=store), patch('secretstorage.util.open_session', return_value=session):
            with self.assertRaises(PlatformUnavailable): operate('put', 'synthetic', 'synthetic secret')
        store.create_item.assert_not_called()
        with patch('secretstorage.dbus_init', side_effect=OSError('PRIVATE SECRET')):
            with self.assertRaises(PlatformUnavailable) as caught: operate('read', 'synthetic')
        self.assertNotIn('PRIVATE', str(caught.exception))

    def test_startup_enable_disable_and_unmanaged_protection(self):
        with tempfile.TemporaryDirectory() as directory, patch('sys.platform', 'linux'):
            root=Path(directory)/'a space % $ ` "';root.mkdir();(root/'run_olive.sh').touch()
            target=configure(True,root,root/'profile',directory)
            body=target.read_text();self.assertIn('Name=OLIVE',body);self.assertIn('%%',body)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            configure(True,root,root/'profile',directory)
            configure(False,root,root/'profile',directory);self.assertFalse(target.exists())
            target.write_text('[Desktop Entry]\nName=personal\n')
            with self.assertRaisesRegex(ValueError,'unmanaged'):configure(False,root,root/'profile',directory)
            with self.assertRaises(ValueError):quote_exec('bad\npath')

    def test_wayland_wins_over_xwayland_and_never_grants_input(self):
        value=capabilities({'XDG_SESSION_TYPE':'wayland','DISPLAY':':0'})
        self.assertEqual(value['session'],'wayland')
        self.assertIn('not yet integrated',value['remote_input'])
        self.assertEqual(capabilities({'DISPLAY':':0'})['session'],'x11')

@unittest.skipUnless(sys.platform == 'linux', 'Linux owned media runtime')
class LinuxMediaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_engine_is_not_owned_or_stopped(self):
        from unittest.mock import AsyncMock
        from olive.services.local_comfy_runtime import LocalComfyRuntime
        runtime=LocalComfyRuntime();runtime.root='/synthetic';runtime.python=sys.executable
        runtime.ready=AsyncMock(return_value=True)
        with patch('olive.studio_tooling.posix_process.start_owned_process',new_callable=AsyncMock) as start:
            await runtime.start_for('http://127.0.0.1:8188')
            await runtime.close();start.assert_not_awaited()
        self.assertFalse(runtime.manages('http://0.0.0.0:8188'))
        self.assertFalse(runtime.manages('http://127.0.0.1:9999'))

    async def test_missing_runtime_and_failed_start_are_honest(self):
        from unittest.mock import AsyncMock
        from olive.services.local_comfy_runtime import LocalComfyRuntime
        runtime=LocalComfyRuntime();runtime.root='/missing-olive-fixture';runtime.python=sys.executable
        runtime.ready=AsyncMock(return_value=False)
        with self.assertRaisesRegex(ValueError,'missing'):await runtime.start_for(runtime.host)
        with tempfile.TemporaryDirectory() as directory:
            runtime.root=directory;Path(directory,'main.py').write_text('raise SystemExit(1)\n')
            with self.assertRaisesRegex(RuntimeError,'exited'):await runtime.start_for(runtime.host)
            self.assertIsNone(runtime.process);self.assertIsNone(runtime.owner)

    async def test_linux_native_denials_hold_even_with_gateway_context(self):
        from olive.desktop.navigation import WindowsNavigationTool
        from olive.desktop.application_launch import launch_identity
        from olive.desktop.clipboard import clipboard_text
        from olive.desktop.emergency_stop import EmergencyStop
        from olive.agent.tool_schema import ToolContext
        with self.assertRaises(PlatformUnavailable):launch_identity(MagicMock())
        with self.assertRaises(PlatformUnavailable):clipboard_text('read')
        tool=WindowsNavigationTool(EmergencyStop(),'settings')
        with self.assertRaises(PlatformUnavailable):await tool.execute({'page':'display'},ToolContext('fixture',progress_callback=tool))
