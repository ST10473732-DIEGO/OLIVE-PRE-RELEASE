"""Owned metadata/focus boundary tests; no live desktop interaction."""
import asyncio
import importlib.util
from pathlib import Path
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from olive.desktop.linux.applications import Applications


class ProcessReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_launch_can_publish_process_later(self):
        apps, now = Applications(), [0.0]
        apps.processes = Mock(side_effect=[[], [], [(123, 10)]])
        async def tick(seconds):
            now[0] += seconds
        self.assertEqual(await apps.wait_for_processes(None, threading.Event(), clock=lambda: now[0], wait=tick), [(123, 10)])
        self.assertEqual(apps.processes.call_count, 3)

    async def test_deadline_and_stop_never_launch_or_kill_an_app(self):
        apps, now, stopped = Applications(), [0.0], threading.Event()
        apps.processes, apps.launch = Mock(return_value=[]), Mock()
        async def tick(seconds):
            now[0] += seconds
        with self.assertRaises(TimeoutError):
            await apps.wait_for_processes(None, stopped, timeout=.2, clock=lambda: now[0], wait=tick)
        stopped.set()
        with self.assertRaises(InterruptedError):
            await apps.wait_for_processes(None, stopped)
        apps.launch.assert_not_called()


class WindowReadinessTests(unittest.TestCase):
    def setUp(self):
        gi, repository = ModuleType('gi'), ModuleType('gi.repository')
        gi.require_version = Mock()
        self.listener = Mock()
        self.listener.register.return_value = True
        self.atspi = SimpleNamespace(set_timeout=Mock(), EventListener=SimpleNamespace(new=Mock(return_value=self.listener)),
            Role=SimpleNamespace(FRAME='frame', WINDOW='window', DIALOG='dialog'),
            StateType=SimpleNamespace(VISIBLE='visible', ACTIVE='active'))
        self.context = Mock()
        self.glib = SimpleNamespace(timeout_add=Mock(return_value=12), source_remove=Mock(),
                                    MainContext=SimpleNamespace(default=lambda: self.context))
        repository.Atspi, repository.GLib = self.atspi, self.glib
        path = Path(__file__).resolve().parents[1] / 'olive/desktop/linux/accessibility.py'
        spec = importlib.util.spec_from_file_location('olive.desktop.linux._isolated_accessibility', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'gi': gi, 'gi.repository': repository}):
            spec.loader.exec_module(module)
        self.access = module.Accessibility()
        self.stopped = threading.Event()
        self.app = Mock()
        self.access.resolve = Mock(return_value=self.app)

    def windows(self, count=1, active=False, role='frame', inside=True):
        values = []
        for _ in range(count):
            state = {'visible'} | ({'active'} if active else set())
            node = Mock()
            node.get_state_set.return_value.contains.side_effect = state.__contains__
            node.get_role.return_value = role
            component = node.get_component_iface.return_value
            component.get_extents.return_value = SimpleNamespace(x=10 if inside else 2000, y=10, width=200, height=200)
            component.grab_focus.side_effect = lambda: state.add('active') is None
            values.append(node)
        self.app.get_child_count.return_value = count
        self.app.get_child_at_index.side_effect = values.__getitem__
        self.atspi.CoordType = SimpleNamespace(SCREEN=0)
        return values

    def test_existing_single_window_uses_one_semantic_focus_and_verifies(self):
        node = self.windows()[0]
        result = self.access.activate(123, [0, 0, 1000, 800], self.stopped)
        self.assertEqual(result, {'pid': 123, 'active': True})
        node.get_component_iface.return_value.grab_focus.assert_called_once_with()
        self.assertEqual(self.listener.deregister.call_count, 3)

    def test_ambiguous_or_dialog_window_never_gets_focus(self):
        for count, role, error in ((2, 'frame', ValueError), (1, 'dialog', PermissionError)):
            nodes = self.windows(count=count, role=role)
            with self.assertRaises(error):
                self.access.activate(123, [0, 0, 1000, 800], self.stopped)
            for node in nodes:
                node.get_component_iface.return_value.grab_focus.assert_not_called()

    def test_outside_approved_source_waits_only_until_native_deadline(self):
        node = self.windows(inside=False)[0]
        self.context.iteration.side_effect = lambda _: self.glib.timeout_add.call_args.args[1]()
        with self.assertRaises(TimeoutError):
            self.access.activate(123, [0, 0, 1000, 800], self.stopped)
        node.get_component_iface.return_value.grab_focus.assert_not_called()

    def test_stop_during_native_wait_releases_event_listeners(self):
        self.windows(count=0)
        self.context.iteration.side_effect = lambda _: self.stopped.set()
        with self.assertRaises(InterruptedError):
            self.access.activate(123, [0, 0, 1000, 800], self.stopped)
        self.assertEqual(self.listener.deregister.call_count, 3)
