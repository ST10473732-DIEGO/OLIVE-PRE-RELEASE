"""Verified distribution desktop entries; argv-only launch, no shell expansion."""
import configparser
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import asyncio
import time

from ..application_discovery import AmbiguousApplication, normalized


@dataclass(frozen=True)
class Application:
    id: str
    name: str
    entry: Path
    digest: str
    argv: tuple[str, ...]
    executable: Path


class Applications:
    def __init__(self, roots=None):
        self.roots = tuple(roots or (Path('/usr/share/applications'), Path('/usr/local/share/applications'),
                                    Path.home() / '.local/share/applications'))
        self.values = {}
        self.launches = []
        self.window_processes = {}

    def discover(self):
        result = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob('*.desktop'))[:1000]:
                try:
                    stat = path.stat()
                    if path.is_symlink() or stat.st_uid not in {0, os.getuid()} or stat.st_mode & 0o022 or stat.st_size > 65536:
                        continue
                    data = path.read_bytes()
                    config = configparser.ConfigParser(interpolation=None, strict=True)
                    config.read_string(data.decode('utf-8'))
                    entry = config['Desktop Entry']
                    if entry.get('Type') != 'Application' or any(entry.get(k, 'false').lower() == 'true' for k in ('Hidden', 'NoDisplay', 'Terminal')):
                        continue
                    argv = shlex.split(entry['Exec'])
                    if any('%' in arg and arg not in ('%u', '%U', '%f', '%F') for arg in argv):
                        continue
                    argv = [arg for arg in argv if arg not in ('%u', '%U', '%f', '%F')]
                    if not argv:
                        continue
                    executable = Path(shutil.which(argv[0]) or '').resolve()
                    # No env/shell/interpreter command wrappers or terminal shortcut.
                    if executable.name in {'env', 'sh', 'bash', 'fish', 'zsh', 'python', 'python3', 'konsole', 'xterm'}:
                        continue
                    executable_stat = executable.stat()
                    if not executable.is_file() or executable_stat.st_uid not in {0, os.getuid()} or executable_stat.st_mode & 0o022:
                        continue
                    if executable_stat.st_uid != 0:
                        with executable.open('rb') as binary:
                            if binary.read(4) != b'\x7fELF':
                                continue  # User entries cannot introduce interpreter wrappers.
                    argv[0] = str(executable)
                    app = Application(path.name, entry['Name'], path, hashlib.sha256(data).hexdigest(), tuple(argv), executable)
                    result.setdefault(app.id, app)
                except (OSError, KeyError, ValueError, configparser.Error):
                    continue
        self.values = result
        return list(result.values())

    def resolve(self, requested):
        wanted = normalized(requested)
        matches = [app for app in self.values.values() if wanted in
                   {normalized(app.name), normalized(app.executable.name), normalized(app.id.removesuffix('.desktop'))}]
        if not matches:
            matches = [app for app in self.values.values() if wanted in normalized(app.name)]
        if len(matches) > 1:
            raise AmbiguousApplication([{'id': a.id, 'name': a.name} for a in matches])
        if not matches:
            raise LookupError('No reviewed installed application matches this name')
        return matches[0]

    def processes(self, app):
        import psutil
        result = []
        for process in psutil.process_iter(['pid', 'ppid', 'exe', 'uids', 'create_time']):
            info = process.info
            if info['exe'] and info['uids'] and info['uids'].real == os.getuid() and Path(info['exe']).resolve() == app.executable:
                result.append((info['pid'], info['ppid'], info['create_time']))
        pids = {pid for pid, _, _ in result}
        # Browser renderer/utility children are not independent app instances.
        return [(pid, created) for pid, parent, created in result if parent not in pids]

    def bind_window_processes(self, app, rows):
        """Bind a launcher wrapper to KWin's exact installed desktop identity.

        Only the private typed helper supplies these rows. This is same-user app
        discovery, not a sandbox claim about application-provided metadata.
        """
        import psutil
        if self.values.get(app.id) is not app or hashlib.sha256(app.entry.read_bytes()).hexdigest() != app.digest:
            raise PermissionError('Application entry changed')
        found = []
        for pid in sorted({row['pid'] for row in rows}):
            if type(pid) is not int or pid <= 0:raise ValueError('Invalid application process')
            process = psutil.Process(pid)
            executable = Path(process.exe()).resolve()
            stat = executable.stat()
            if process.uids().real != os.getuid() or stat.st_uid not in {0, os.getuid()} or stat.st_mode & 0o022:
                raise PermissionError('Application process owner or executable changed')
            with executable.open('rb') as source:
                if source.read(4) != b'\x7fELF':raise PermissionError('GUI process is not a native executable')
            created = process.create_time()
            self.window_processes[(app.id, pid, created)] = str(executable)
            found.append((pid, created))
        return found

    def verify_process(self, app, pid, created):
        import psutil
        process = psutil.Process(pid)
        expected = self.window_processes.get((app.id, pid, created), str(app.executable))
        if process.create_time() != created or process.exe() != expected or process.uids().real != os.getuid():
            raise PermissionError('Application process lifetime or executable changed')
        return process

    def launch(self, app):
        if self.values.get(app.id) is not app or hashlib.sha256(app.entry.read_bytes()).hexdigest() != app.digest:
            raise PermissionError('Application entry changed; review again')
        existing = self.processes(app)
        if existing:
            return existing
        # Preserve normal profile and existing windows. Never terminate a user app.
        environment = dict(os.environ)
        # Electron disables AT-SPI on some child processes. That implementation
        # detail must not suppress accessibility in a user-requested GUI app.
        environment.pop('NO_AT_BRIDGE', None)
        process = subprocess.Popen(app.argv, shell=False, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.launches = [p for p in self.launches if p.poll() is None]
        self.launches.append(process)
        return self.processes(app)

    async def wait_for_processes(self, app, stopped, *, timeout=3, clock=time.monotonic, wait=asyncio.sleep, discover=None):
        """Bounded discovery after one launch, not a retry of launching the app.

        Process creation has no portable session event; poll metadata at 100 ms.
        Window readiness uses native AT-SPI events separately.
        """
        deadline = clock() + timeout
        while True:
            if stopped.is_set():
                raise InterruptedError('Stopped while waiting for the requested application')
            found = await asyncio.to_thread(self.processes, app)
            if not found and discover is not None:
                found = await discover()
            if found:
                return found
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError('App launched once but no matching process appeared within the startup budget')
            await wait(min(.1, remaining))
