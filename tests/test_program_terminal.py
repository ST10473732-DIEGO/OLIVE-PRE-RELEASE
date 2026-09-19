"""Real ConPTY runs in synthetic workspaces; no unrelated process is touched."""
import asyncio
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

import psutil

from olive.services.run_service import RunService
from olive.studio_tooling.pty import TerminalServices
from olive.workspace import Workspace


@unittest.skipUnless(sys.platform in {"win32", "linux"}, "Native PTY platform required")
class ProgramTerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_closing_terminal_reaps_program_and_owned_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'main.py'
            source.write_text('import subprocess, sys, time\n'
                              'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])\n'
                              'print("CHILD=" + str(child.pid), flush=True)\n'
                              'time.sleep(120)\n')
            runs = RunService()
            terminals = TerminalServices(lambda *_: None)
            runs.terminals = terminals
            workspace = Workspace(root_path=str(root), title='Owned fixture')
            session = await runs.start(workspace, [sys.executable, str(source)], interactive=True)
            try:
                for _ in range(100):
                    match = re.search(r'CHILD=(\d+)', session.stdout)
                    if match:
                        break
                    await asyncio.sleep(.05)
                self.assertIsNotNone(match, session.stdout)
                child = psutil.Process(int(match[1]))
                terminals.close(session.terminal_session_id)
                final = await asyncio.wait_for(runs.wait(session.id), 5)
                self.assertFalse(final.accepts_input)
                self.assertNotEqual(final.state, 'running')
                self.assertFalse(child.is_running())
                self.assertFalse(psutil.pid_exists(session.process_id))
            finally:
                await runs.stop(session.id)
                terminals.close_all()

    async def test_missing_executable_is_a_failed_run_not_permanently_starting(self):
        with tempfile.TemporaryDirectory() as directory:
            runs = RunService()
            runs.terminals = TerminalServices(lambda *_: None)
            workspace = Workspace(root_path=directory, title='Missing executable fixture')
            with self.assertRaises(Exception):
                await runs.start(workspace, [str(Path(directory) / 'missing.exe')], interactive=True)
            self.assertEqual(next(iter(runs.sessions.values())).state, 'failed')
