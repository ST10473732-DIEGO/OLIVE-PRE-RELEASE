"""Explicit Research uses the shared orchestrator and existing policy boundary."""
import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host


class ResearchBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-m2-research-')
        self.host = Host(lambda event: None)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s
        self.chat_id = self.s.current_chat_id

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def test_explicit_form_uses_shared_router_and_context(self):
        project = self.s.data.create_project('Fixture research project')
        self.s.interaction.router.execute = AsyncMock(return_value='Fixture routed result')
        question = 'How does this fixture work?'
        await self.host.execute('interaction.research', dict(chat_id=self.chat_id, question=question, depth='Quick', project_id=project['id']))
        step, context = self.s.interaction.router.execute.await_args.args
        self.assertEqual(step['intent'], 'research.start')
        self.assertEqual(step['entities']['query'], question)
        self.assertEqual(context.project_id, project['id'])
        self.assertEqual(context.research_depth, 'Quick')
        self.assertNotIn(self.chat_id, self.s.interaction.active)
        self.assertEqual(self.s.chats[self.chat_id].messages[-1].content, 'Fixture routed result')

    async def test_form_rejects_invalid_context_without_starting(self):
        self.s.interaction.router.execute = AsyncMock()
        for values in ({'depth': 'unbounded'}, {'project_id': 'unknown'}, {'question': ''}):
            arguments = dict(chat_id=self.chat_id, question='Fixture question')
            arguments.update(values)
            with self.assertRaises(ValueError):
                await self.s.interaction.research_question(**arguments)
        self.s.interaction.active[self.chat_id] = asyncio.current_task()
        try:
            with self.assertRaises(ValueError):
                await self.s.interaction.research_question('Fixture question', self.chat_id)
        finally:
            self.s.interaction.active.clear()
        self.s.interaction.router.execute.assert_not_awaited()

    async def test_cancel_reaches_research_preparation_and_persists_state(self):
        entered = asyncio.Event()
        async def wait_for_configuration():
            entered.set()
            await asyncio.Event().wait()
        self.s.research.configure = wait_for_configuration
        work = asyncio.create_task(self.host.execute('interaction.research', dict(chat_id=self.chat_id, question='Fixture cancellation question', depth='Quick')))
        await asyncio.wait_for(entered.wait(), 5)
        current = await self.host.execute('research.current', {})
        self.assertTrue(current['active'])
        identifier = current['session']['id']
        await self.host.execute('research.cancel', {})
        await asyncio.wait_for(work, 5)
        saved = await self.host.execute('research.get', {'session_id': identifier})
        self.assertEqual(saved['status'], 'cancelled')
        self.assertEqual(saved['sources'], [])
        self.assertFalse((await self.host.execute('research.current', {}))['active'])

    async def test_source_learning_retains_registered_tool_boundary(self):
        self.s.agent.tool = AsyncMock(side_effect=PermissionError('Fixture denial'))
        with self.assertRaises(PermissionError):
            await self.host.execute('research.save_sources', {'session_id': 'fixture-session', 'source_ids': ['fixture-source']})
        self.s.agent.tool.assert_awaited_once_with('web.learn', {'session_id': 'fixture-session', 'source_ids': ['fixture-source'], 'collection': 'OLIVE Research'})

    async def test_source_approval_summary_uses_selected_repository_source(self):
        from olive.research.models import ResearchSession, ResearchSource
        from olive.bridge.presentation import approval_presentation
        session = ResearchSession('Fixture')
        selected = ResearchSource('https://example.invalid/selected', 'Selected fixture')
        session.sources = [selected, ResearchSource('https://example.invalid/unselected', 'Unselected')]
        self.s.research.repository.save(session)
        value = {'tool_name': 'web.learn', 'summary': 'web.learn', 'arguments': {'session_id': session.id, 'source_ids': [selected.id]}}
        result = approval_presentation(value, self.s)
        self.assertEqual(result['targets'], [selected.url])
        self.assertEqual(result['action'], 'Save reviewed research sources to Knowledge')
        self.assertNotIn('unselected', result['content'])
        self.assertEqual(value['arguments']['source_ids'], [selected.id])
