"""Owned-only diagnostic outcomes; controlled processes, no live UI access."""
import unittest
import sys
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
import psutil
from tests.test_owned_launch import fixture, window, Process
from olive.desktop.owned_launch import NoOwnedWindow, AmbiguousOwnedWindow
from olive.runtime.request_diagnostics import RequestDiagnostic, current


class ResolutionDiagnosticsTests(unittest.TestCase):
    def test_zero_and_multiple_are_distinct_and_request_correlated(self):
        root, record = fixture()
        diagnostic = RequestDiagnostic('request', 'desktop.attach_launch')
        token = current.set(diagnostic)
        try:
            for values, error, outcome in [([], NoOwnedWindow, 'no_eligible_owned_window'),
                    ([window(), window(hwnd=51)], AmbiguousOwnedWindow, 'multiple_eligible_owned_windows')]:
                with self.assertRaises(error):
                    record.resolve(process_factory=lambda _: root, window_reader=lambda _: values)
                self.assertEqual(diagnostic.resolution['eligible_count'], len(values))
                self.assertEqual(diagnostic.resolution['outcome'], outcome)
                self.assertEqual(diagnostic.resolution['launch_id'], record.reference)
                self.assertTrue(diagnostic.resolution['process_alive'])
                self.assertNotIn('Same title', str(diagnostic.resolution))
        finally:
            current.reset(token)

    def test_enumeration_failure_is_not_empty_result(self):
        root, record = fixture()
        original = OSError('controlled enumeration failure')
        def read(_): raise original
        with self.assertRaises(OSError) as error:
            record.resolve(process_factory=lambda _: root, window_reader=read)
        self.assertIs(error.exception, original)
        self.assertEqual(record.resolution['outcome'], 'enumeration_failure')
        self.assertIsNone(record.resolution['eligible_count'])

    def test_exit_identity_and_filters_are_distinct(self):
        root, record = fixture()
        def exited(_): raise psutil.NoSuchProcess(10)
        with self.assertRaises(psutil.NoSuchProcess): record.resolve(process_factory=exited)
        self.assertFalse(record.resolution['process_alive'])
        self.assertEqual(record.resolution['outcome'], 'owned_process_exited')
        root.created = 20
        with self.assertRaises(PermissionError): record.resolve(process_factory=lambda _: root)
        self.assertEqual(record.resolution['identity_failure'], 'Launcher lifetime or executable changed')
        root.created = 10
        root.descendants = [Process(11, 'runtime.exe', argv=['launcher.exe', 'other.py'], parent=root)]
        with self.assertRaises(NoOwnedWindow):
            record.resolve(process_factory=lambda _: root, window_reader=lambda _: [window(99)])
        self.assertEqual(record.resolution['initial']['command_rejected'], 1)
        self.assertEqual(record.resolution['window_rejections']['unowned_pid'], 1)
        self.assertEqual(record.resolution['candidates'], [])

    @unittest.skipUnless(sys.platform == "win32", "Windows native UI/ConPTY requires Windows")
    def test_owned_visibility_and_title_filters_counted_without_unrelated_reads(self):
        from olive.desktop.windows_observation import windows_for_processes
        counts = {}
        with patch('win32gui.EnumWindows', side_effect=lambda f, _: [f(h, None) for h in (1,2,3)]), \
             patch('win32process.GetWindowThreadProcessId', side_effect=lambda h: (1,99 if h==3 else 10)), \
             patch('win32gui.IsWindowVisible', side_effect=lambda h: h==2) as visible, \
             patch('olive.desktop.windows_observation.inspect_window', return_value={**window(), 'title':''}) as inspect:
            self.assertEqual(windows_for_processes({10:10}, counts), [])
        self.assertEqual(counts, dict(owned_handles=2, invisible=1, empty_title=1, returned=0))
        self.assertEqual(visible.call_count, 2)
        inspect.assert_called_once_with(2)


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_invisible_windows_then_unique_revalidate_in_one_request(self):
        from olive.desktop.owned_window_wait import wait_for_owned_window
        root, record = fixture()
        now = [0.0]
        calls = []
        async def sleep(delay): now[0] += delay
        async def probe():
            calls.append(1)
            return record.resolve(process_factory=lambda _: root,
                window_reader=lambda _: [] if len(calls)==1 else [window()])
        found = await wait_for_owned_window(record, lambda: None, clock=lambda:now[0], sleep=sleep, probe=probe)
        self.assertEqual(found['hwnd'], 50)
        self.assertEqual(record.resolution['wait']['first']['eligible_count'], 0)
        self.assertEqual(record.resolution['wait']['attempts'], 2)
        self.assertEqual(record.resolution['revalidation']['accepted'], 1)

    async def test_ambiguity_identity_and_enumeration_never_retried(self):
        from olive.desktop.owned_window_wait import wait_for_owned_window
        for error in (AmbiguousOwnedWindow('ambiguous'), PermissionError('identity'), OSError('enumeration'), TimeoutError('provider timeout'), psutil.NoSuchProcess(10)):
            record = SimpleNamespace(resolution={})
            calls=[]
            async def probe(): calls.append(1); raise error
            with self.assertRaises(type(error)) as caught:
                await wait_for_owned_window(record, lambda:None, probe=probe)
            self.assertIs(caught.exception,error)
            self.assertEqual(len(calls),1)

    async def test_timeout_distinct_from_ambiguity_without_wall_clock_sleep(self):
        from olive.desktop.owned_window_wait import wait_for_owned_window, OwnedWindowTimeout
        now=[0.0];record=SimpleNamespace(resolution={});calls=[]
        async def probe():
            calls.append(1);record.resolution={'eligible_count':0};raise NoOwnedWindow('not visible')
        async def sleep(delay):now[0]+=delay
        with self.assertRaisesRegex(OwnedWindowTimeout,'readiness'):
            await wait_for_owned_window(record,lambda:None,timeout=.1,clock=lambda:now[0],sleep=sleep,probe=probe)
        self.assertEqual(len(calls),2)
        self.assertEqual(record.resolution['outcome'],'owned_window_readiness_timeout')

    async def test_exit_or_reused_identity_after_first_zero_stops_wait(self):
        from olive.desktop.owned_window_wait import wait_for_owned_window
        for error in (psutil.NoSuchProcess(10), PermissionError('reused')):
            record=SimpleNamespace(resolution={});calls=[]
            async def probe():
                calls.append(1);record.resolution={}
                if len(calls)==1:raise NoOwnedWindow('not visible')
                raise error
            async def sleep(_):pass
            with self.assertRaises(type(error)):
                await wait_for_owned_window(record,lambda:None,sleep=sleep,probe=probe)
            self.assertEqual(len(calls),2)

    async def test_stop_cancels_actual_controller_wait_without_observation(self):
        from unittest.mock import AsyncMock, Mock
        from olive.application.desktop_controller import DesktopController
        from olive.desktop.launch_targets import LaunchTargets
        # Exercise the same operation ownership/Stop cancellation used by Electron.
        d=object.__new__(DesktopController)
        from olive.desktop.emergency_stop import EmergencyStop
        d.stop_event=EmergencyStop();d.universal=SimpleNamespace(owner=None)
        d.operation=None;d.gateway=Mock();d.publish=Mock();d.status=Mock(return_value={})
        d.inspect_target=AsyncMock(side_effect=AssertionError('Cancelled attach observed'))
        d.launch_targets=LaunchTargets(d)
        record=SimpleNamespace(resolution={})
        began=asyncio.Event();waiting=asyncio.Event()
        async def probe():
            began.set();record.resolution={};raise NoOwnedWindow('not visible')
        async def sleep(_):waiting.set();await asyncio.Future()
        from olive.desktop.owned_window_wait import wait_for_owned_window
        async def wait(r,check):return await wait_for_owned_window(r,check,probe=probe,sleep=sleep)
        d.launch_targets.records['owned']=record
        with patch('olive.desktop.launch_targets.wait_for_owned_window',side_effect=wait):
            task=asyncio.create_task(d.attach_launch('owned'))
            await waiting.wait();d.stop()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(d.stop_event.is_set());self.assertIsNone(d.operation)
        d.inspect_target.assert_not_called()
