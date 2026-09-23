"""Linux PTY adapter for the existing terminal session/output protocol."""
import codecs
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import threading
import time


class PosixPTY:
    def __init__(self, columns, rows, cwd, environment, shell, command=None):
        if not command:
            if shell not in {'bash', 'sh'}:
                raise ValueError('Choose a Linux shell: bash or sh')
            executable = shutil.which(shell, path=environment.get('PATH'))
            if not executable:
                raise FileNotFoundError(shell)
            command = [executable, '--noprofile', '--norc', '-i'] if shell == 'bash' else [executable, '-i']
        self.fd_lock = threading.RLock()
        self.master, slave = pty.openpty()
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.process = None
        ready_read, ready_write = os.pipe()
        try:
            self.set_size(columns, rows)
            env = dict(environment, TERM='xterm-256color')
            self.process = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name('posix_exec.py')), str(ready_write), str(os.getpid()), *command],
                cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                start_new_session=True, pass_fds=(ready_write,), close_fds=True)
            os.close(ready_write)
            ready_write = -1
            if not select.select([ready_read], [], [], 10)[0]:
                raise TimeoutError('The terminal process could not be started')
            failure = os.read(ready_read, 64)
            if failure:
                number = int(failure)
                raise OSError(number, os.strerror(number), command[0])
            self.pid = self.process.pid
            os.set_blocking(self.master, False)
        except BaseException:
            if self.process:
                self.terminate()
            else:
                self.close()
            raise
        finally:
            os.close(slave)
            os.close(ready_read)
            if ready_write >= 0:
                os.close(ready_write)

    def set_size(self, columns, rows):
        with self.fd_lock:
            if self.master < 0:
                raise ValueError('The terminal is closed')
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))

    def isalive(self):
        return self.process.poll() is None

    def read(self, blocking=False):
        with self.fd_lock:
            if self.master < 0:
                return ''
            try:
                if not select.select([self.master], [], [], .05 if blocking else 0)[0]:
                    return ''
                return self.decoder.decode(os.read(self.master, 65536))
            except OSError as error:
                if error.errno in (errno.EIO, errno.EAGAIN):
                    return ''
                raise

    def write(self, data):
        payload = memoryview(data.encode('utf-8'))
        deadline = time.monotonic() + 3
        while payload:
            if not self.isalive():
                raise ValueError('The terminal is not running')
            if time.monotonic() >= deadline:
                raise TimeoutError('Terminal input timed out')
            with self.fd_lock:
                if self.master < 0:
                    raise ValueError('The terminal is closed')
                if select.select([], [self.master], [], .05)[1]:
                    try:
                        payload = payload[os.write(self.master, payload):]
                    except BlockingIOError:
                        pass

    def get_exitstatus(self):
        code = self.process.wait(timeout=5)
        self.close()
        return code

    def terminate(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # The still-owned session leader pins this process-group ID.
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        self.close()

    def close(self):
        # Natural reader exit and user Stop can arrive concurrently. Transfer
        # ownership before close, and exclude I/O until the descriptor is gone.
        with self.fd_lock:
            descriptor, self.master = self.master, -1
            if descriptor >= 0:
                os.close(descriptor)
