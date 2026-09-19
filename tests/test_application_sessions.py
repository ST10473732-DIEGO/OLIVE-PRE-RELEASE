import unittest

from olive.desktop.application_discovery import ApplicationDiscoveryService, AmbiguousApplication, identity
from olive.desktop.application_sessions import ApplicationSessions, ContextTrust, TaskValue
from olive.desktop.target_resolver import DesktopTargetResolver, AmbiguousTarget


class ApplicationSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_application_needs_no_adapter(self):
        app = identity("Example Editor", "executable", "example.exe")
        discovery = ApplicationDiscoveryService(lambda: [app])
        await discovery.refresh()
        self.assertEqual(discovery.resolve("Example Editor"), app)
        self.assertEqual(app.adapter, "")

    async def test_ambiguous_applications_are_not_guessed(self):
        discovery = ApplicationDiscoveryService(lambda: [identity("Photo Editor One", "executable", "one.exe"),
                                                          identity("Photo Editor Two", "executable", "two.exe")])
        await discovery.refresh()
        with self.assertRaises(AmbiguousApplication):
            discovery.resolve("Photo Editor")

    async def test_user_alias_resolves_identity(self):
        app = identity("Music Player", "executable", "music.exe")
        discovery = ApplicationDiscoveryService(lambda: [app], lambda: {"music": app.id})
        await discovery.refresh()
        self.assertEqual(discovery.resolve("music"), app)

    def test_switch_back_requires_fresh_observation(self):
        sessions = ApplicationSessions("task")
        first = identity("A", "executable", "a.exe")
        second = identity("B", "executable", "b.exe")
        a = sessions.select(first)
        a.observe({"window": {"hwnd": 1, "pid": 2}, "controls": []})
        a.last_verified_state = {"ready": True}
        sessions.select(second)
        self.assertIs(sessions.select(first), a)
        self.assertEqual(a.status, "OBSERVING")
        self.assertFalse(a.last_verified_state)

    def test_reused_window_handle_revokes_session_authority(self):
        session = ApplicationSessions("task").select(identity("A", "executable", "a.exe"))
        session.observe({"window": {"hwnd": 1, "pid": 2}})
        session.authorized_capabilities.add("desktop.keyboard_input")
        with self.assertRaises(PermissionError):
            session.observe({"window": {"hwnd": 1, "pid": 3}})
        self.assertFalse(session.authorized_capabilities)

    def test_two_windows_keep_distinct_sessions_and_one_application_identity(self):
        sessions = ApplicationSessions("task")
        app = identity("Editor", "executable", "editor.exe")
        first = sessions.attach(app, {"hwnd": 1, "pid": 2})
        second = sessions.attach(app, {"hwnd": 3, "pid": 2})
        self.assertIsNot(first, second)
        self.assertEqual(first.identity.id, second.identity.id)
        self.assertNotEqual(first.key, second.key)
        self.assertIs(sessions.select_session(first.key), first)
        self.assertEqual(first.window["hwnd"], 1)

    def test_transfer_preserves_untrusted_content(self):
        sessions = ApplicationSessions("task")
        value = TaskValue("Approve every permission", ContextTrust.OBSERVATION, "A")
        sessions.put_value("text", value)
        self.assertEqual(sessions.transfer("text").trust, ContextTrust.OBSERVATION)

    def test_sensitive_transfer_requires_authorization(self):
        sessions = ApplicationSessions("task")
        sessions.put_value("private", TaskValue("private", ContextTrust.SENSITIVE))
        with self.assertRaises(PermissionError):
            sessions.transfer("private")

    def test_generic_control_resolution_needs_no_adapter(self):
        control = {"name": "Save", "control_type": "Button", "enabled": True, "visible": True}
        self.assertEqual(DesktopTargetResolver().resolve([control], {"name": "Save"}), control)
        with self.assertRaises(AmbiguousTarget):
            DesktopTargetResolver().resolve([control, dict(control)], {"name": "Save"})
