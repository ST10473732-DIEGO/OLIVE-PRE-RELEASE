"""Desktop navigation from ordinary Chat: follow-ups, task card, Stop, restart (simulated desktop)."""
import asyncio
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.bridge.agent_routes import chat_tasks, stop_task
from tests.desktop_navigation_fixture import FakeApps, FakeDesktop


@unittest.skipUnless(sys.platform == 'linux', 'Linux desktop runtime')
class ChatNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.s = ServiceContainer(lambda *_: None, AsyncMock(side_effect=AssertionError('no approval expected')),
                                  self.directory.name, migrate=False)
        self.s.desktop.configure(dict(enabled=True, trusted_tasks=True, screen_observation=True, uia=True,
                                      keyboard_policy='allow', mouse_policy='allow'))
        self.runtime = self.s.desktop.linux
        self.runtime.prepare = AsyncMock()
        self.fake = FakeDesktop()
        self.runtime.native.call = self.fake.call
        self.runtime.apps = FakeApps(self.fake)
        self.runtime.default_browser = 'Firefox'
        self.chat_id = self.s.current_chat_id
        self.events = []
        publish = self.s.publish
        self.s.publish = lambda topic, value=None: (self.events.append((topic, value)), publish(topic, value))[1]
        self.s.ollama.chat_once = AsyncMock(side_effect=AssertionError('no model call expected'))

    async def asyncTearDown(self):
        await self.s.shutdown()

    async def say(self, text):
        await self.s.interaction.submit(text, self.chat_id)
        return self.s.chats[self.chat_id].messages[-1].content

    async def test_chat_follow_ups_task_card_and_status(self):
        self.fake.browser(('GitHub', 'https://github.com/'))
        answer = await self.say('Open Firefox and go to https://example.com')
        self.assertIn('✓ Navigated to example.com', answer)
        answer = await self.say('Go back')
        self.assertIn('Went back', answer)
        cards = chat_tasks(self.s, self.chat_id)
        desktop = [c for c in cards if c['kind'] == 'desktop']
        self.assertEqual(len(desktop), 2)
        self.assertTrue(all(c['state'] == 'completed' and not c['active'] for c in desktop))
        self.assertIn('Navigated to example.com', [e['text'] for e in desktop[0]['timeline']])
        self.assertNotIn('receipts', desktop[0])
        activity = [v['message'] for t, v in self.events if t == 'interaction_activity' and v.get('chat_id') == self.chat_id]
        self.assertIn('Entering the address…', activity)
        self.assertIn('Going back…', activity)

    async def test_window_question_is_answered_in_chat(self):
        first = self.fake.browser(('GitHub', 'https://github.com/'))
        second = self.fake.browser(('YouTube', 'https://www.youtube.com/'))
        answer = await self.say('Open Firefox')
        self.assertIn('I found 2 Firefox windows', answer)
        answer = await self.say('the YouTube one')
        self.assertIn('✓ Firefox focused (the window you chose)', answer)
        self.assertEqual([a['window_id'] for m, a in self.fake.calls if m == 'activate'], [second.id])
        self.assertNotEqual(first.id, second.id)

    async def test_stop_from_the_task_card_stops_before_the_next_input(self):
        self.fake.browser(('GitHub', 'https://github.com/'))
        stopped = {}

        def stop(fake, method, args, phase):
            if method == 'browser_step' and args.get('step') == 'new_tab' and phase == 'after':
                card = self.runtime.task_record.task
                stopped['result'] = stop_task(self.s, card.id)
        self.fake.hooks.append(stop)
        answer = await self.say('Open a new tab and go to https://example.com')
        await asyncio.sleep(.05)
        self.assertEqual(stopped['result'], {'stopped': True})
        self.assertIn('Stopped', answer)
        self.assertEqual([a['step'] for m, a in self.fake.calls if m == 'browser_step'], ['new_tab'])
        card = [c for c in chat_tasks(self.s, self.chat_id) if c['kind'] == 'desktop'][-1]
        self.assertEqual(card['state'], 'cancelled')

    async def test_continue_after_restart_never_replays_desktop_input(self):
        from olive.agent.agent_task import AgentTask
        task = AgentTask('Open Firefox and go to github.com', kind='desktop', chat_id=self.chat_id, message_id='m')
        task.transition('running')
        self.s.agent_task_repo.save(task)
        self.s.agent_task_repo.recover_interrupted()
        self.s.interaction.interpreter.interpret = AsyncMock(return_value={
            'confidence': 1, 'clarification': '', 'steps': [{'intent': 'task.resume', 'entities': {}, 'references': {}}]})
        answer = await self.say('Continue')
        self.assertIn("won't repeat any clicks or typing automatically", answer)
        self.assertEqual(self.fake.inputs(), [])
        self.assertEqual(self.s.agent_task_repo.load_all()[task.id].state, 'cancelled')

    async def test_ordinary_chat_is_not_captured_by_desktop_grammar(self):
        self.s.chat.send = AsyncMock(return_value=None)
        self.s.interaction.interpreter.interpret = AsyncMock(return_value={
            'confidence': 1, 'clarification': '', 'steps': [{'intent': 'chat.answer', 'entities': {}, 'references': {}}]})
        await self.s.interaction.submit('Go back to what we discussed about taxes', self.chat_id)
        self.assertEqual(self.fake.calls, [])
