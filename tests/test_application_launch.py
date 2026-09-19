import unittest
from unittest.mock import AsyncMock, Mock, patch
from olive.desktop.application_discovery import ApplicationDiscoveryService, identity
from olive.desktop.application_launch import ApplicationLauncher, ApplicationLaunchTool, matches
from olive.desktop.emergency_stop import EmergencyStop
from olive.agent.tool_schema import ToolContext


class ApplicationLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_preserves_display_name_when_running_path_duplicates(self):
        catalog = [identity("Google Chrome", "executable", "chrome.exe"), identity("chrome", "executable", "chrome.exe")]
        service = ApplicationDiscoveryService(catalog=lambda: catalog)
        await service.refresh()
        self.assertEqual(service.resolve("Google Chrome").display_name, "Google Chrome")
        self.assertEqual(len(service.applications), 1)

    def test_window_matching_uses_identity_not_spoofed_title(self):
        app = identity("Example", "app_id", "Package!App")
        self.assertFalse(matches(app, {"title": "Example", "package_identity": "Other!App"}))
        self.assertTrue(matches(app, {"title": "Untrusted", "package_identity": "Package!App"}))

    async def test_direct_launch_tool_has_no_authorization(self):
        tool = ApplicationLaunchTool(Mock(applications=[]), EmergencyStop())
        with self.assertRaises(PermissionError):
            await tool.execute({"application_id": "invented"}, ToolContext("task"))

    async def test_unknown_catalog_id_cannot_launch(self):
        desktop = Mock(discovery=Mock(applications=[]), stop_event=EmergencyStop())
        launcher = ApplicationLauncher(desktop)
        with self.assertRaises(ValueError):
            await launcher.open("invented")
        desktop.gateway.approval.assert_not_called()
