"""Exercise real portal ownership code with only the native DBus boundary replaced."""
import importlib.util
from pathlib import Path
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def portal_type():
    gi = ModuleType('gi')
    gi.require_version = Mock()
    repository = ModuleType('gi.repository')
    repository.Gio = Mock()
    repository.GLib = SimpleNamespace(Variant=lambda signature, value: value)
    path = Path(__file__).resolve().parents[1] / 'olive/desktop/linux/portal.py'
    spec = importlib.util.spec_from_file_location('isolated_portal', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict('sys.modules', {'gi': gi, 'gi.repository': repository}):
        spec.loader.exec_module(module)
    return module.Portal


class PortalCleanupTests(unittest.TestCase):
    def setUp(self):
        cls = portal_type()
        self.portal = cls.__new__(cls)
        self.portal.stopped = threading.Event()
        self.portal.shortcut = self.portal.remote = None
        self.portal.stop_verified = False
        self.portal.sessions = set()
        self.portal.streams = []
        self.portal.close_path = Mock()
        self.portal.request = Mock()
        def create(interface):
            path = '/owned/' + interface
            self.portal.sessions.add(path)
            return path
        self.portal.create = Mock(side_effect=create)

    def test_denied_or_timed_out_binding_releases_exact_shortcut_session(self):
        for error in (PermissionError('Denied'), TimeoutError('Consent deadline')):
            with self.subTest(error=type(error).__name__):
                self.portal.request.side_effect = error
                with self.assertRaises(type(error)):
                    self.portal.bind_stop()
                self.assertIsNone(self.portal.shortcut)
                self.assertEqual(self.portal.sessions, set())
                self.portal.close_path.assert_called_with('Session', '/owned/GlobalShortcuts')

    def test_missing_assigned_key_does_not_leave_an_unusable_session(self):
        self.portal.request.return_value = {'shortcuts': [('stop', {})]}
        with self.assertRaises(PermissionError):
            self.portal.bind_stop()
        self.assertIsNone(self.portal.shortcut)
        self.assertEqual(self.portal.sessions, set())

    def test_control_denial_preserves_verified_shortcut_and_closes_control(self):
        self.portal.shortcut = '/owned/GlobalShortcuts'
        self.portal.sessions.add(self.portal.shortcut)
        self.portal.stop_verified = True
        self.portal.request.side_effect = PermissionError('Denied')
        with self.assertRaises(PermissionError):
            self.portal.start()
        self.assertIsNone(self.portal.remote)
        self.assertEqual(self.portal.sessions, {'/owned/GlobalShortcuts'})
        self.assertTrue(self.portal.stop_verified)
        self.portal.close_path.assert_called_once_with('Session', '/owned/RemoteDesktop')

    def test_second_start_never_replaces_an_owned_live_session(self):
        self.portal.remote = '/owned/existing'
        self.portal.stop_verified = True
        with self.assertRaises(ValueError):
            self.portal.start()
        self.portal.create.assert_not_called()
