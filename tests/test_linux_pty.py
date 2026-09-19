"""Real Linux session ownership, UTF-8, resize, natural exit and shell tests."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
import psutil
from olive.studio_tooling.pty import TerminalServices
from olive.services.build_test_service import BuildAndTestService


@unittest.skipUnless(sys.platform == 'linux', 'Linux PTY acceptance')
class LinuxPTYTests(unittest.IsolatedAsyncioTestCase):
    async def test_shell_utf8_resize_and_natural_exit_reaps_detached_descendant(self):
        events=[]
        terminals=TerminalServices(lambda topic, value: events.append((topic,value)))
        unrelated=await asyncio.create_subprocess_exec(sys.executable,'-c','import time; time.sleep(60)')
        with tempfile.TemporaryDirectory() as directory:
            def output():return ''.join(v['data'] for t,v in events if t=='terminal.data')
            async def wait_for(text):
                async with asyncio.timeout(10):
                    while text not in output():await asyncio.sleep(.02)
            try:
                session=terminals.create('ws',directory,'bash',dict(os.environ))
                session.resize(123,41)
                session.write("stty size; printf 'héllo東京\\n'\r")
                await wait_for('41 123')
                await wait_for('héllo東京')
                session.write('exit\r')
                async with asyncio.timeout(5):
                    while session.state=='running':await asyncio.sleep(.02)
                with self.assertRaises(ValueError):session.write('stale')
                source=Path(directory)/'main.py'
                source.write_text('import subprocess,sys\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],start_new_session=True)\nprint("OWNED="+str(p.pid),flush=True)\n')
                session=terminals.create('ws',directory,'program',dict(os.environ),command=[sys.executable,str(source)])
                async with asyncio.timeout(5):
                    while session.state=='running':await asyncio.sleep(.02)
                import re
                pid=int(re.search(r'OWNED=(\d+)',output())[1])
                self.assertFalse(psutil.pid_exists(pid), 'Detached child must be reaped, not left as a zombie')
                self.assertFalse(psutil.pid_exists(session.pid))
                self.assertIsNone(unrelated.returncode)
            finally:
                terminals.close_all()
                unrelated.terminate();await unrelated.wait()

    def test_project_venv_precedes_system_and_never_falls_back_to_repo_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(BuildAndTestService.python_executable(root),sys._base_executable)
            python=root/'.venv/bin/python';python.parent.mkdir(parents=True);python.symlink_to(sys._base_executable)
            self.assertEqual(BuildAndTestService.python_executable(root),str(python))

    async def test_pipe_jobs_reap_detached_children_on_exit_and_stop(self):
        from olive.services.run_service import RunService
        from olive.workspace import Workspace
        import re
        with tempfile.TemporaryDirectory() as directory:
            for stop in (False, True):
                with self.subTest(stop=stop):
                    runs = RunService()
                    workspace = Workspace(root_path=directory, title='Pipe fixture')
                    code = 'import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],start_new_session=True)\nprint("CHILD="+str(p.pid),flush=True)\n' + ('time.sleep(60)\n' if stop else '')
                    session = await runs.start(workspace, [sys.executable, '-c', code])
                    child = None
                    try:
                        async with asyncio.timeout(5):
                            while not (match := re.search(r'CHILD=(\d+)', session.stdout)):
                                await asyncio.sleep(.02)
                        child = int(match[1])
                        if stop:
                            await runs.stop(session.id)
                        final = await asyncio.wait_for(runs.wait(session.id), 5)
                        self.assertEqual(final.state, 'stopped' if stop else 'completed')
                        self.assertFalse(psutil.pid_exists(child))
                        self.assertFalse(psutil.pid_exists(session.process_id))
                    finally:
                        await runs.stop(session.id)
                        if child and psutil.pid_exists(child):
                            psutil.Process(child).kill()

    async def test_abrupt_owner_exit_reaps_its_live_job(self):
        import json
        script = '''import asyncio, os, sys, json
from olive.studio_tooling.posix_process import start_owned_process
async def main():
    process = await start_owned_process([sys.executable, '-c', 'import os,time; print(os.getpid(),flush=True); time.sleep(60)'], env=dict(os.environ), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    child = int(await process.stdout.readline())
    print(json.dumps([process.pid,child]), flush=True)
    await asyncio.Event().wait()
asyncio.run(main())
'''
        owner = await asyncio.create_subprocess_exec(sys.executable, '-c', script, stdout=asyncio.subprocess.PIPE)
        try:
            identities = json.loads(await asyncio.wait_for(owner.stdout.readline(), 10))
            owner.terminate()
            await owner.wait()
            async with asyncio.timeout(10):
                while any(psutil.pid_exists(pid) for pid in identities):
                    await asyncio.sleep(.05)
        finally:
            if owner.returncode is None:
                owner.terminate()
                await owner.wait()
