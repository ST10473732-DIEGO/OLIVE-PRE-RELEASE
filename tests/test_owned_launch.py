"""Controlled process/window fixtures; no real desktop interaction."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from olive.desktop.owned_launch import OwnedLaunch, canonical
from olive.desktop.application_discovery import identity
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


class Process:
    def __init__(self,pid,exe='launcher.exe',argv=None,created=10,parent=None):
        self.pid,self.path,self.argv,self.created,self.owner=pid,exe,argv or ['launcher.exe','script.py'],created,parent
        self.descendants=[]
    def exe(self): return self.path
    def cmdline(self): return self.argv
    def create_time(self): return self.created
    def parent(self): return self.owner
    def children(self,recursive=True): return self.descendants


def fixture():
    root=Process(10)
    record=OwnedLaunch(identity('Fixture','executable','script.py'),10,10,canonical('launcher.exe'),
                       ('launcher.exe','script.py'),tuple(map(canonical,['launcher.exe','runtime.exe'])))
    return root,record


def window(pid=10,exe='launcher.exe',created=10,hwnd=50):
    return dict(pid=pid,executable=exe,process_created=created,hwnd=hwnd,title='Same title',application='fixture')


class OwnedIdentityTests(unittest.TestCase):
    def test_launch_approval_shows_executable_script_and_scope_without_json(self):
        from olive.bridge.presentation import approval_presentation
        result=approval_presentation({'tool_name':'terminal.execute','summary':'Launch selected script',
            'arguments':{'executable':'runtime.exe','arguments':['selected.py'],'file_hashes':{'selected.py':'hash'}}})
        self.assertIn('runtime.exe',result['content']);self.assertIn('selected.py',result['content'])
        self.assertIn('separate permissions',result['scope'])
        self.assertIn('not in an execution sandbox',result['consequence'])

    def test_direct_window_match(self):
        root,r=fixture()
        value=r.resolve(process_factory=lambda _:root,window_reader=lambda _: [window()])
        self.assertEqual(value['pid'],10)

    def test_child_requires_relationship_exact_script_and_expected_runtime(self):
        root,r=fixture(); child=Process(11,'runtime.exe',created=11,parent=root);root.descendants=[child]
        seen=[]
        value=r.resolve(process_factory=lambda _:root,window_reader=lambda p:seen.append(p) or [window(11,'runtime.exe',11)])
        self.assertEqual(value['pid'],11)
        self.assertEqual(seen,[{10:10,11:11}])

    def test_same_title_unrelated_process_rejected(self):
        root,r=fixture()
        with self.assertRaises(LookupError):
            r.resolve(process_factory=lambda _:root,window_reader=lambda _: [window(99)])

    def test_unrelated_python_script_and_unexpected_runtime_rejected(self):
        for exe,args in [('runtime.exe',['launcher.exe','other.py']),('unknown.exe',['launcher.exe','script.py'])]:
            root,r=fixture();root.descendants=[Process(11,exe,argv=args,created=11,parent=root)]
            self.assertEqual(r.processes(lambda _:root),{10:10})

    def test_unrelated_parent_and_reused_pid_rejected(self):
        root,r=fixture();other=Process(10,created=9)
        root.descendants=[Process(11,'runtime.exe',created=11,parent=other)]
        with self.assertRaises(PermissionError):r.processes(lambda _:root)
        root.descendants=[];root.created=20
        with self.assertRaises(PermissionError):r.processes(lambda _:root)

    def test_closed_ambiguous_and_replaced_window_rejected(self):
        root,r=fixture()
        for values in [[],[window(),window(hwnd=51)], [window(created=9)]]:
            with self.assertRaises(LookupError):r.resolve(process_factory=lambda _:root,window_reader=lambda _:values)
        r.resolve(process_factory=lambda _:root,window_reader=lambda _: [window()])
        with self.assertRaises(PermissionError):
            r.resolve(process_factory=lambda _:root,window_reader=lambda _: [window(hwnd=51)])

    def test_pid_filter_precedes_unrelated_title_or_metadata_reads(self):
        from olive.desktop.windows_observation import windows_for_processes
        def enumerate_handles(callback,unused):
            callback(100,None);callback(200,None)
        with patch('win32gui.EnumWindows',side_effect=enumerate_handles), \
             patch('win32process.GetWindowThreadProcessId',side_effect=lambda h:(1,10 if h==100 else 99)), \
             patch('win32gui.IsWindowVisible',return_value=True) as visible, \
             patch('win32gui.GetWindowText',side_effect=AssertionError('Unfiltered title read')), \
             patch('olive.desktop.windows_observation.inspect_window',return_value=window()) as inspect:
            self.assertEqual(len(windows_for_processes({10:10})),1)
            visible.assert_called_once_with(100);inspect.assert_called_once_with(100)


class OwnedBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.services=ServiceContainer(lambda *a:None,AsyncMock(return_value=ConfirmationResponse(False)),
                                       data_dir=self.directory.name,migrate=False)
        self.d=self.services.desktop
    async def asyncTearDown(self):await self.services.shutdown()

    async def test_disabled_attach_and_launch_do_not_enable_control(self):
        with self.assertRaises(PermissionError):await self.d.attach_launch('unknown')
        with self.assertRaises(PermissionError):await self.d.launch_local('script.py','python')
        self.assertFalse(self.d.configuration()['enabled'])

    async def test_target_only_attach_reuses_gateway_without_discovery(self):
        self.d.configure({'enabled':True})
        r=Mock(application=identity('Fixture','executable','script.py'),resolve=Mock(return_value=window()),resolution={})
        self.d.launch_targets.records['owned']=r
        self.d.gateway.observe=AsyncMock(return_value={'window':window(),'controls':[]})
        with patch.object(self.d,'list_windows',side_effect=AssertionError('Broad enumeration')), \
             patch('olive.application.desktop_controller.enumerate_windows',side_effect=AssertionError('Broad enumeration')):
            result=await self.d.attach_launch('owned')
        self.assertEqual(result['session']['window']['pid'],10)
        self.d.gateway.observe.assert_awaited_once()

    async def test_inspection_denial_reaches_real_gateway_and_never_provider(self):
        self.d.configure({'enabled':True})
        self.services.permissions.save({'desktop.inspect_application':'deny'})
        self.d.launch_targets.records['owned']=Mock(application=identity('Fixture','executable','script.py'),resolve=Mock(return_value=window()),resolution={})
        self.d.provider.call=AsyncMock(side_effect=AssertionError('Denied provider called'))
        with self.assertRaises(PermissionError):await self.d.attach_launch('owned')
        self.d.provider.call.assert_not_called()
        self.assertEqual(self.d.record.status,'PAUSED_REVIEW_REQUIRED')

    async def test_stopped_attach_does_not_resolve_or_replay(self):
        self.d.configure({'enabled':True});self.d.stop()
        r=Mock();self.d.launch_targets.records['owned']=r
        with self.assertRaises(asyncio.CancelledError):await self.d.attach_launch('owned')
        r.resolve.assert_not_called()

    async def test_general_discovery_denial_prevents_enumeration(self):
        self.d.configure({'enabled':True})
        self.services.permissions.save({'desktop.inspect_application':'deny'})
        with patch('olive.application.desktop_controller.enumerate_windows',side_effect=AssertionError('Denied read')):
            with self.assertRaises(PermissionError):await self.d.list_windows()

    async def test_unknown_reference_never_attaches(self):
        self.d.configure({'enabled':True})
        with self.assertRaises(ValueError):await self.d.attach_launch('renderer-made-up')
        self.assertIsNone(self.d.record)

    async def test_launch_denial_never_starts_a_process(self):
        self.d.configure({'enabled':True})
        selected=Path(self.directory.name)/'fixture.exe';selected.write_bytes(b'not executable')
        with patch('olive.desktop.launch_targets.subprocess.Popen',side_effect=AssertionError('Denied launch')):
            with self.assertRaises(PermissionError):await self.d.launch_local(str(selected),'executable')
        self.assertEqual(self.d.launch_targets.snapshot(),[])

    async def test_launch_file_change_invalidates_review(self):
        self.d.configure({'enabled':True})
        selected=Path(self.directory.name)/'fixture.exe';selected.write_bytes(b'before review')
        async def changed(*args,**kwargs):selected.write_bytes(b'changed after review')
        self.d.gateway.approval=AsyncMock(side_effect=changed)
        with patch('olive.desktop.launch_targets.subprocess.Popen',side_effect=AssertionError('Stale launch')):
            with self.assertRaisesRegex(PermissionError,'changed after review'):
                await self.d.launch_local(str(selected),'executable')
        self.assertEqual(self.d.launch_targets.snapshot(),[])

    async def test_control_denial_and_focus_loss_never_reach_provider(self):
        from olive.desktop.application_sessions import ApplicationSession
        from olive.desktop.workflow import DesktopStep
        self.d.configure({'enabled':True})
        session=ApplicationSession(identity('Fixture','executable','script.py'),'fixture')
        session.observe({'window':window(),'controls':[{'name':'Check text','runtime_id':[1],
            'enabled':True,'visible':True,'control_type':'Button','actions':['invoke']}]})
        step=DesktopStep(session.identity.id,'invoke',{'runtime_id':[1]},{},{'name':'Verified'},'desktop.control_application')
        self.services.permissions.save({'desktop.control_application':'deny'})
        self.d.provider.call=AsyncMock(side_effect=AssertionError('Unauthorised provider call'))
        with self.assertRaises(PermissionError):await self.d.gateway.authorize(session,step)
        self.services.permissions.save({'desktop.control_application':'ask'})
        self.d.gateway.confirmations.request=AsyncMock(return_value=ConfirmationResponse(True))
        permit=await self.d.gateway.authorize(session,step)
        self.d.gateway.ui_owner=lambda pid:False
        with patch('win32gui.GetForegroundWindow',return_value=999),patch('win32process.GetWindowThreadProcessId',return_value=(1,99)):
            with self.assertRaisesRegex(PermissionError,'focus changed'):
                await self.d.gateway.execute(session,step,permit,self.d.stop_event)
        self.d.provider.call.assert_not_called()
