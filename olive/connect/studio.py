"""Guarded, peer/workspace-scoped C8 authority and bounded process ownership."""
import asyncio
import sqlite3
from dataclasses import dataclass, field
from threading import RLock, Event
import time

from ..agent.permission_service import PermissionDecision, PermissionService
from .contracts import ConnectError, canonical, identifier
from .studio_protocol import CAPABILITIES, ERRORS, PROTOCOL, StudioRequest
from .studio_store import StudioStore


class BoundApproval:
    def __init__(self, request, binding):
        self.request, self.binding = request, binding

    def __getattr__(self, name):
        return getattr(self.request, name)

    def fingerprint(self):
        import hashlib
        return hashlib.sha256(canonical([self.request.fingerprint(), self.binding])).hexdigest()


@dataclass
class Job:
    request: StudioRequest
    channel: object
    binding: str
    revision: int
    handle: object = None
    state: str = 'starting'
    cancelled: bool = False
    task: object = None
    last_poll: float = field(default_factory=time.monotonic)
    released: Event = field(default_factory=Event)
    error: str | None = None


class RemoteStudioService:
    def __init__(self, service, runtime, loop):
        self.service, self.runtime, self.loop = service, runtime, loop
        self.store = StudioStore(service.repository)
        self.lock = RLock()
        self.launch_lock = asyncio.Lock()
        self.jobs = {}
        self.pending = {}
        self.enabled = False
        self.tasks = set()

    def activate(self):
        self.enabled = True

    def share(self, device_id, workspace_id):
        identifier(device_id); identifier(workspace_id)
        workspace = self.runtime.workspace(workspace_id)
        with self.lock, self.service.repository.transaction() as db:
            peer = self.service.repository.get(db, device_id)
            if not peer or peer.get('trust_state') != 'paired':
                raise ConnectError('device_revoked')
            share = self.store.share(db, device_id, workspace.id, self.runtime.root_hash(workspace))
            # Explicit Off rules also override any historical device-wide rule.
            for cap in CAPABILITIES:
                if not any(r['capability'] == cap and r['scope'] == share['workspace_id'] for r in peer['permissions']):
                    peer['permissions'].append(dict(capability=cap, scope=share['workspace_id'], decision='deny'))
            peer['revision'] += 1
            self.service.repository.put(db, peer)
        return self.shared(device_id)

    def permission(self, device_id, workspace_id, capability, decision):
        identifier(device_id); identifier(workspace_id)
        if capability not in CAPABILITIES or capability == 'studio.debug' or decision not in {'allow', 'ask', 'deny'}:
            raise ConnectError('invalid_request')
        with self.lock, self.service.repository.transaction() as db:
            self._share(db, device_id, workspace_id)
            peer = self.service.repository.get(db, device_id)
            if not peer or peer.get('trust_state') != 'paired':
                raise ConnectError('device_revoked')
            peer['permissions'] = [r for r in peer['permissions'] if (r['capability'], r['scope']) != (capability, workspace_id)]
            peer['permissions'].append(dict(capability=capability, scope=workspace_id, decision=decision))
            peer['revision'] += 1
            self.service.repository.put(db, peer)
            db.execute('UPDATE studio_shares_v1 SET revision=revision+1 WHERE peer=? AND reference=?', (device_id, workspace_id))
        self.invalidate(device_id)
        if self.service.approvals:
            self.service.approvals.invalidate(device_id)
        return self.shared(device_id)

    def unshare(self, device_id, workspace_id):
        with self.lock, self.service.repository.transaction() as db:
            db.execute('DELETE FROM studio_shares_v1 WHERE peer=? AND reference=?', (device_id, workspace_id))
            peer = self.service.repository.get(db, device_id)
            if peer:
                peer['permissions'] = [r for r in peer['permissions'] if r['scope'] != workspace_id]
                peer['revision'] += 1
                self.service.repository.put(db, peer)
        self.invalidate(device_id)
        if self.service.approvals:
            self.service.approvals.invalidate(device_id)
        return self.shared(device_id)

    def _share(self, db, peer, reference):
        share = next((s for s in self.store.shares(db, peer) if s['workspace_id'] == reference), None)
        if not share:
            raise ConnectError('workspace_not_shared')
        workspace = self.runtime.workspace(share['local_id'])
        if self.runtime.root_hash(workspace) != share['root_hash']:
            raise ConnectError('workspace_unavailable')
        return share, workspace

    @staticmethod
    def _decision(record, capability, reference):
        # Never inherit device-wide, file, AI, local-tool or other-workspace grants.
        rules = [r for r in record['permissions'] if r['scope'] == reference]
        return PermissionService.evaluate_device(rules, capability, reference)

    def shared(self, peer):
        with self.lock, self.service.repository.transaction(read_only=True) as db:
            record = self.service.repository.get(db, peer)
            return [self._metadata(db, record, s) for s in self.store.shares(db, peer)] if record else []

    def _metadata(self, db, record, share):
        try:
            _, workspace = self._share(db, record['device_id'], share['workspace_id'])
            title = workspace.title[:100]
        except ConnectError:
            title = 'Unavailable workspace'
        return dict(workspace_id=share['workspace_id'], display_name=title,
            share_revision=share['share_revision'], permissions={c: self._decision(record, c, share['workspace_id']).value for c in sorted(CAPABILITIES)})

    def _authority(self, db, req, channel):
        with channel.authority_snapshot(db):
            channel.check()
        if not self.enabled or self.service.closed:
            raise ConnectError('connection_lost')
        if req.source_device_id != channel.peer or req.target_device_id != self.service.local_id:
            raise ConnectError('invalid_request')
        record = self.service.repository.get(db, channel.peer)
        if not record or record['trust_state'] != 'paired' or record.get('public_identity') != channel.public:
            raise ConnectError('device_revoked')
        return record

    def _scope(self, db, req, record, capability=None):
        share, workspace = self._share(db, record['device_id'], req.workspace_id)
        if share['share_revision'] != req.share_revision:
            raise ConnectError('workspace_unavailable')
        cap = capability or req.capability
        policy = next((c for c in self.service.capabilities_from_db(db) if c['capability'] == cap), {})
        decision = self._decision(record, cap, req.workspace_id)
        if policy.get('policy_disabled') or decision == PermissionDecision.DENY:
            raise ConnectError('permission_denied')
        return workspace, decision

    def _approve(self, req, channel, record, binding, title):
        key = (channel.peer, req.request_id)
        now = time.monotonic()
        for old, value in list(self.pending.items()):
            if value[2] < now:
                self.pending.pop(old)
        value = (req.fingerprint(), binding, now + max(0, req.expires_at - self.service.clock()), channel)
        old = self.pending.get(key)
        if old and (old[:2] != value[:2] or old[3] is not channel):
            if self.service.approvals:
                self.service.approvals.discard(*key)
            raise ConnectError('changed_duplicate')
        if not old and len(self.pending) >= 16:
            raise ConnectError('busy')
        self.pending[key] = value
        bound = BoundApproval(req, binding)
        if not self.service.approvals or not self.service.approvals.check(bound, channel.public, record, target_name=title):
            raise ConnectError('confirmation_required')

    def receive(self, raw, channel, deliver):
        req = StudioRequest.decode(raw)
        audit_state = None
        try:
            with self.lock:
                # Commit claim BEFORE any write/process effect. Crashes fail closed.
                consequential = req.operation in ('save', 'build', 'test', 'run')
                with self.service.repository.transaction(timeout=.25, read_only=not consequential,
                        component='studio_receipt_repository' if consequential else 'studio_share_repository') as db:
                    record = self._authority(db, req, channel)
                    now = int(self.service.clock())
                    if req.timestamp > now + 5 or req.expires_at <= now:
                        raise ConnectError('expired_request')
                    if req.operation == 'workspaces':
                        result = self._workspaces(db, req, channel, record)
                    elif req.operation in ('run_status', 'run_cancel'):
                        result = self._status(db, req, channel, record)
                    else:
                        workspace, decision = self._scope(db, req, record)
                        result = self.store.get(db, req)
                        if result is None:
                            binding = self.runtime.binding(workspace, req.operation)
                            if req.operation == 'tree':
                                import hashlib
                                binding = hashlib.sha256(canonical(self.runtime.tree(workspace))).hexdigest()
                            if req.operation in ('read', 'save'):
                                revision = self.runtime.read(workspace, req.arguments['path'])['revision']
                                if req.operation == 'save' and revision != req.arguments['expected_hash']:
                                    raise ConnectError('revision_conflict')
                                binding += revision
                            if decision == PermissionDecision.ASK:
                                self._approve(req, channel, record, binding, workspace.title[:100])
                            if req.operation in ('save', 'build', 'test', 'run'):
                                self.store.claim(db, req)
                            else:
                                result = self.runtime.tree(workspace) if req.operation == 'tree' else self.runtime.read(workspace, req.arguments['path'])
                    authorized_revision = record['revision']
                audit_state = 'completed'
                if result is None:
                    with self.service.repository.transaction(timeout=.25, component='studio_receipt_repository') as db:
                        record = self._authority(db, req, channel)
                        workspace, _ = self._scope(db, req, record)
                        if record['revision'] != authorized_revision:
                            raise ConnectError('permission_denied')
                        if req.operation == 'save':
                            result = self.runtime.save(workspace, req)
                        else:
                            active = [j for j in self.jobs.values() if not j.released.is_set()]
                            if len(active) >= 2 or any(j.channel.peer == channel.peer for j in active) or self.runtime.busy(workspace):
                                raise ConnectError('busy')
                            for key, job in list(self.jobs.items()):
                                if job.released.is_set() and time.monotonic() - job.last_poll > 30:
                                    self.runtime.retire(job.handle)
                                    self.jobs.pop(key)
                            if len(self.jobs) >= 32:
                                raise ConnectError('busy')
                            job = Job(req, channel, binding, record['revision'])
                            self.jobs[(channel.peer, req.request_id)] = job
                            asyncio.run_coroutine_threadsafe(self._run(job), self.loop)
                            result = {'state': 'starting', 'job_id': req.request_id}
                        self.store.finish(db, req, result)
                        audit_state = 'saved' if req.operation == 'save' else 'accepted'
                        self.store.audit(db, req, audit_state, now)
                    # The effect receipt has committed before any success is sent.
                    audit_state = None  # Already recorded atomically with the receipt.
                    if self.service.approvals:
                        self.service.approvals.discard(channel.peer, req.request_id)
                    self.pending.pop((channel.peer, req.request_id), None)
                # Fresh read-only authority pins permission commits through the
                # bounded transmission, without reserving SQLite's writer slot.
                with self.service.repository.transaction(timeout=.25, read_only=True,
                        component='studio_share_repository') as db:
                    record = self._authority(db, req, channel)
                    if record['revision'] != authorized_revision:
                        raise ConnectError('permission_denied')
                    if req.operation == 'workspaces':
                        result = self._workspaces(db, req, channel, record)
                    elif req.operation in ('run_status', 'run_cancel'):
                        result = self._status(db, req, channel, record)
                    else:
                        self._scope(db, req, record)
                    with channel.authority_snapshot(db):
                        deliver(canonical(dict(protocol_version=PROTOCOL, request_id=req.request_id, result=result, error=None)))
        except Exception as error:
            if isinstance(error, (sqlite3.Error, OSError)):
                channel.diagnostics.storage_failed(error)
            code = str(error) if isinstance(error, ConnectError) else (
                'revision_conflict' if isinstance(error, RuntimeError) and 'changed since' in str(error) else
                'file_not_found' if isinstance(error, FileNotFoundError) else
                'unsupported_file' if isinstance(error, (UnicodeError, ValueError, PermissionError)) else 'workspace_unavailable')
            code = {'request_denied': 'permission_denied', 'approval_changed_request': 'changed_duplicate', 'connection_closed': 'connection_lost'}.get(code, code)
            if code not in ERRORS:
                code = 'invalid_request'
            if code in ('revision_conflict', 'changed_duplicate') and self.service.approvals:
                self.service.approvals.discard(channel.peer, req.request_id)
            # Attribute invalid claims to the authenticated source, never a claimed ID.
            from dataclasses import replace
            req = replace(req, source_device_id=channel.peer)
            audit_state = code
            deliver(canonical(dict(protocol_version=PROTOCOL, request_id=req.request_id, result=None, error=code)))
        finally:
            if audit_state is not None and req.operation != 'run_status':
                # Reporting failure must not repeat the failing write and escape
                # into C3. No source/output is sent when authorization failed.
                try:
                    with self.service.repository.transaction(timeout=.25, component='activity_repository') as db:
                        self.store.audit(db, req, audit_state, int(self.service.clock()))
                except (sqlite3.Error, OSError) as error:
                    channel.diagnostics.storage_failed(error)

    def _workspaces(self, db, req, channel, record):
        if any(c['capability'] == 'studio.view' and c['policy_disabled']
               for c in self.service.capabilities_from_db(db)):
            raise ConnectError('permission_denied')
        shares = [s for s in self.store.shares(db, channel.peer)
                  if self._decision(record, 'studio.view', s['workspace_id']) != PermissionDecision.DENY]
        if any(self._decision(record, 'studio.view', s['workspace_id']) == PermissionDecision.ASK for s in shares):
            self._approve(req, channel, record, [(s['workspace_id'], s['share_revision']) for s in shares], 'Shared Studio workspace list')
        return {'workspaces': [self._metadata(db, record, s) for s in shares]}

    def _status(self, db, req, channel, record):
        job = self.jobs.get((channel.peer, req.arguments['job_id']))
        if not job or job.channel is not channel or job.request.workspace_id != req.workspace_id:
            raise ConnectError('workspace_unavailable')
        workspace, _ = self._scope(db, req, record, job.request.capability)
        if record['revision'] != job.revision:
            raise ConnectError('permission_denied')
        job.last_poll = time.monotonic()
        if req.operation == 'run_cancel':
            job.cancelled = True
        result = self.runtime.status(workspace, job.handle) if job.handle else {'state': job.state}
        if job.cancelled:
            result = {'state': 'cancelled' if job.released.is_set() else 'cancelling'}
        return dict(result, job_id=job.request.request_id, error=job.error)

    async def _run(self, job):
        job.task = asyncio.current_task()
        self.tasks.add(job.task)
        try:
            async with self.launch_lock:
                # Authority writes serialize with the actual structured launch.
                with self.lock, self.service.repository.transaction(timeout=.25) as db:
                    record = self._authority(db, job.request, job.channel)
                    workspace, _ = self._scope(db, job.request, record)
                    if job.cancelled or record['revision'] != job.revision:
                        raise ConnectError('permission_denied')
                    if self.runtime.binding(workspace, job.request.operation) != job.binding:
                        raise ConnectError('configuration_changed')
                    job.handle = await self.runtime.start(workspace, job.request.operation)
                    job.state = "running"
            while True:
                if job.cancelled or time.monotonic() - job.last_poll > 15:
                    job.cancelled = True
                    await self.runtime.stop(job.handle)
                    break
                with self.lock, self.service.repository.transaction(timeout=.25, read_only=True) as db:
                    record = self._authority(db, job.request, job.channel)
                    self._scope(db, job.request, record)
                    if record['revision'] != job.revision:
                        raise ConnectError('permission_denied')
                state = self.runtime.status(workspace, job.handle)['state']
                if state != 'running':
                    job.state = state
                    break
                await asyncio.sleep(.1)
        except BaseException as error:
            job.error = str(error) if isinstance(error, ConnectError) and str(error) in ERRORS else 'toolchain_unavailable' if isinstance(error, FileNotFoundError) else job.request.operation + '_failed'
            job.state = 'failed'
        finally:
            if job.handle:
                session = job.handle['session']
                if session.state in {'starting', 'running'}:
                    await self.runtime.stop(job.handle)
            self.tasks.discard(job.task)
            try:
                with self.service.repository.transaction(timeout=.25) as db:
                    self.store.finish(db, job.request, {'job_id': job.request.request_id,
                        'state': 'cancelled' if job.cancelled else job.state, 'error': job.error})
                    self.store.audit(db, job.request, 'cancelled' if job.cancelled else job.state, int(self.service.clock()))
            except Exception:
                pass  # Durable committed claim still prohibits a second launch.
            job.released.set()

    def invalidate(self, peer=None, reason='permission_denied', *, channel=None):
        with self.lock:
            for job in self.jobs.values():
                if (peer is None or job.channel.peer == peer) and (channel is None or job.channel is channel):
                    job.cancelled = True
            for key, value in list(self.pending.items()):
                if (peer is None or key[0] == peer) and (channel is None or value[3] is channel):
                    self.pending.pop(key)
                    if self.service.approvals:
                        self.service.approvals.discard(*key)

    def stop(self, device_id, job_id):
        with self.lock:
            job = self.jobs.get((device_id, job_id))
            if job:
                job.cancelled = True
        return {'cancellation_requested': bool(job)}

    def snapshot(self, peer):
        with self.lock:
            return [dict(job_id=j.request.request_id, workspace_id=j.request.workspace_id,
                operation=j.request.operation, state='cancelled' if j.cancelled else j.state)
                for j in self.jobs.values() if j.channel.peer == peer and not j.released.is_set()]

    def close(self):
        self.enabled = False
        self.invalidate()

    async def shutdown(self):
        self.close()
        deadline = time.monotonic() + 8
        while any(not j.released.is_set() for j in self.jobs.values()):
            if time.monotonic() >= deadline:
                raise TimeoutError('remote_studio_shutdown_timeout')
            await asyncio.sleep(.05)
        with self.lock:
            for job in self.jobs.values():
                self.runtime.retire(job.handle)
            self.jobs.clear()
            self.pending.clear()
