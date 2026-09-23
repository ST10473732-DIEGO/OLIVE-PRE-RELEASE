"""Reviewed local launches attached via backend-owned ephemeral references."""
import asyncio
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .application_discovery import identity
from .application_sessions import ApplicationSession
from .owned_launch import OwnedLaunch, canonical
from .owned_window_wait import wait_for_owned_window
from ..runtime.request_diagnostics import stage


def fingerprint(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError('Choose a bounded local executable or script')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class LaunchTargets:
    def __init__(self, desktop):
        self.desktop = desktop
        self.records = {}

    async def launch_local(self, path, kind):
        """Only the native file-dialog route supplies this path; no shell args."""
        d = self.desktop
        d.gateway.check()
        selected = Path(path).resolve(strict=True)
        if kind not in {'executable','python'} or (kind == 'python' and selected.suffix.casefold() != '.py'):
            raise ValueError('Unsupported selected launch file')
        if kind == 'executable':
            if os.name == 'nt' and selected.suffix.casefold() != '.exe':
                raise ValueError('Choose a Windows executable')
            if os.name != 'nt':
                with selected.open('rb') as source:
                    if source.read(4) != b'\x7fELF' or not os.access(selected, os.X_OK):
                        raise ValueError('Choose an executable native ELF file; scripts use the reviewed Python route')
        executable = selected if kind == 'executable' else (
            Path(sys.executable).with_name('pythonw.exe') if os.name == 'nt' else Path(sys.executable))
        allowed = [canonical(executable)]
        if kind == 'python':
            # Backend-known interpreter identity, not an arbitrary descendant.
            base = Path(getattr(sys,'_base_executable',sys.executable))
            allowed.append(canonical(base.with_name('pythonw.exe') if os.name == 'nt' else base))
        argv = (str(executable),) if kind == 'executable' else (str(executable),str(selected))
        app = identity(selected.name, 'executable', str(selected))
        return await self.launch(app, argv, tuple(allowed), script=kind == 'python')

    async def launch(self, app, argv, allowed, *, script=False):
        d = self.desktop
        d.gateway.check()
        if len(self.records) >= 16:
            raise ValueError('Launch-session limit reached; restart the isolated session')
        hashes = {p:await asyncio.to_thread(fingerprint,p) for p in set(argv)|set(allowed)}
        session = ApplicationSession(app, str(uuid.uuid4()))
        details = {'application':app.display_name,'executable':argv[0],
                   'arguments':list(argv[1:]),'file_hashes':hashes,
                   'scope':'One new process tree; only verified owned windows',
                   'consequence':'Run selected local code with your account permissions; this is not a sandbox'}
        if script:
            await d.gateway.approval(session,'terminal.execute','Run this selected local script',details,always=True)
        await d.gateway.approval(session,'system.open_application','Launch this selected local application',details,always=True)
        d.gateway.check()
        for permission in (['terminal.execute'] if script else []) + ['system.open_application']:
            d.gateway.require_not_denied(session,permission)
        for path, before in hashes.items():
            if await asyncio.to_thread(fingerprint,path) != before:
                raise PermissionError('Launch file changed after review')
        d.gateway.check()
        # Launch is synchronous here so cancellation cannot lose the owned PID.
        process = subprocess.Popen(list(argv),shell=False)
        import psutil
        live = psutil.Process(process.pid)
        record = OwnedLaunch(app,process.pid,live.create_time(),canonical(live.exe()),tuple(argv),allowed)
        self.records[record.reference] = record
        return {'launch_id':record.reference,'application':app.display_name,
                'state':'launched_not_inspected','message':'Launch recorded. Attach this target to request scoped inspection.'}

    async def attach(self, launch_id):
        stage('launch_reference')
        d = self.desktop
        d.gateway.check()
        record = self.records.get(launch_id)
        if record is None:
            raise ValueError('Unknown or expired launch reference; no action replayed')
        stage('owned_launch_resolution')
        window = await wait_for_owned_window(record, d.gateway.check)
        stage('target_attachment')
        d.gateway.check()
        return await d.inspect_target(record.application,window)

    def snapshot(self):
        return [{'launch_id':r.reference,'application':r.application.display_name,
                 'state':'attached' if r.window else 'launched_not_inspected',
                 'resolution':r.resolution} for r in self.records.values()]
