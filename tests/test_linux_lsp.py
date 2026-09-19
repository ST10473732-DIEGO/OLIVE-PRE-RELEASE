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
            events = []
            services = LanguageServices(lambda name, payload: events.append((name, payload)))
            try:
                session = await services.ensure('ws', directory, 'python', dict(os.environ))
                # Exercise the pinned Studio providers, independent of host lint plugins.
                await session.notify('workspace/didChangeConfiguration', {'settings': {
                    'pylsp': {'plugins': {
                        'pyflakes': {'enabled': True},
                        'pycodestyle': {'enabled': False},
                        'mccabe': {'enabled': False},
                        'flake8': {'enabled': False},
                        'pylint': {'enabled': False},
                        'autopep8': {'enabled': True},
                        'yapf': {'enabled': False},
                    }}}})
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
                version = await session.change(str(program), 'value=unknown_name\n')
                # Earlier edits may still publish E305 or an undefined `ad`.
                # Only diagnostics for this document version prove the contract.
                def current_diagnostics():
                    return [diagnostic for name, event in events
                            if name == 'lsp.diagnostics' and event['path'] == str(program)
                            and event['version'] == version
                            for diagnostic in event['diagnostics']]
                async with asyncio.timeout(15):
                    while not current_diagnostics():
                        await asyncio.sleep(.1)
                self.assertTrue(any(item['source'] == 'pyflakes'
                                    and "undefined name 'unknown_name'" in item['message'].lower()
                                    for item in current_diagnostics()), current_diagnostics())
                await session.change(str(program), 'value=1+2\n')
                self.assertTrue(await session.feature('formatting', str(program), {}))
            finally:
                await services.stop_all()
            self.assertFalse(session.transport.alive)
