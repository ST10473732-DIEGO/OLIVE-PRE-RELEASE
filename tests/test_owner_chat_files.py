import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from olive.application.service_container import ServiceContainer
from olive.authority.owner import owner_identity


class OwnerChatFilesTests(unittest.IsolatedAsyncioTestCase):
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
