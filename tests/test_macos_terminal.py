"""Studio's interactive terminal on macOS: a real PTY under the POSIX supervisor."""
import asyncio
import re
import sys
import tempfile
import time
import unittest

import psutil

from olive.studio_tooling.pty import TerminalSession


def alive(pid):
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


@unittest.skipUnless(sys.platform == "darwin", "macOS terminal")
class MacTerminalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = []
        self.env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": self.temp.name, "LANG": "en_US.UTF-8"}

    async def asyncTearDown(self):
        self.temp.cleanup()

    def session(self, shell):
        def publish(topic, value):
            if topic == "terminal.data":
                self.output.append(value["data"])
        session = TerminalSession("t-" + shell, "w", self.temp.name, shell, "Terminal", asyncio.get_running_loop(), publish)
        session.start(self.env)
        return session

    async def wait_for(self, pattern, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            match = re.search(pattern, "".join(self.output).replace("\r", ""))
            if match:
                return match
            await asyncio.sleep(.05)
        self.fail(f"no {pattern!r} in terminal output: {''.join(self.output)[-400:]!r}")

    async def test_each_shell_is_a_real_terminal_with_size_input_and_ctrl_c(self):
        for shell in ("zsh", "bash", "sh"):
            with self.subTest(shell=shell):
                self.output.clear()
                session = self.session(shell)
                try:
                    session.resize(120, 40)
                    session.write('echo "ready-$((6*7))"; stty size; tty\n')
                    await self.wait_for(r"ready-42")
                    await self.wait_for(r"40 120")
                    await self.wait_for(r"/dev/ttys\d+")
                    session.write("sleep 30\n")
                    await asyncio.sleep(.5)
                    session.write("\x03")  # Ctrl-C reaches the foreground job, not the shell.
                    session.write("echo after-interrupt\n")
                    await self.wait_for(r"after-interrupt")
                finally:
                    session.kill()

    async def test_closing_reaps_background_and_disowned_jobs(self):
        for shell in ("zsh", "bash"):
            with self.subTest(shell=shell):
                self.output.clear()
                session = self.session(shell)
                session.write("sleep 300 & echo job=$!\n")
                job = int((await self.wait_for(r"job=(\d+)")).group(1))
                self.assertTrue(alive(job))
                session.kill()
                for _ in range(60):
                    if not alive(job):
                        break
                    await asyncio.sleep(.05)
                self.assertFalse(alive(job), "a background job outlived its terminal")
                # A disowned job whose shell already exited has no live parent chain left.
                self.output.clear()
                session = self.session(shell)
                session.write("nohup sleep 300 >/dev/null 2>&1 &\n")
                session.write("echo orphan=$!\n")
                session.write("disown\n")
                orphan = int((await self.wait_for(r"orphan=(\d+)")).group(1))
                session.write("exit\n")
                for _ in range(100):
                    if not alive(orphan):
                        break
                    await asyncio.sleep(.05)
                session.kill()
                self.assertFalse(alive(orphan), "a disowned job outlived its terminal session")


if __name__ == "__main__":
    unittest.main()
