import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from olive.desktop.application_discovery import identity
from olive.desktop.navigation import WindowsNavigation


class NavigationAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.desktop = SimpleNamespace(
            s=SimpleNamespace(tool_registry=Mock()), stop_event=Mock(),
            discovery=SimpleNamespace(applications=[], refresh=AsyncMock()),
            gateway=SimpleNamespace(approval=AsyncMock(), require_not_denied=Mock()))
        self.navigation = WindowsNavigation(self.desktop)

    async def test_explorer_uses_discovered_executable_scope(self):
        with patch.dict("os.environ", {"WINDIR": "C:/Windows"}):
            actual = await self.navigation.application_identity("folder")
        expected = identity("explorer", "executable", str(Path("C:/Windows") / "explorer.exe"))
        self.assertEqual(actual.id, expected.id)

    async def test_settings_uses_installed_package_scope(self):
        app = identity("Settings", "app_id", "windows.immersivecontrolpanel_example!App")
        self.desktop.discovery.applications = [app]
        self.assertIs(await self.navigation.application_identity("settings"), app)

    async def test_missing_or_ambiguous_settings_never_launches(self):
        with self.assertRaises(LookupError):
            await self.navigation.open_settings()
        self.desktop.discovery.applications = [
            identity("Settings", "app_id", "windows.immersivecontrolpanel_one!App"),
            identity("Settings", "app_id", "windows.immersivecontrolpanel_two!App")]
        with self.assertRaises(LookupError):
            await self.navigation.open_settings()
        self.desktop.s.tool_registry.require.assert_not_called()

    async def test_folder_read_revoked_during_navigation_confirmation(self):
        self.desktop.gateway.require_not_denied.side_effect = PermissionError("Revoked")
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PermissionError):
                await self.navigation.open_folder(folder)
        self.assertEqual(self.desktop.gateway.approval.await_count, 2)
        self.desktop.s.tool_registry.require.assert_not_called()
