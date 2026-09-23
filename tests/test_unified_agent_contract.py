import asyncio
import json
import threading
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from olive.desktop.task_authority import TaskAuthority, interpreted_scope
from olive.desktop.gui_owl import parse_action, compositor_point
from olive.services.model_residency_service import ModelResidencyService


class UnifiedAuthorityTests(unittest.TestCase):
    def test_freeform_interpretation_cannot_invent_text_or_app(self):
        request = 'Could you bring up Firefox and look up glacier monitoring please?'
        steps = [{'intent': 'application.search', 'entities': {'application': 'Firefox', 'query': 'glacier monitoring'}, 'references': {}}]
        scope = interpreted_scope(request, steps)
        self.assertEqual((scope.application, scope.effect, scope.content), ('Firefox', 'search', 'glacier monitoring'))
        for field, value in [('query', 'invented facts'), ('application', 'Konsole'), ('approved', True)]:
            bad = json.loads(json.dumps(steps))
            bad[0]['entities'][field] = value
            with self.assertRaises(ValueError):
                interpreted_scope(request, bad)

    def test_cancelled_grant_never_revives_after_new_explicit_request(self):
        stop = threading.Event()
        authority = TaskAuthority(stop)
        policy = dict(enabled=True, trusted_tasks=True, keyboard_policy='allow', mouse_policy='allow')
        old = authority.issue('Open Kate', 'old', policy, local_user=True)
        stop.set()
        authority.cancel()
        stop.clear()
        new = authority.issue('Open Kate', 'new', policy, local_user=True)
        with self.assertRaises(InterruptedError):
            authority.check(old, policy)
        authority.check(new, policy)
        policy['enabled'] = False
        with self.assertRaises(PermissionError):
            authority.check(new, policy)

    def test_freeform_named_click_keeps_literal_target_and_rejects_typing(self):
        request = 'Could you press New sample in the Fixture app for me?'
        steps = [{'intent':'application.control', 'entities':{'application':'Fixture', 'target':'New sample', 'action':'click'}, 'references':{}}]
        self.assertEqual(interpreted_scope(request, steps).effect, 'click')
        steps[0]['entities']['action'] = 'set_text'
        with self.assertRaises(ValueError):
            interpreted_scope(request, steps)


