"""Agent bridge shares natural-language routing; isolated fixtures only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.bridge.agent_routes import launch
from olive.agent.agent_task import AgentTask


class AgentBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-m2-agent-')
        self.host = Host(lambda event: None)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s
        self.chat_id = self.s.current_chat_id

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def test_objective_enters_same_language_orchestrator_without_rewriting_text(self):
        project = self.s.data.create_project('Fixture project')
        folder = Path(self.temp.name) / 'fixture-workspace'
        folder.mkdir()
        workspace = self.s.data.create_workspace('Fixture workspace', str(folder), project['id'])
        self.s.interaction.submit = AsyncMock(return_value={'result':'fixture'})
        result = await self.host.execute('interaction.launch', dict(chat_id=self.chat_id, text='Inspect my selected project.', workspace_id=workspace['id'], project_id=project['id']))
        self.assertEqual(result, {'result':'fixture'})
        self.s.interaction.submit.assert_awaited_once_with('Inspect my selected project.', self.chat_id)
        self.assertEqual(self.s.interaction.context(self.chat_id).project_id, project['id'])
        self.assertEqual(self.s.interaction.selected_workspace, workspace['id'])

    async def test_context_rejects_unknown_or_mismatched_project_and_active_edits(self):
        self.s.interaction.submit = AsyncMock()
        with self.assertRaises(ValueError):
            await launch(self.s, self.chat_id, 'fixture', workspace_id='unknown')
        a = self.s.data.create_project('Fixture A')
        b = self.s.data.create_project('Fixture B')
        folder = Path(self.temp.name) / 'fixture-workspace'
        folder.mkdir()
        workspace = self.s.data.create_workspace('Fixture', str(folder), a['id'])
        with self.assertRaisesRegex(ValueError, 'different project'):
            await launch(self.s, self.chat_id, 'fixture', workspace_id=workspace['id'], project_id=b['id'])
        self.s.interaction.interpreting[self.chat_id] = {'fixture'}
        try:
            with self.assertRaises(ValueError):
                await launch(self.s, self.chat_id, 'fixture')
        finally:
            self.s.interaction.interpreting.clear()
        self.s.interaction.submit.assert_not_awaited()

    async def test_history_is_bounded_and_details_keep_structured_task_evidence(self):
        task = AgentTask('Fixture task', state='failed', completion_summary='One step completed; validation failed.')
        task.files_changed = ['fixture.py']
        task.validation_status = 'failed'
        self.s.agent_task_repo.save(task)
        history = await self.host.execute('agent.history', {})
        self.assertNotIn('tool_calls', history[0])
        detail = await self.host.execute('agent.get', {'task_id': task.id})
        self.assertEqual(detail['state'], 'failed')
        self.assertEqual(detail['files_changed'], ['fixture.py'])
        self.assertEqual(detail['validation_status'], 'failed')
        self.s.agent.history = Mock(return_value=[task.to_dict()] * 101)
        self.assertEqual(len(await self.host.execute('agent.history', {})), 100)

    async def test_studio_selection_enters_same_language_core_as_untrusted_context(self):
        folder = Path(self.temp.name) / 'studio-fixture'
        folder.mkdir()
        (folder / 'main.py').write_text('print("fixture")\n', encoding='utf-8')
        workspace = self.s.data.create_workspace('Fixture Studio', str(folder))
        await self.host.execute('studio.open', {'workspace_id':workspace['id'],'path':'main.py'})
        self.s.interaction.submit = AsyncMock(return_value='Fixture routed')
        await self.host.execute('interaction.studio', {'chat_id':self.chat_id,'text':'Explain this selection','workspace_id':workspace['id'],'project_id':'','path':'main.py','selection':'untrusted fixture selection'})
        self.s.interaction.submit.assert_awaited_once_with('Explain this selection', self.chat_id)
        context = self.s.interaction.context(self.chat_id)
        self.assertEqual(context.snapshot()['untrusted_editor_context']['selection'], 'untrusted fixture selection')
        self.assertEqual(Path(context.entities['path']), folder / 'main.py')
        with self.assertRaises(ValueError):
            await self.host.execute('interaction.studio', {'chat_id':self.chat_id,'text':'Fixture','workspace_id':workspace['id'],'project_id':'','path':'../outside.py','selection':''})
