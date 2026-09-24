import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from olive.application.service_container import ServiceContainer
from olive.authority.owner import owner_identity


class OwnerChatFilesTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_workspace_reference_runs_exact_owned_project_without_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            ask=AsyncMock(side_effect=AssertionError('Redundant approval'))
            s=ServiceContainer(lambda *_:None,ask,directory,migrate=False)
            s.settings.update(owner_mode=True,owner_installation={'id':'fixture','owner':owner_identity()})
            try:
                old=s.data.create_coding_project('Old','python')
                chosen=s.data.create_coding_project('Chosen','python')
                (Path(chosen['root_path'])/'main.py').write_text('print("selected reference ran")\n')
                s.interaction.select_workspace(old['id'])
                s.interaction.context(s.current_chat_id).workspace_id=old['id']
                s.interaction.interpreter.interpret=AsyncMock(return_value={'confidence':1,'clarification':'','steps':[
                    {'intent':'code.run','entities':{},'references':{}}]})
                await s.interaction.submit('Run my project',workspace_id=chosen['id'])
                await asyncio.wait_for(asyncio.gather(*s.run_service._tasks.values()),10)
                run=list(s.run_service.sessions.values())[-1]
                self.assertEqual(run.workspace_id,chosen['id'])
                self.assertEqual(run.state,'completed');self.assertEqual(run.exit_code,0)
                self.assertIn('selected reference ran',run.stdout)
                ask.assert_not_awaited()
            finally:await s.shutdown()

    async def test_answer_and_remote_requests_do_not_acquire_selected_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            s=ServiceContainer(lambda *_:None,AsyncMock(),directory,migrate=False)
            s.settings.update(owner_mode=True,owner_installation={'id':'fixture','owner':owner_identity()})
            s.chat.send=AsyncMock()
            try:
                chosen=s.data.create_coding_project('Private','python')
                await s.interaction.submit('Give me Java code for a calculator',workspace_id=chosen['id'])
                self.assertIsNone(s.interaction.context(s.current_chat_id).workspace_id)
                s.interaction.interpreter.interpret=AsyncMock(return_value={'confidence':1,'clarification':'','steps':[
                    {'intent':'conversation.answer','entities':{},'references':{}}]})
                await s.interaction.submit('Write the code and then run it in an isolated preview',workspace_id=chosen['id'])
                self.assertIsNone(s.interaction.context(s.current_chat_id).workspace_id)
                s.chat.targets[s.current_chat_id]={'device_id':'remote'}
                await s.interaction.submit('Run my project',workspace_id=chosen['id'])
                self.assertIsNone(s.interaction.context(s.current_chat_id).workspace_id)
                self.assertFalse(s.run_service.sessions)
                self.assertFalse(any(e['stage']=='workspace_reference_bound' for t in s.interaction.request_traces for e in t['events']))
            finally:await s.shutdown()

    async def test_stale_workspace_reference_never_falls_back_to_another_project(self):
        with tempfile.TemporaryDirectory() as directory:
            s=ServiceContainer(lambda *_:None,AsyncMock(),directory,migrate=False)
            try:
                with self.assertRaisesRegex(ValueError,'no longer available'):
                    await s.interaction.submit('Run my project',workspace_id='removed')
                self.assertFalse(s.run_service.sessions)
            finally:await s.shutdown()

    async def test_actual_chat_create_edit_move_and_code_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            ask=AsyncMock(side_effect=AssertionError('Redundant approval'))
            services=ServiceContainer(lambda *_:None,ask,directory,migrate=False)
            services.settings.update(owner_mode=True,owner_installation={'id':'fixture','owner':owner_identity()})
            source=Path(directory)/'note.py';target=Path(directory)/'moved.py'
            try:
                for request in [f'Create a Python file at {source} containing "print(42)\\n"',
                                f'Edit {source} to contain "print(43)"',
                                f'Move {source} to {target}']:
                    await services.interaction.submit(request)
                self.assertEqual(target.read_text(),'print(43)')
                self.assertFalse(source.exists());ask.assert_not_awaited()
                services.chat.send=AsyncMock()
                await services.interaction.submit('Give me Python code containing the words "delete and send".')
                services.chat.send.assert_awaited_once()
                self.assertEqual(target.read_text(),'print(43)')
            finally:await services.shutdown()
