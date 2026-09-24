"""Isolated bridge contracts and lifecycle tests; no desktop or external messages."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from unittest.mock import patch

from olive.bridge.contracts import decode, validate, MAX_FRAME
from olive.bridge.host import Host
from olive.runtime.profile_lock import ProfileLock


class ContractTests(unittest.TestCase):
    def request(self, method='runtime.snapshot', args=None):
        return dict(v=1, id='request-1', method=method, args=args or {})

    def test_allowlist_and_unknown_fields(self):
        validate(self.request())
        for request in [self.request('agent.tool'), self.request(args={'secret': 'value'}),
                        dict(self.request(), v=True), dict(self.request(), extra=1),
                        self.request('approval.respond', {'approval_id':'a','fingerprint':'b','approved':'yes'})]:
            with self.assertRaises(ValueError):
                validate(request)

    def test_duplicate_keys_and_frame_limits(self):
        with self.assertRaises(ValueError):
            decode(b'{"v":1,"v":1,"id":"a","method":"runtime.snapshot","args":{}}')
        with self.assertRaises(ValueError):
            decode(b' ' * (MAX_FRAME+1))

    def test_profile_writer_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with ProfileLock(directory):
                with self.assertRaises(RuntimeError):
                    ProfileLock(directory).acquire()
            with ProfileLock(directory):
                pass


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_tools_do_not_inherit_private_protocol_stdin(self):
        from olive.services.execution_provider import NativeExecutionProvider, SandboxLimits
        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as start:
            await NativeExecutionProvider().start(['python','main.py'],'.',{},SandboxLimits())
            self.assertEqual(start.call_args.kwargs['stdin'],asyncio.subprocess.DEVNULL)

    async def test_duplicate_request_executes_once_and_changed_arguments_rejected(self):
        host = Host(lambda event: None)
        host.execute = AsyncMock(return_value={'done':True})
        request = dict(v=1,id='same',method='chat.draft',args={'chat_id':'chat','text':'owned'})
        results = await asyncio.gather(host.handle(request),host.handle(request))
        self.assertEqual(results,[{'done':True}]*2)
        host.execute.assert_awaited_once()
        with self.assertRaises(ValueError):
            await host.handle(dict(request,args={'chat_id':'another','text':'owned'}))

    async def test_approval_binds_arguments_and_cannot_be_reused(self):
        from olive.agent.confirmation_service import ConfirmationRequest
        events=[]
        host=Host(events.append)
        pending=asyncio.create_task(host.confirm(ConfirmationRequest('task','studio.save','Save test file','medium',arguments={'path':'test.py','text':'hello'})))
        await asyncio.sleep(0)
        approval=events[0]['data']
        with self.assertRaises(ValueError):
            await host.execute('approval.respond',dict(approval_id=approval['id'],fingerprint='changed',approved=True))
        self.assertFalse(pending.done())
        await host.execute('approval.respond',dict(approval_id=approval['id'],fingerprint=approval['fingerprint'],approved=False))
        self.assertFalse((await pending).approved)
        with self.assertRaises(ValueError):
            await host.execute('approval.respond',dict(approval_id=approval['id'],fingerprint=approval['fingerprint'],approved=True))

    async def test_shutdown_stops_input_and_denies_pending_approval(self):
        from olive.agent.confirmation_service import ConfirmationRequest
        host=Host(lambda event:None)
        stop=Mock()
        host.services=SimpleNamespace(agent=SimpleNamespace(active=None),desktop=SimpleNamespace(stop_event=stop,operation=None,universal=SimpleNamespace(owner=None)),shutdown=AsyncMock(),run_service=SimpleNamespace(sessions={}))
        pending=asyncio.create_task(host.confirm(ConfirmationRequest('task','send','Send','high')))
        await asyncio.sleep(0)
        await host.shutdown()
        self.assertFalse((await pending).approved)
        stop.set.assert_called_once()
        with self.assertRaises(RuntimeError):
            await host.handle(dict(v=1,id='late',method='runtime.snapshot',args={}))


class ComparisonTests(unittest.TestCase):
    def test_compare_preserves_buffer_and_rebase_rejects_changed_disk(self):
        from olive.application.studio_tools import StudioAccessTool
        from olive.services.studio_service import StudioService
        from olive.services.checkpoint_service import CheckpointService
        from olive.workspace import Workspace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            file=root/'main.py';file.write_text('original',encoding='utf-8')
            service=StudioService(Workspace('fixture',str(root)),CheckpointService(root/'checkpoints'))
            state=service.open_file('main.py');service.update('main.py','unsaved edit')
            controller=SimpleNamespace(service=lambda _:service)
            compare=StudioAccessTool(controller,'compare')
            rebase=StudioAccessTool(controller,'rebase')
            file.write_text('disk change',encoding='utf-8')
            result=compare.perform({'workspace':str(root),'path':'main.py'},SimpleNamespace(task_id='fixture'))
            self.assertEqual(state.text,'unsaved edit')
            self.assertEqual(result.data['disk_text'],'disk change')
            arguments={'workspace':str(root),'path':'main.py','disk_hash':result.data['disk_hash'],'expected_hash':state.loaded_hash}
            file.write_text('newer disk change',encoding='utf-8')
            with self.assertRaises(RuntimeError):
                rebase.perform(arguments,SimpleNamespace(task_id='fixture'))
            self.assertEqual(state.text,'unsaved edit')
            self.assertTrue(rebase.definition.confirmation_required)


if __name__ == '__main__':
    unittest.main()