class GuiProtocolTests(unittest.TestCase):
    def action(self, value):
        return '<tool_call>' + json.dumps({'name': 'computer_use', 'arguments': value}) + '</tool_call>'

    def test_upstream_action_is_mapped_without_executing_code(self):
        raw = self.action({'action': 'left_click', 'coordinate': [250, 750]})
        self.assertEqual(parse_action(raw)['coordinate'], [250, 750])
        self.assertEqual(compositor_point([250, 750], (400, 200), (100, 50, 800, 400), (1600, 900), (-1920, 0, 1920, 1080)), (-1560, 420))

    def test_unknown_malformed_multi_action_and_authority_fields_fail_closed(self):
        values = [{'action': 'exec', 'code': 'print(1)'},
                  {'action': 'left_click', 'coordinate': [-1, 200]},
                  {'action': 'left_click', 'coordinate': [True, 200]},
                  {'action': 'left_click', 'coordinate': [1000, 200]},
                  {'action': 'key', 'keys': ['CTRL', 'ALT', 'F2']},
                  {'action': 'type', 'text': 'hello', 'approved': True},
                  {'action': 'scroll', 'pixels': float('nan')}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_action(self.action(value))
        for raw in ('import os', self.action({'action': 'wait', 'time': 1})*2,
                    '<tool_call>{"name":"computer_use","arguments":{"action":"wait","action":"terminate","time":1}}</tool_call>'):
            with self.assertRaises(ValueError):
                parse_action(raw)


@unittest.skipUnless(hasattr(os, 'getuid'), 'Linux owned-file policy')
class FileTransferTests(unittest.TestCase):
    def test_collision_and_symlink_refused_before_any_ui_effect(self):
        from olive.desktop.linux.file_task import owned_file
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'note.txt'
            source.write_text('owned fixture')
            destination = root / 'copies'
            destination.mkdir()
            _, _, target = owned_file(str(source), str(destination))
            target.write_text('unrelated existing file')
            with self.assertRaises(FileExistsError):
                owned_file(str(source), str(destination))
            self.assertEqual(target.read_text(), 'unrelated existing file')
            alias = root / 'alias.txt'
            alias.symlink_to(source)
            with self.assertRaises(PermissionError):
                owned_file(str(alias), str(destination))


class SharedResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ollama_gui_and_remote_consumers_share_one_lease(self):
        ollama = type('Ollama', (), {'unload_model': AsyncMock()})()
        manager = ModelResidencyService(ollama)
        start, close = AsyncMock(), AsyncMock()
        manager.register_provider('gui', start, close)
        async with manager.lease('chat'):
            pass
        async with manager.lease('gui'):
            ollama.unload_model.assert_awaited_once_with('chat')
            queued = asyncio.create_task(self.acquire(manager))
            await asyncio.sleep(0)
            self.assertFalse(queued.done())
        await queued
        close.assert_awaited_once_with()

    async def acquire(self, manager):
        async with manager.lease('remote-chat'):
            self.assertEqual(manager.active, 'remote-chat')


class UnifiedChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from olive.application.service_container import ServiceContainer
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.services = ServiceContainer(lambda *_: None, AsyncMock(), self.directory.name, migrate=False)
        self.s = self.services
        self.s.desktop.configure(dict(enabled=True, trusted_tasks=True, screen_observation=True,
            keyboard_policy='allow', mouse_policy='allow'))
        if not self.s.desktop.linux:
            self.skipTest('Linux Chat route')
        self.s.desktop.linux.run = AsyncMock(return_value='Verified fixture')
        self.s.interaction.interpreter.interpret = AsyncMock(return_value={
            'confidence':1, 'clarification':'', 'steps':[{'intent':'application.search',
                'entities':{'application':'Firefox','query':'glacier monitoring'},'references':{}}]})

    async def asyncTearDown(self):
        await self.s.shutdown()

    async def test_normal_chat_paraphrase_preserves_user_provenance(self):
        request = 'Could you bring up Firefox and look up glacier monitoring please?'
        await self.s.interaction.submit(request)
        args = self.s.desktop.linux.run.call_args
        self.assertEqual(args.args[0], request)
        chat = self.s.chats[self.s.current_chat_id]
        user = [m for m in chat.messages if m.role == 'user']
        self.assertEqual(len(user), 1)
        self.assertEqual(args.args[1], user[0].id)
        self.assertEqual(user[0].content, request)
        self.assertIsNotNone(args.kwargs['interpretation'])

    async def test_connect_target_cannot_enter_local_desktop_route(self):
        self.s.chat.targets[self.s.current_chat_id] = 'fixture-peer'
        await self.s.interaction.submit('Open Firefox and search for glacier monitoring')
        self.s.desktop.linux.run.assert_not_awaited()

    async def test_ordinary_answer_does_not_start_input(self):
        self.s.interaction.interpreter.interpret.return_value['steps'] = [
            {'intent':'conversation.answer','entities':{},'references':{}}]
        self.s.chat.send = AsyncMock(return_value={})
        await self.s.interaction.submit('What is a glacier?')
        self.s.desktop.linux.run.assert_not_awaited()


class ConsequentialClickTests(unittest.TestCase):
    def test_generic_click_cannot_confirm_payment_or_overwrite(self):
        from olive.desktop.task_authority import TaskScope, validate_effect
        from types import SimpleNamespace
        for label, title in [('Continue', 'Checkout'), ('OK', 'Save File'), ('Allow', 'Settings')]:
            grant = SimpleNamespace(scope=TaskScope('Fixture', 'click', label))
            target = dict(id='button', name=label, role='button', enabled=True)
            observation = dict(revision='current', controls=[target, dict(id='frame', role='frame', name=title)])
            proposal = dict(action='click', target='button', value='', revision='current', expected='')
            with self.assertRaises(PermissionError):
                validate_effect(grant, proposal, observation)
