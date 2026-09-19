"""OS-released exclusive writer lock shared by both presentation runtimes."""
import os
from pathlib import Path


class ProfileLock:
    def __init__(self, directory):
        self.path = Path(directory).resolve() / 'runtime-writer.lock'
        self.file = None

    def acquire(self):
        if self.file is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        legacy = self.path.parent / 'qt-runtime.lock'
        if legacy.exists():
            import psutil
            try:
                pid = int(legacy.read_text(encoding='utf-8').splitlines()[0])
            except (OSError, ValueError, IndexError):
                raise RuntimeError('An unreadable Qt profile lock requires review') from None
            if pid != os.getpid() and psutil.pid_exists(pid):
                raise RuntimeError('A Qt runtime is already using this profile')
        stream = self.path.open('a+b')
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            raise RuntimeError('Another OLIVE runtime is using this profile') from error
        self.file = stream
        return self

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()
