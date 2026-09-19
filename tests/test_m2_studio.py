"""Studio routes operate only on isolated authorised workspaces."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.services.run_service import RunSession
from olive.tools.git import GitTool

class StudioBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='olive-m2-studio-')
        self.host=Host(lambda event:None)
        self.s=ServiceContainer(self.host.publish,self.host.confirm,data_dir=self.temp.name,migrate=False)
        self.host.services=self.s
        self.root=Path(self.temp.name)/'workspace';self.root.mkdir()
        self.file=self.root/'main.py';self.file.write_text('print("fixture")\n',encoding='utf-8')
        self.workspace=self.s.data.create_workspace('Fixture Studio',str(self.root))
        self.args={'workspace_id':self.workspace['id'],'path':'main.py'}
    async def asyncTearDown(self):
        await self.host.shutdown();self.temp.cleanup()
    async def test_discard_removes_only_open_buffer_not_disk_and_checks_lock(self):
        opened=await self.host.execute('studio.open',self.args)
        await self.host.execute('studio.buffer',dict(self.args,text='unsaved fixture',expected_hash=opened['loaded_hash']))
        lock=self.s.studio.locks[self.workspace['id']]
        async with lock:
            with self.assertRaises(ValueError):await self.host.execute('studio.discard_buffer',self.args)
        await self.host.execute('studio.discard_buffer',self.args)
        self.assertEqual(self.file.read_text(encoding='utf-8'),'print("fixture")\n')
        self.assertFalse(self.host.buffers)
        with self.assertRaises(ValueError):await self.host.execute('studio.discard_buffer',self.args)
    async def test_dirty_history_guard_precedes_any_git_or_rollback_action(self):
        opened=await self.host.execute('studio.open',self.args)
        await self.host.execute('studio.buffer',dict(self.args,text='dirty',expected_hash=opened['loaded_hash']))
        for method,args in [('studio.git',{'action':'checkout','name':'fixture'}),('studio.rollback_latest',{})]:
            with self.assertRaisesRegex(ValueError,'unsaved'):
                await self.host.execute(method,dict(workspace_id=self.workspace['id'],**args))
        self.assertFalse(self.host.pending)
    async def test_git_cannot_escape_approved_root_or_stage_outside_file(self):
        repository=Mock();repository.root.return_value=self.root.parent
        tool=GitTool('add',repository,self.s.workspace_repo)
        with self.assertRaises(PermissionError):tool._execute({'workspace':str(self.root),'files':['main.py']})
        repository.root.return_value=self.root
        with self.assertRaises((ValueError,PermissionError)):tool._execute({'workspace':str(self.root),'files':['../outside.py']})
        repository.add.assert_not_called()
    async def test_search_is_real_bounded_workspace_read(self):
        result=await self.host.execute('studio.search',{'workspace_id':self.workspace['id'],'query':'fixture'})
        self.assertEqual(result['matches'][0][0],'main.py')
        self.assertFalse(self.host.pending)
    async def test_direct_git_read_does_not_override_explicit_denial(self):
        self.s.permissions.save({'filesystem.read': 'deny'})
        with self.assertRaisesRegex(PermissionError, 'Permission denied'):
            await self.host.execute('studio.git', {'workspace_id': self.workspace['id'], 'action': 'status'})
        self.assertFalse(self.host.pending)
    async def test_diagnostics_parse_real_run_records_and_exclude_outside_paths(self):
        run=RunSession(self.workspace['id'],['fixture'],'python_console',state='failed',exit_code=1,
                       stderr=f'{self.file}:3:2: error: fixture failure\n../outside.py:4:1: warning: outside\n',
                       stdout='test_fixture (fixture.Test) ... FAIL\n')
        self.s.run_service.sessions[run.id]=run
        result=await self.host.execute('studio.diagnostics',{'workspace_id':self.workspace['id']})
        self.assertEqual(result[0]['session_id'],run.id)
        self.assertEqual(result[0]['problems'][0]['file'],'main.py')
        self.assertIsNone(result[0]['problems'][1]['file'])
        self.assertEqual(result[0]['tests'][0]['state'],'failed')

    async def test_command_cancellation_retains_output_and_persists_cancelled_task(self):
        task=asyncio.create_task(self.host.execute('studio.command',{'workspace_id':self.workspace['id'],'command':"import time; print('fixture started',flush=True); time.sleep(20)",'shell':'python'}))
        async def wait_for(predicate):
            async with asyncio.timeout(5):
                while not predicate():await asyncio.sleep(.01)
        await wait_for(lambda:bool(self.host.pending))
        approval=next(iter(self.host.pending.values()))[0]
        await self.host.execute('approval.respond',{'approval_id':approval['id'],'fingerprint':approval['fingerprint'],'approved':True})
        await wait_for(lambda:any('fixture started' in record['stdout'] for record in self.host.commands.records.values()))
        identity=next(iter(self.host.commands.records))
        await self.host.execute('studio.cancel_command',{'command_id':identity})
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.host.commands.records[identity]['state'],'cancelled')
        self.assertIn('fixture started',self.host.commands.records[identity]['stdout'])
        latest=next(iter(self.s.agent_task_repo.load_all().values()))
        self.assertEqual(latest.state,'cancelled')
