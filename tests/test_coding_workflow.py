import sys
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


class CodingWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.decision = True
        async def review(request):
            return ConfirmationResponse(self.decision)
        self.s = ServiceContainer(lambda *args: None, review, self.root, migrate=False)
        self.context = self.s.interaction.context(self.s.current_chat_id)

    async def asyncTearDown(self):
        await self.s.shutdown()
        self.temp.cleanup()

    async def test_denied_creation_does_not_create_workspace_or_source(self):
        self.decision = False
        with self.assertRaises(PermissionError):
            await self.s.coding.create("Denied", "python", "Create a timer", self.context)
        self.assertFalse((self.root / "Denied").exists())
        self.assertFalse(self.s.workspace_repo.load_all())

    async def test_cancelled_review_cannot_create_project(self):
        pending = asyncio.Event()
        async def review(request):
            pending.set()
            await asyncio.Event().wait()
        self.s.confirmations.handler = review
        task = asyncio.create_task(self.s.coding.create("Cancelled", "python", "Create a timer", self.context))
        await pending.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertFalse((self.root / "Cancelled").exists())
        self.assertFalse(self.s.workspace_repo.load_all())

    async def test_folder_scoped_deny_applies_to_creation(self):
        self.s.permissions.save({}, scopes=[{'permission': 'filesystem.write', 'path': str(self.root / 'Denied'), 'decision': 'deny'}])
        with self.assertRaises(PermissionError):
            await self.s.coding.create('Denied', 'python', 'Create a timer', self.context)
        self.assertFalse((self.root / 'Denied').exists())

    async def test_owner_starter_creation_has_no_approval_generation_or_run(self):
        from olive.authority.owner import owner_identity
        self.s.settings['owner_mode'] = True
        self.s.settings['owner_installation'] = {'id':'fixture','owner':owner_identity()}
        self.s.confirmations.handler = AsyncMock(side_effect=AssertionError('redundant approval'))
        self.s.coding.modify = AsyncMock(side_effect=AssertionError('unrequested source generation'))
        request = 'Create a Python project named Starter in Studio'
        with self.s.owner_policy.request(request, self.context.chat_id, local=True, creation_root=str(self.root)):
            result = await self.s.coding.create('Starter','python',request,self.context)
        self.assertIn('console starter',result)
        self.assertTrue((self.root/'Starter'/'main.py').is_file())
        self.s.confirmations.handler.assert_not_awaited()

    async def test_pending_ai_save_preserves_new_editor_typing(self):
        folder = self.root / "project"
        folder.mkdir()
        source = folder / "main.py"
        source.write_text("print('old')\n")
        workspace = self.s.data.create_workspace("Fixture", str(folder))
        opened = await self.s.studio.access(workspace['id'], 'open', path='main.py')
        async def review(request):
            self.s.studio.service(workspace['id']).update('main.py', "print('typed while waiting')\n")
            return ConfirmationResponse(True)
        self.s.confirmations.handler = review
        with self.assertRaises(PermissionError):
            await self.s.studio.access(workspace['id'], 'save', path='main.py', text="print('AI')\n",
                                      expected_hash=opened['loaded_hash'], expected_text=opened['text'])
        self.assertEqual(source.read_text(), "print('old')\n")
        self.assertIn('typed while waiting', self.s.studio.service(workspace['id']).open_files['main.py'].text)

    async def test_dirty_editor_is_rejected_before_generation(self):
        workspace = self.s.data.create_coding_project("Dirty", "python")
        state = await self.s.studio.access(workspace['id'], 'open', path='main.py')
        self.s.studio.service(workspace['id']).update('main.py', state['text'] + '# unsaved\n')
        self.s.ollama.chat_measured = AsyncMock()
        with self.assertRaisesRegex(ValueError, 'unsaved'):
            await self.s.coding.modify(workspace['id'], 'Add a feature')
        self.s.ollama.chat_measured.assert_not_awaited()

    async def test_model_cannot_escape_workspace_or_overwrite_unread_file(self):
        workspace = self.s.data.create_coding_project("Bounded", "python")
        self.s.model_router.route = lambda request: SimpleNamespace(name='fixture')
        for path in ('../outside.py', 'requirements.txt'):
            self.s.ollama.chat_measured = AsyncMock(return_value={'content': json.dumps({'files': [{'path': path, 'content': 'bad'}]})})
            with self.subTest(path=path), self.assertRaises((ValueError, PermissionError)):
                await self.s.coding.modify(workspace['id'], 'Add a feature')
        self.assertFalse((Path(workspace['root_path']).parent/'outside.py').exists())

    @unittest.skipUnless(sys.platform in {"win32", "linux"}, "Native PTY platform required")
    async def test_running_program_input_has_session_identity_and_deny_boundary(self):
        workspace = self.s.data.create_coding_project("Input", "python")
        (Path(workspace['root_path'])/'main.py').write_text("print(input(), flush=True)\n")
        run = await self.s.studio.run(workspace['id'])
        with self.assertRaises(ValueError):
            await self.s.run_service.input('another-workspace', run['session_id'], 'wrong\n')
        self.s.permissions.save({'terminal.execute': 'deny'})
        with self.assertRaises(PermissionError):
            await self.s.studio.input(workspace['id'], run['session_id'], 'denied\n')
        self.s.permissions.save({})
        await self.s.studio.input(workspace['id'], run['session_id'], 'hello\n')
        final = await asyncio.wait_for(self.s.run_service.wait(run['session_id']), 10)
        self.assertEqual(final.state, 'completed')
        self.assertIn('hello', final.stdout)  # ConPTY includes control sequences and input echo.
        self.assertIsNotNone(final.terminal_session_id)
        with self.assertRaises(PermissionError):
            await self.s.studio.input(workspace['id'], run['session_id'], 'stale\n')
