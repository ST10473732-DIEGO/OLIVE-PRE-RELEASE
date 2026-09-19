"""Pipe-based Linux jobs using the same scoped descendant reaper as PTYs."""
import asyncio
import os
from pathlib import Path
import select
import sys


class OwnedProcess:
    def __init__(self, process):
        self.process = process

    def __getattr__(self, name):
        return getattr(self.process, name)

    def kill(self):
        # Let the private supervisor kill and reap its subtree before exiting.
        try:
            self.process.terminate()
        except ProcessLookupError:
            pass

    terminate = kill


async def start_owned_process(command, **options):
    read_fd, write_fd = os.pipe()
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('posix_exec.py')), str(write_fd), str(os.getpid()), *command,
            start_new_session=True, pass_fds=(write_fd,), **options)
        os.close(write_fd)
        write_fd = -1

        def ready():
            if not select.select([read_fd], [], [], 10)[0]:
                raise TimeoutError('The owned process could not be started')
            return os.read(read_fd, 64)

        failure = await asyncio.to_thread(ready)
        if failure:
            number = int(failure)
            raise OSError(number, os.strerror(number), command[0])
        return OwnedProcess(process)
    except BaseException:
        if process:
            OwnedProcess(process).kill()
            await process.wait()
        raise
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)
