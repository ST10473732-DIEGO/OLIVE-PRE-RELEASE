"""Private Linux process supervisor; executed in a new session, never imported by UI.

Subreaping is confined to this run so grandchildren are reaped without changing
application-global process state. The child executes an argument array.
"""
import ctypes
import fcntl
import os
import signal
import sys
import termios
import time

import psutil


def main():
    ready = int(sys.argv[1])
    parent = int(sys.argv.pop(2))
    os.set_inheritable(ready, False)
    try:
        if os.getppid() != parent:
            raise OSError('The owning application has exited')
        # A dedicated process (not a preexec_fn in the threaded backend).
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError('Could not establish owned child reaping')
        if os.isatty(0):
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        stopped = False
        def stop(*_):
            nonlocal stopped
            stopped = True
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, stop)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGQUIT, signal.SIG_IGN)
        child = os.fork()
        if child == 0:
            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGPIPE):
                signal.signal(sig, signal.SIG_DFL)
            try:
                os.execvpe(sys.argv[2], sys.argv[2:], os.environ)
            except OSError as error:
                os.write(ready, str(error.errno).encode())
                os._exit(127)
        os.close(ready)
        ready = -1
        status = None
        while not stopped and status is None and os.getppid() == parent:
            pid, value = os.waitpid(-1, os.WNOHANG)
            if pid == child:
                status = value
            if not pid:
                time.sleep(.01)
        # Only identity-bound descendants of this supervisor, including children
        # that created a different process group/session, may be signalled.
        owner = psutil.Process()
        while True:
            for process in reversed(owner.children(recursive=True)):
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass
            try:
                while True:
                    pid, value = os.waitpid(-1, os.WNOHANG)
                    if pid == child and status is None:
                        status = value
                    if pid == 0:
                        break
            except ChildProcessError:
                break
            time.sleep(.01)
        code = os.waitstatus_to_exitcode(status) if status is not None else -signal.SIGTERM
        return code if code >= 0 else 128 - code
    except BaseException as error:
        if ready >= 0:
            os.write(ready, str(getattr(error, 'errno', None) or 5).encode())
        return 127


if __name__ == '__main__':
    sys.exit(main())
