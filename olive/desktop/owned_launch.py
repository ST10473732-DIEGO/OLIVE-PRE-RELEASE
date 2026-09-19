"""Ephemeral launch references and conservative process-bound window resolution."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import time
import uuid
from ..runtime.request_diagnostics import stage, current


class NoOwnedWindow(LookupError):
    """Verified process exists, but no eligible owned window was observed."""


class AmbiguousOwnedWindow(LookupError):
    """More than one eligible owned window; selection must never be guessed."""


def canonical(value):
    return os.path.normcase(str(Path(value).resolve()))


@dataclass
class OwnedLaunch:
    application: object
    pid: int
    created: float
    executable: str
    argv: tuple
    allowed_executables: tuple
    reference: str = field(default_factory=lambda: uuid.uuid4().hex)
    recorded: float = field(default_factory=time.monotonic)
    window: dict | None = None
    resolution: dict = field(default_factory=dict)

    def processes(self, process_factory=None, diagnostic=None):
        import psutil
        factory = process_factory or psutil.Process
        counts = diagnostic if diagnostic is not None else {}
        counts.update(candidates=0, accepted=0, executable_rejected=0,
                      command_rejected=0, lifetime_rejected=0)
        if time.monotonic() - self.recorded > 1200:
            raise PermissionError('Launch reference expired; review a new launch')
        root = factory(self.pid)
        if root.create_time() != self.created or canonical(root.exe()) != self.executable:
            raise PermissionError('Launcher lifetime or executable changed')
        candidates = [root, *root.children(recursive=True)]
        counts['candidates'] = len(candidates)
        if len(candidates) > 32:
            raise PermissionError('Launch process tree exceeds its bounded scope')
        accepted = {}
        for process in candidates:
            if canonical(process.exe()) not in self.allowed_executables:
                counts['executable_rejected'] += 1
                continue
            # A Python interpreter alone is not the application. Require the exact
            # reviewed command (including script), even for redirector descendants.
            command = process.cmdline()
            if len(command) != len(self.argv) or any(canonical(a) != canonical(b) for a,b in zip(command,self.argv)):
                counts['command_rejected'] += 1
                continue
            created = process.create_time()
            if created < self.created:
                counts['lifetime_rejected'] += 1
                continue
            cursor = process
            visited = set()
            while cursor.pid != self.pid:
                if cursor.pid in visited or len(visited) >= 32:
                    raise PermissionError('Invalid process ancestry')
                visited.add(cursor.pid)
                parent = cursor.parent()
                if parent is None or parent.create_time() > cursor.create_time():
                    raise PermissionError('Process ancestry changed')
                if canonical(parent.exe()) not in self.allowed_executables or tuple(map(canonical,parent.cmdline())) != tuple(map(canonical,self.argv)):
                    raise PermissionError('Unexpected process in launch ancestry')
                cursor = parent
            if cursor.create_time() != self.created:
                raise PermissionError('Launcher PID was reused')
            accepted[process.pid] = created
            counts['accepted'] += 1
        if self.pid not in accepted:
            raise PermissionError('Launcher command identity changed')
        return accepted

    def resolve(self, *, process_factory=None, window_reader=None):
        from .windows_observation import windows_for_processes
        import psutil
        detail = dict(launch_id=self.reference, launch_pid=self.pid,
                      elapsed_ms=round((time.monotonic()-self.recorded)*1000, 2),
                      process_alive=None, eligible_count=None, initial={}, enumeration={}, revalidation={})
        self.resolution = detail
        context = current.get()
        if context is not None:
            context.resolution = detail
        try:
            return self._resolve(process_factory, window_reader, windows_for_processes, detail)
        except Exception as error:
            detail['error_category'] = type(error).__name__
            if isinstance(error, psutil.NoSuchProcess):
                detail.update(outcome='owned_process_exited', process_alive=False)
            elif isinstance(error, PermissionError):
                # All identity errors here are fixed, application-authored messages.
                detail.update(outcome='owned_identity_rejected', identity_failure=str(error))
            elif 'outcome' not in detail:
                detail['outcome'] = 'enumeration_failure' if detail['phase'] == 'enumeration' else 'process_query_failure'
            raise

    def _resolve(self, process_factory, window_reader, default_reader, detail):
        stage('owned_process_identity')
        detail['phase'] = 'initial_identity'
        owned = self.processes(process_factory, detail['initial'])
        detail['process_alive'] = True
        stage('owned_window_resolution')
        detail['phase'] = 'enumeration'
        windows = window_reader(owned) if window_reader else default_reader(owned, detail['enumeration'])
        # Re-read lifetime/ancestry after enumeration to reject races and exits.
        stage('owned_identity_revalidation')
        detail['phase'] = 'identity_revalidation'
        fresh = self.processes(process_factory, detail['revalidation'])
        matches = []
        rejected = dict(unowned_pid=0, lifetime=0, executable=0)
        candidates = []
        for w in windows:
            pid = w.get('pid')
            if pid not in fresh:
                rejected['unowned_pid'] += 1
                continue
            # Never retain metadata supplied for an unrelated process.
            candidates.append({k:w.get(k) for k in ('hwnd','pid','process_created')})
            if w.get('process_created') != fresh[pid]:
                rejected['lifetime'] += 1
            elif canonical(w.get('executable','')) not in self.allowed_executables:
                rejected['executable'] += 1
            else:
                matches.append(w)
        detail.update(eligible_count=len(matches), window_rejections=rejected, candidates=candidates[:32])
        if not matches:
            detail['outcome'] = 'no_eligible_owned_window'
            raise NoOwnedWindow('No eligible owned window; no target selected')
        if len(matches) > 1:
            detail['outcome'] = 'multiple_eligible_owned_windows'
            raise AmbiguousOwnedWindow('Multiple eligible owned windows; no target selected')
        window = matches[0]
        if self.window and any(window.get(k) != self.window.get(k) for k in ('hwnd','pid','process_created')):
            raise PermissionError('Owned target changed; review a new launch')
        self.window = dict(window)
        detail['outcome'] = 'unique_owned_window'
        return window
