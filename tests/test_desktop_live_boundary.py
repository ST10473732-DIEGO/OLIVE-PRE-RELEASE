import tempfile
import unittest
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.agent.tool_schema import ToolContext
from olive.desktop.capabilities import capability_map
from olive.desktop.settings import validate


class DesktopBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.services = ServiceContainer(lambda *args: None, AsyncMock(return_value=ConfirmationResponse(False)),
                                         data_dir=self.folder.name, migrate=False)

    async def asyncTearDown(self):
        await self.services.shutdown()

    async def test_disabled_desktop_cannot_enumerate(self):
        with self.assertRaises(PermissionError):
            await self.services.desktop.list_windows()

    async def test_uia_switch_does_not_disable_independent_providers(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        desktop = self.services.desktop
        desktop.configure({"enabled": True, "uia": False})
        desktop.gateway.check()
        session = ApplicationSession(identity("Test", "executable", "test.exe"), "task")
        with self.assertRaisesRegex(PermissionError, "UI Automation"):
            await desktop.gateway.observe(session)
        desktop.stop_event.set()
        import asyncio
        with self.assertRaises(asyncio.CancelledError):
            desktop.gateway.check()

    async def test_direct_tool_invocation_has_no_gateway_capability(self):
        tool = self.services.tool_registry.require("desktop.invoke")
        with self.assertRaises(PermissionError):
            await tool.execute({"window": {}}, ToolContext("test"))

    def test_stop_is_synchronous(self):
        self.services.desktop.stop_event.set()
        self.assertTrue(self.services.desktop.status()["stopped"])

    def test_capabilities_are_untrusted_and_exclude_secrets(self):
        controls = [{"name": "Save", "enabled": True, "visible": True, "actions": ["invoke"]},
                    {"name": "Password", "password": True, "enabled": True, "visible": True, "actions": ["set_text"]}]
        result = capability_map({"controls": controls})
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["untrusted_content"])

    def test_conservative_settings(self):
        self.assertFalse(validate()["enabled"])
        self.assertEqual(validate()["keyboard_policy"], "deny")
        with self.assertRaises(ValueError):
            validate({"user_takeover": "ignore"})

    def test_custom_secret_fields_require_takeover(self):
        from olive.desktop.privacy import secret_field
        for name in ("Recovery code", "Enter seed phrase", "Private key", "Account password"):
            self.assertTrue(secret_field(name))
        self.assertFalse(secret_field("Search documentation"))

    async def test_cached_inspection_cannot_override_new_deny(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        self.services.desktop.configure({"enabled": True})
        session = ApplicationSession(identity("Test", "executable", "test.exe"), "task")
        session.authorized_capabilities.add("desktop.inspect_application")
        self.services.permissions.save({"desktop.inspect_application": "deny"})
        with self.assertRaises(PermissionError):
            await self.services.desktop.gateway.observe(session)

    async def test_unknown_application_policy_is_enforced(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        self.services.desktop.configure({"enabled": True, "unknown_app_policy": "deny"})
        session = ApplicationSession(identity("Unknown", "executable", "unknown.exe"), "task")
        self.services.permissions.save({"desktop.inspect_application": "allow"})
        with self.assertRaisesRegex(PermissionError, "unknown-app policy"):
            await self.services.desktop.gateway.observe(session)

    async def test_packaged_launch_identity_is_preserved_when_inspecting_window(self):
        from olive.desktop.application_discovery import identity
        desktop = self.services.desktop
        desktop.configure({"enabled": True})
        window = {"hwnd": 1, "pid": 2, "application": "Fixture", "executable": "fixture.exe", "package_identity": "FixturePackage!App"}
        desktop.windows = {"1": window}
        desktop.gateway.observe = AsyncMock(return_value={"window": window, "controls": []})
        await desktop.inspect("1")
        session = desktop.sessions.sessions[desktop.sessions.current]
        self.assertEqual(session.identity.id, identity("Fixture", "app_id", "FixturePackage!App").id)

    def test_application_only_permissions_can_be_saved_through_ui_controller(self):
        result = self.services.data.save_permissions({"desktop.control_application": "ask"},
            [{"permission": "desktop.control_application", "application": "fixture", "decision": "deny"}])
        self.assertEqual(result["scopes"][0]["application"], "fixture")

    async def test_search_cannot_press_enter_in_an_arbitrary_form(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        from olive.desktop.workflow import DesktopStep
        self.services.desktop.configure({"enabled": True, "keyboard_policy": "ask"})
        session = ApplicationSession(identity("Fixture", "executable", "fixture.exe"), "task")
        session.observe({"window": {}, "controls": [{"runtime_id": "field", "name": "Message", "control_type": "Edit"}]})
        step = DesktopStep(session.identity.id, "search", {"runtime_id": "field"}, {"text": "Query"}, {"name": "Result"}, "desktop.control_application")
        with self.assertRaisesRegex(PermissionError, "search field"):
            await self.services.desktop.gateway.authorize(session, step)
        session.observations[-1]["controls"][0]["name"] = "Message #search"
        with self.assertRaisesRegex(PermissionError, "search field"):
            await self.services.desktop.gateway.authorize(session, step)

    async def test_punctuated_send_and_store_get_cannot_bypass_preview(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        from olive.desktop.workflow import DesktopStep
        self.services.desktop.configure({"enabled": True})
        session = ApplicationSession(identity("Fixture", "executable", "fixture.exe"), "task")
        for label in ("Send.", "Get. ", "Install…", "Purchase!"):
            session.observe({"window": {}, "controls": [{"runtime_id": "action", "name": label, "control_type": "Button"}]})
            step = DesktopStep(session.identity.id, "invoke", {"runtime_id": "action"}, {}, {"name": "Done"}, "desktop.control_application")
            with self.assertRaisesRegex(PermissionError, "consequence preview"):
                await self.services.desktop.gateway.authorize(session, step)

    async def test_stop_cancels_pending_auxiliary_operation(self):
        import asyncio
        desktop = self.services.desktop
        desktop.configure({"enabled": True})
        started = asyncio.Event()
        async def pending(*args):
            started.set()
            await asyncio.Event().wait()
        desktop.clipboard.run = pending
        task = asyncio.create_task(desktop.clipboard_action("read"))
        await started.wait()
        desktop.stop()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(desktop.operation)

    async def test_shutdown_drains_operation_before_closing_browser(self):
        import asyncio
        desktop = self.services.desktop
        desktop.configure({"enabled": True})
        started = asyncio.Event()
        finished = asyncio.Event()
        async def pending(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                finished.set()
        async def close_browser():
            self.assertTrue(finished.is_set())
        desktop.clipboard.run = pending
        desktop.browser.shutdown = AsyncMock(side_effect=close_browser)
        task = asyncio.create_task(desktop.clipboard_action("read"))
        await started.wait()
        await desktop.shutdown()
        self.assertTrue(task.cancelled())
        self.assertIsNone(desktop.operation)

    async def test_permission_revoked_during_confirmation_remains_authoritative(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        self.services.desktop.configure({"enabled": True})
        session = ApplicationSession(identity("Test", "executable", "test.exe"), "task")
        async def revoke(request):
            self.services.permissions.save({"desktop.control_application": "deny"})
            return ConfirmationResponse(True)
        self.services.desktop.gateway.confirmations.request = revoke
        with self.assertRaisesRegex(PermissionError, "revoked"):
            await self.services.desktop.gateway.approval(session, "desktop.control_application", "Test", {}, always=True)

    async def test_input_revoked_after_later_approval_never_reaches_provider(self):
        from olive.desktop.application_discovery import identity
        from olive.desktop.application_sessions import ApplicationSession
        from olive.desktop.workflow import DesktopStep
        desktop = self.services.desktop
        desktop.configure({"enabled": True, "keyboard_policy": "ask"})
        session = ApplicationSession(identity("Test", "executable", "test.exe"), "task")
        session.window = {"hwnd": 1, "pid": 2}
        session.observe({"window": session.window, "controls": [{"name": "Editor", "runtime_id": "edit", "enabled": True, "visible": True}]})
        async def approve(request):
            if request.tool_name == "desktop.control_application":
                self.services.permissions.save({"desktop.keyboard_input": "deny"})
            return ConfirmationResponse(True)
        desktop.gateway.confirmations.request = approve
        desktop.provider.call = AsyncMock()
        step = DesktopStep(session.identity.id, "set_text", {"runtime_id": "edit"}, {"text": "Fixture"},
                           {"value": "Fixture"}, "desktop.control_application")
        permit = await desktop.gateway.authorize(session, step)
        with self.assertRaisesRegex(PermissionError, "revoked"):
            await desktop.gateway.execute(session, step, permit, desktop.stop_event)
        desktop.provider.call.assert_not_awaited()
