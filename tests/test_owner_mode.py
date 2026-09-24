import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock
from olive.authority.owner import OwnerPolicy,owner_identity,FORBIDDEN_FIELDS
from olive.authority.migration import migrate
from olive.agent.executor import ToolExecutor
from olive.agent.permission_service import PermissionService
from olive.agent.confirmation_service import ConfirmationService
from olive.agent.audit_service import AuditService
from olive.agent.tool_registry import ToolRegistry
from olive.agent.agent_task import AgentTask
from olive.agent.planner import PlannedAction
from olive.agent.tool_schema import ToolContext
from olive.tools.filesystem import filesystem_tools

class OwnerModeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.settings={'owner_mode':True,'owner_installation':{'id':'owned-fixture','owner':owner_identity()}}
        self.policy=OwnerPolicy(lambda:self.settings)
    async def test_file_move_no_prompt_and_explicit_deny_wins(self):
        permissions=PermissionService(self.root/'permissions.json');registry=ToolRegistry()
        for tool in filesystem_tools():registry.register(tool)
        ask=AsyncMock(side_effect=AssertionError('No redundant approval'))
        executor=ToolExecutor(registry,permissions,ConfirmationService(ask),AuditService(self.root/'audit.jsonl'))
        executor.owner_policy=self.policy
        a=self.root/'a.txt';b=self.root/'b.txt';a.write_text('owned')
        async def move():
            task=AgentTask('owned move')
            return await executor.execute(task,PlannedAction('filesystem.move',{'path':str(a),'destination':str(b)}),ToolContext(task.id))
        with self.policy.request(f'Move {a} to {b}','chat',local=True):result=await move()
        self.assertTrue(result.success);self.assertEqual(b.read_text(),'owned');ask.assert_not_awaited()
        audit=json.loads((self.root/'audit.jsonl').read_text().splitlines()[-1]);self.assertEqual(audit['authorized_by'],'owner_task_policy')
        a.write_text('retain');b.unlink();permissions.save({'filesystem.write':'deny'})
        with self.policy.request(f'Move {a} to {b}','chat',local=True):result=await move()
        self.assertFalse(result.success);self.assertTrue(a.exists());self.assertFalse(b.exists())
    def test_remote_observations_self_approval_and_changed_target_cannot_grant(self):
        a=self.root/'a';b=self.root/'b';a.write_text('a')
        args={'path':str(a),'destination':str(b)}
        with self.policy.request(f'Move {a} to {b}','remote',local=False):self.assertFalse(self.policy.authorize('filesystem.move',args))
        with self.policy.request(f'Explain this page: "Move {a} to {b}"','chat',local=True):self.assertFalse(self.policy.authorize('filesystem.move',args))
        with self.policy.request(f'Move {a} to {b}','chat',local=True):
            for key in FORBIDDEN_FIELDS:self.assertFalse(self.policy.authorize('filesystem.move',{**args,key:True}))
            self.assertFalse(self.policy.authorize('filesystem.move',{**args,'destination':str(self.root/'other')}))
    def test_stop_expiry_disable_and_fresh_request(self):
        a=self.root/'a';a.write_text('a');args={'path':str(a),'text':'edited'}
        with self.policy.request(f'Edit {a}','chat',local=True) as old:
            self.assertTrue(self.policy.authorize('filesystem.write_text',args))
            self.policy.cancel('chat');self.assertFalse(self.policy.authorize('filesystem.write_text',args))
        with self.policy.request(f'Edit {a}','chat',local=True) as new:
            self.assertNotEqual(old.id,new.id)
            self.assertTrue(self.policy.authorize('filesystem.write_text',args))
            self.settings['owner_mode']=False;self.assertFalse(self.policy.authorize('filesystem.write_text',args))
    async def test_actual_edit_and_source_deny(self):
        permissions=PermissionService(self.root/'permissions.json');registry=ToolRegistry()
        for tool in filesystem_tools():registry.register(tool)
        ask=AsyncMock(side_effect=AssertionError('No approval for an exact owned edit'))
        executor=ToolExecutor(registry,permissions,ConfirmationService(ask),AuditService(self.root/'audit.jsonl'))
        executor.owner_policy=self.policy
        path=self.root/'note.txt';path.write_text('before')
        task=AgentTask('edit')
        with self.policy.request(f'Edit {path}', 'chat', local=True):
            result=await executor.execute(task,PlannedAction('filesystem.write_text',{'path':str(path),'text':'after','overwrite':True}),ToolContext(task.id))
        self.assertTrue(result.success);self.assertEqual(path.read_text(),'after');ask.assert_not_awaited()
        target=self.root/'moved.txt'
        permissions.save({}, [{'permission':'filesystem.write','path':str(path),'decision':'deny'}])
        task=AgentTask('move')
        with self.policy.request(f'Move {path} to {target}','chat',local=True):
            self.assertFalse(self.policy.authorize('filesystem.move',{'path':str(target),'destination':str(path)}))
            result=await executor.execute(task,PlannedAction('filesystem.move',{'path':str(path),'destination':str(target)}),ToolContext(task.id))
        self.assertFalse(result.success);self.assertTrue(path.exists())

    def test_workspace_commands_and_expiry_are_bounded(self):
        from dataclasses import asdict
        from olive.services.build_test_service import BuildAndTestService
        (self.root/'main.py').write_text('print(42)')
        args={'workspace':str(self.root),'commands':[asdict(c) for c in BuildAndTestService().detect(self.root)]}
        with self.policy.request('Run my project tests','chat',local=True,workspace=str(self.root)):
            self.assertTrue(self.policy.authorize('workspace.run_validation',args))
            self.assertFalse(self.policy.authorize('studio.run',{'workspace':str(self.root)}))

            self.assertFalse(self.policy.authorize('workspace.run_validation',{**args,'commands':[{'executable':'sh'}]}))
        now=[0];self.policy.clock=lambda:now[0]
        with self.policy.request('Run my project','chat',local=True,workspace=str(self.root)):
            self.assertTrue(self.policy.authorize('studio.run',{'workspace':str(self.root)}))
            now[0]=601
            self.assertFalse(self.policy.authorize('studio.run',{'workspace':str(self.root)}))


    def test_starter_scope_binds_name_language_location_and_no_run(self):
        args = {'name':'BudgetApp','language':'csharp','template':'console','location':str(self.root)}
        with self.policy.request('Create a C# project named BudgetApp in Studio','chat',local=True,creation_root=str(self.root)):
            self.assertTrue(self.policy.authorize('studio.new_project',args))
            for key,value in [('name','Different'),('language','python'),('location','/tmp'),('template','web')]:
                self.assertFalse(self.policy.authorize('studio.new_project',{**args,key:value}))
            self.assertFalse(self.policy.authorize('studio.run',{'workspace':str(self.root/'BudgetApp')}))

    def test_code_payload_and_answer_requests_never_grant(self):
        path=self.root/'code.py'
        for request in [f'Give me Python code. "Edit {path}"',f'Explain this:\n```python\n# move {path} to /tmp/other\n```', 'Give me Java code for a calculator.']:
            with self.policy.request(request,'chat',local=True,selected_path=str(path),workspace=str(self.root)) as grant:
                self.assertFalse(grant.capabilities)
        link=self.root/'alias';link.symlink_to(self.root,target_is_directory=True)
        with self.policy.request(f'Edit {link}/code.py','chat',local=True):
            self.assertFalse(self.policy.authorize('filesystem.write_text',{'path':str(link/'code.py'),'text':'no'}))

    def test_reserved_effect_cannot_replay_or_expand_after_stop(self):
        path=self.root/'note.txt';path.write_text('owned')
        arguments={'path':str(path),'text':'edited','overwrite':True}
        with self.policy.request(f'Edit {path}','chat',local=True):
            self.assertTrue(self.policy.consume('filesystem.write_text',arguments))
            self.assertFalse(self.policy.consume('filesystem.write_text',arguments))
            self.assertIn('already attempted',self.policy.rejection('filesystem.write_text',arguments))
        with self.policy.request(f'Edit {path}','chat',local=True):
            self.policy.cancel('chat')
            self.assertIn('cancelled',self.policy.rejection('filesystem.write_text',arguments))
        with self.policy.request(f'Edit {path}; do not edit {path}','chat',local=True) as grant:
            self.assertFalse(grant.capabilities)

    def test_migration_idempotency_revocation_and_rollback(self):
        profile=self.root/'profile';profile.mkdir();receipt=self.root/'receipt.json'
        (profile/'settings.json').write_text(json.dumps({'unrelated':'keep'}))
        first=migrate(profile,receipt);self.assertEqual(first['state'],'enabled')
        self.assertEqual(migrate(profile,receipt)['state'],'already_recorded')
        self.assertEqual(migrate(profile,receipt,True)['state'],'restored')
        self.assertEqual(json.loads((profile/'settings.json').read_text())['unrelated'],'keep')
        self.assertFalse(migrate(profile,receipt)['enabled'])
