"""Safe pause boundaries and outcome classification; controlled integration."""
import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.application.agent_controller import ObservedExecutor
from olive.agent.agent_task import AgentTask
from olive.agent.tool_schema import ToolContext
from olive.agent.tool_result import ToolResult
from olive.bridge.host import Host


class CloseoutTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-m2-closeout-')
        self.host = Host(lambda event: None)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def test_pause_waits_for_operation_then_resume_and_cancel_at_boundary(self):
        agent = self.s.agent
        task = AgentTask('Controlled boundary regression', state='running')
        entered, finish = asyncio.Event(), asyncio.Event()
        async def execute(*args):
            entered.set()
            await finish.wait()
            return ToolResult(success=True, summary='Controlled operation completed')
        executor = SimpleNamespace(registry=None, execute=AsyncMock(side_effect=execute))
        observed = ObservedExecutor(agent, executor)
        context = ToolContext(task.id, agent.cancel_event)
        first = asyncio.create_task(observed.execute(task, None, context))
        agent.active = first
        await entered.wait()
        agent.pause()
        self.assertEqual(agent.pause_state, 'pausing')
        self.assertEqual(task.state, 'running')
        self.assertEqual(self.host.activity_snapshot()['state'], 'Working')
        finish.set()
        await first
        second = asyncio.create_task(observed.execute(task, None, context))
        agent.active = second
        await asyncio.sleep(0)
        self.assertEqual(agent.pause_state, 'paused')
        self.assertEqual(task.state, 'paused')
        self.assertEqual(executor.execute.await_count, 1)
        self.assertEqual(self.host.activity_snapshot()['state'], 'Paused')
        self.host.activities['unrelated-chat'] = {'method': 'chat.regenerate'}
        self.assertEqual(self.host.activity_snapshot()['state'], 'Thinking')
        self.host.activities.clear()
        self.s.desktop.operation = asyncio.create_task(asyncio.sleep(60))
        self.assertEqual(self.host.activity_snapshot()['state'], 'Working')
        self.s.desktop.operation.cancel()
        await asyncio.gather(self.s.desktop.operation, return_exceptions=True)
        self.s.desktop.operation = None
        await agent.resume()
        await second
        self.assertEqual(task.state, 'running')
        self.assertEqual(executor.execute.await_count, 2)
        agent.pause()
        third = asyncio.create_task(observed.execute(task, None, context))
        agent.active = third
        await asyncio.sleep(0)
        agent.cancel()
        result = await third
        self.assertEqual(result.error_type, 'Cancelled')
        self.assertEqual(task.state, 'cancelled')
        self.assertEqual(executor.execute.await_count, 2)
        agent.active = None

    async def test_partial_upgrade_reports_retained_batches(self):
        self.s.rag.reembed_missing = AsyncMock(return_value=(24, 48))
        result = await self.host.execute('knowledge.upgrade', {})
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['completed'], 24)
        self.assertIn('retained', result['summary'])
        self.assertIn('lexical search remains available', result['summary'])

    async def test_diagnostics_include_validation_results_without_run_session_copy(self):
        workspace = self.s.data.create_workspace('Temporary validation', self.temp.name)
        self.s.studio.validations['validation'] = {'workspace_id': workspace['id'], 'results': [
            {'name': 'Tests', 'session_id': 'actual-command-id', 'state': 'completed', 'exit_code': 0,
             'stderr': 'test_add (test_main.LocalAcceptance.test_add) ... ok\nRan 1 test in 0.001s\nOK\n'}]}
        result = await self.host.execute('studio.diagnostics', {'workspace_id': workspace['id']})
        self.assertEqual(result[0]['session_id'], 'actual-command-id')
        self.assertTrue(result[0]['tests'])
        self.assertFalse(self.s.run_service.sessions)

    async def test_agent_validation_summary_uses_actual_outcome(self):
        self.s.agent_executor.execute = AsyncMock(return_value=ToolResult(True, 'Checks passed'))
        result = await self.s.agent.tool('workspace.run_validation', {}, return_outcome=True)
        self.assertEqual(self.s.agent_task_repo.load_all()[result['task_id']].validation_status, 'passed')
        self.s.agent_executor.execute.return_value = ToolResult.failure('Not approved', 'ConfirmationDenied')
        result = await self.s.agent.tool('workspace.run_validation', {}, retain_failure=True, return_outcome=True)
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(self.s.agent_task_repo.load_all()[result['task_id']].validation_status, 'not_run')
