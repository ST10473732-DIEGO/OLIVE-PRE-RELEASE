"""Target-only adapter to existing Studio services. Never accepts a command."""
from dataclasses import asdict
import hashlib
from pathlib import Path
import re

from .contracts import ConnectError, canonical
from .studio_protocol import MAX_FILE, OUTPUT_BYTES, TREE_DEPTH, TREE_ENTRIES, relative_path
from ..services.studio_service import StudioService
from ..services.workspace_service import IGNORED
from ..services.run_service import ExecutionPolicy


class StudioRuntime:
    def __init__(self, services):
        self.s = services
        self.tooling = services.studio_tooling

    def workspace(self, identity):
        workspace = self.s.workspace_repo.load_all().get(identity)
        if not workspace or not Path(workspace.root_path).is_dir():
            raise ConnectError('workspace_unavailable')
        return workspace

    @staticmethod
    def root_hash(workspace):
        return hashlib.sha256(workspace.root_path.encode()).hexdigest()

    def _local_permission(self, workspace, permission):
        from ..agent.permission_service import PermissionDecision
        if self.s.permissions.evaluate(permission, workspace.root_path).decision == PermissionDecision.DENY:
            raise ConnectError('permission_denied')

    def path(self, workspace, name):
        relative_path(name)
        root = Path(workspace.root_path)
        current = root
        for part in name.split('/'):
            if part.startswith('.') or part.casefold() in IGNORED or part.casefold() in {'credentials', 'secrets'}:
                raise ConnectError('unsupported_file')
            current = current / part
            if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
                raise ConnectError('unsupported_file')
        path = workspace.resolve(name)
        if not path.is_file():
            raise ConnectError('file_not_found')
        if path.stat().st_size > MAX_FILE:
            raise ConnectError('unsupported_file')
        return path

    def tree(self, workspace):
        self._local_permission(workspace, "filesystem.read")
        values = StudioService(workspace, self.s.checkpoints).tree(
            limit=TREE_ENTRIES + 1, max_depth=TREE_DEPTH, exclude_hidden=True)
        result = []
        size = 0
        for item in values:
            try:
                relative_path(item['path'])
            except ConnectError:
                continue
            if not item['directory']:
                try:
                    self.path(workspace, item['path'])
                except (ConnectError, OSError, PermissionError):
                    continue
            size += len(canonical(item))
            if size > 48000 or len(result) >= TREE_ENTRIES:
                break
            result.append(item)
        return {'entries': result, 'truncated': len(values) > len(result) or any(
            v['directory'] and len(v['path'].split('/')) >= TREE_DEPTH for v in result)}

    def read(self, workspace, path):
        self._local_permission(workspace, "filesystem.read")
        self.path(workspace, path)
        state = StudioService(workspace, self.s.checkpoints).open_file(path)
        if len(state.text.encode('utf-8')) > MAX_FILE:
            raise ConnectError('unsupported_file')
        return {'path': path, 'text': state.text, 'revision': state.loaded_hash}

    def save(self, workspace, req):
        self._local_permission(workspace, "filesystem.write")
        a = req.arguments
        self.path(workspace, a['path'])
        # Use the local Studio writer reservation, but never its editable buffer.
        local = self.s.studio.service(workspace.id)
        with local.write_lock:
            state = local.open_files.get(a['path'])
            if state and state.unsaved:
                raise ConnectError('revision_conflict')
            service = StudioService(workspace, self.s.checkpoints, write_lock=local.write_lock)
            state = service.open_file(a['path'])
            if state.loaded_hash != a['expected_hash']:
                raise ConnectError('revision_conflict')
            state.text = a['text']
            record = service.save(a['path'], 'remote-studio-' + req.source_device_id + '-' + req.request_id)
            return {'revision': record.after_hash, 'state': 'saved'}

    def binding(self, workspace, operation):
        if operation not in ('build', 'test', 'run'):
            return ''
        config = self.tooling.config_get(workspace.id)
        # Bind local configuration and project manifests, never transport their contents.
        from ..studio_tooling import dotnet
        manifests = []
        root = Path(workspace.root_path)
        paths = dotnet._walk(root, {'.csproj', '.fsproj', '.vbproj', '.sln', '.slnx', '.props', '.targets'})
        paths += [root / name for name in ('main.py', 'pyproject.toml', 'global.json') if (root / name).exists()]
        if config['program']:
            paths.append(Path(config['program']))
        if config['launch_profile']:
            # Local profiles may launch arbitrary executables or browsers.
            raise ConnectError('configuration_changed')
        if config['interpreter']:
            interpreter = Path(config['interpreter']).resolve()
            if re.fullmatch(r'python(?:3(?:\.\d+)?)?(?:\.exe)?', interpreter.name, re.IGNORECASE) is None:
                raise ConnectError('toolchain_unavailable')
        if len(paths) > 64:
            raise ConnectError('busy')
        for path in sorted(set(paths)):
            name = path.relative_to(root).as_posix()
            self.path(workspace, name)
            manifests.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
        scanned = dotnet.scan(root)
        for item in scanned['projects']:
            for path in [item['path'], *item['references']]:
                self.path(workspace, Path(path).relative_to(root).as_posix())
        for item in scanned['solutions']:
            for path in item['projects']:
                self.path(workspace, Path(path).relative_to(root).as_posix())
        return hashlib.sha256(canonical([config, manifests, workspace.trust_level])).hexdigest()

    def busy(self, workspace):
        return (workspace.id in self.s.studio.launching or
            any(v.workspace_id == workspace.id and v.state in {'starting', 'running'} for v in self.s.run_service.sessions.values()) or
            any(self.s.studio.validations[k]['workspace_id'] == workspace.id for k in self.s.studio.validation_cancellations))

    async def start(self, workspace, operation):
        from ..agent.permission_service import PermissionDecision
        from ..studio_tooling import dotnet
        from ..services.build_test_service import BuildAndTestService
        for permission in ('filesystem.read', 'terminal.execute'):
            if self.s.permissions.evaluate(permission, workspace.root_path).decision == PermissionDecision.DENY:
                raise ConnectError('permission_denied')
        if self.busy(workspace):
            raise ConnectError('busy')
        # Build/test controller has no isolated-provider parity: preserve fail closed.
        if workspace.trust_level == 'untrusted':
            raise ConnectError('permission_denied')
        root = Path(workspace.root_path)
        for name in ('obj', 'bin'):
            workspace.resolve(name)
            if (root / name).is_symlink() or getattr(root / name, 'is_junction', lambda: False)():
                raise ConnectError('workspace_unavailable')
        if operation == 'run':
            command, kind, cwd, environment = self.tooling._launch_plan(workspace)
            if kind not in {'python_console', 'dotnet_application'}:
                raise ConnectError('run_failed')
            config = self.tooling.config_get(workspace.id)
            if kind == 'dotnet_application':
                # Insert before the application's argument delimiter.
                index = command.index('--') if '--' in command else len(command)
                command[index:index] = ['--no-restore', '--no-build']
            else:
                self.path(workspace, Path(command[1]).relative_to(root).as_posix())
            session = await self.s.run_service.start(workspace, command, kind,
                ExecutionPolicy(workspace.trust_level, 120, False, True), environment, cwd=cwd,
                interactive=False, configured_environment=None, owned_children=True)
            return {'session': session, 'job': None}
        if operation == 'test':
            result = await self.tooling._tool_test({'workspace': workspace.id, '_remote': True}, None)
            job = self.tooling.jobs[result['id']]
        elif dotnet.scan(root)['projects']:
            result = await self.tooling._tool_build({'workspace': workspace.id, 'mode': 'build', '_remote': True}, None)
            job = self.tooling.jobs[result['id']]
        else:
            commands = [c for c in BuildAndTestService().detect(root) if c.name == 'Python compile']
            if not commands:
                raise ConnectError('toolchain_unavailable')
            c = commands[0]
            async def done(job, session):
                return {}
            job = await self.tooling._run_job(workspace, 'build', [c.executable, *c.arguments],
                'Python compile', 'python_build', done, timeout=120, owned_children=True)
        return {'session': self.s.run_service.sessions[job['session_id']], 'job': job}

    async def stop(self, handle):
        if handle['job']:
            await self.tooling.job_cancel(handle['job']['id'])
            await handle['job']['task']
        else:
            await self.s.run_service.stop(handle['session'].id)

    def retire(self, handle):
        if not handle:
            return
        session = handle['session']
        if session.state in {'starting', 'running'}:
            return
        self.s.run_service.sessions.pop(session.id, None)
        self.s.run_service._tasks.pop(session.id, None)
        if handle['job']:
            self.tooling.jobs.pop(handle['job']['id'], None)

    def status(self, workspace, handle):
        session, job = handle['session'], handle['job']
        text = (session.stdout + session.stderr).replace("\0", "")
        # Tool diagnostics can contain absolute paths. Redact path-shaped tokens;
        # arbitrary program output remains explicit workspace code output.
        text = text.replace(workspace.root_path, '<workspace>')
        text = re.sub(r'(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s\x1b<>]+', '<path>', text)
        raw = text.encode('utf-8')
        output = raw[-OUTPUT_BYTES:].decode('utf-8', errors='ignore')
        state = 'running' if session.state in {'created', 'starting', 'running'} or (job and not job['task'].done()) else (
            'cancelled' if session.state in {'stopped', 'timed_out'} else 'completed' if session.exit_code == 0 else 'failed')
        summary = (job or {}).get('summary', {})
        summary = summary if isinstance(summary, dict) else {}
        import math
        summary = {k: v for k, v in summary.items() if type(v) in (int, float) and math.isfinite(v) and v >= 0}
        for k in ('passed', 'failed', 'skipped'):
            if type(summary.get(k)) is not int:
                summary[k] = 0
        diagnostics = []
        diagnostic_bytes = 0
        for item in ((job or {}).get('diagnostics', []) + [r for r in (job or {}).get('results', []) if isinstance(r, dict) and r.get('state') == 'failed'])[:32]:
            if not isinstance(item, dict):
                continue
            file = item.get('file', '')
            try:
                name = Path(file).resolve().relative_to(Path(workspace.root_path)).as_posix() if file else ''
                if name:
                    relative_path(name)
            except (ValueError, ConnectError):
                name = ''
            message = str(item.get('message', ''))[:512].replace(workspace.root_path, '<workspace>')
            message = re.sub(r'(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s\x1b<>]+', '<path>', message).replace('\0', '')
            line = item.get('line', 0)
            entry = dict(path=name, line=line if type(line) is int and 0 <= line <= 10000000 else 0,
                severity='warning' if item.get('severity') == 'warning' else 'error', message=message)
            diagnostic_bytes += len(canonical(entry))
            if diagnostic_bytes > 8000:
                break
            diagnostics.append(entry)
        if state == 'completed' and job and job['kind'] == 'test' and (job.get('error') or 'summary' not in job):
            state = 'failed'
        return {'state': state, 'exit_code': session.exit_code, 'output': output, 'diagnostics': diagnostics,
            'truncated': len(raw) > OUTPUT_BYTES or len(session.stdout) >= self.s.run_service.MAX_OUTPUT or len(session.stderr) >= self.s.run_service.MAX_OUTPUT,
            'tests': {key: summary.get(key, 0) for key in ('passed', 'failed', 'skipped', 'duration_seconds')}}
