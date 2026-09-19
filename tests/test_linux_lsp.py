"""Python LSP uses installed tooling while keeping a separate project interpreter."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from olive.studio_tooling.lsp import LanguageServices
from olive.studio_tooling.toolchain import module_available


@unittest.skipUnless(sys.platform == 'linux' and module_available(sys.executable, 'pylsp'), 'Linux python-lsp-server required')
class PythonLanguageServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_python_language_features_and_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            program = root / 'main.py'
            source = 'def add(a, b):\n    """Add two values."""\n    return a + b\n\nvalue = add(2, 3)\n'
            program.write_text(source)
            services = LanguageServices(lambda *_: None)
            try:
                session = await services.ensure('ws', directory, 'python', dict(os.environ))
                await session.open(str(program), source, 'python')
                pos = {'position': {'line': 4, 'character': 10}}
                self.assertIn('add', str(await session.feature('hover', str(program), pos)))
                self.assertTrue(await session.feature('definition', str(program), pos))
                self.assertGreaterEqual(len(await session.feature('references', str(program), pos)), 2)
                self.assertIn('add', str(await session.feature('signatureHelp', str(program), {'position': {'line': 4, 'character': 12}})))
                self.assertTrue(await session.feature('documentSymbol', str(program), {}))
                rename = await session.feature('rename', str(program), dict(pos, newName='sum_values'))
                self.assertGreaterEqual(rename['total'], 1)
                self.assertGreaterEqual(str(rename).count('sum_values'), 2)
                await session.change(str(program), source + 'ad')
                completion = await session.feature('completion', str(program), {'position': {'line': 5, 'character': 2}})
                self.assertTrue(any(i['label'].split('(')[0] == 'add' for i in completion['items']), completion)
                await session.change(str(program), 'value=unknown_name\n')
                async with asyncio.timeout(15):
                    while not session.diagnostics.get(str(program)):
                        await asyncio.sleep(.1)
                self.assertIn('undefined name', str(session.diagnostics).lower())
                await session.change(str(program), 'value=1+2\n')
                self.assertTrue(await session.feature('formatting', str(program), {}))
            finally:
                await services.stop_all()
            self.assertFalse(session.transport.alive)
