"""Bounded target job owner, separate from TLS, permission and model authority."""
import asyncio
from collections import deque
from dataclasses import dataclass, field
from threading import Event, RLock
import time

from ..agent.permission_service import PermissionDecision, PermissionService
from .contracts import ConnectError, canonical
from .inference_protocol import (CAPABILITY, CHUNK_BYTES, ERRORS, PROTOCOL, TERMINAL,
                                 InferenceRequest, input_size)
from .inference_store import InferenceStore


@dataclass
class Job:
    request: InferenceRequest
    channel: object
    rules: list
    born: float
    state: str = 'awaiting_approval'
    error: str | None = None
    future: object = None
    task: object = None
    cancel_requested: bool = False
    closing: bool = False  # Run left generation; only cleanup remains (loop thread only).
    released: Event = field(default_factory=Event)
    events: deque = field(default_factory=deque)
    sequence: int = 0
    acknowledged: int = 0
    output_bytes: int = 0
    last_poll: float = 0
    ended: float = 0
    queued_at: float = 0

    def __post_init__(self):
        self.released.set()  # No runtime owner until execution is scheduled.

    @property
    def peer(self):
        return self.channel.peer


class RemoteInferenceService:
    ACTIVE = 1
    QUEUED = 2
    PER_PEER = 1  # one active/queued/approval request per peer
    APPROVALS = 4
    QUEUE_SECONDS = 30
    INACTIVITY = 15
    RETENTION = 30

    def __init__(self, service, runtime, loop, *, clock=time.monotonic):
        self.service, self.runtime, self.loop, self.clock = service, runtime, loop, clock
        self.lock = RLock()
        self.store = InferenceStore(service.repository)
        self.jobs = {}
        self.active = None
        self.enabled = False
        self.monitor = None
        self.monitor_task = None
        self.tasks = set()  # Actual coroutines on the existing model event loop.
        self.owners = {}  # Includes scheduled tasks that have not started yet.

    def activate(self):
        with self.lock:
            self.enabled = True
            if self.monitor is None or self.monitor.done():
                self.monitor = asyncio.run_coroutine_threadsafe(self._monitor(), self.loop)

    def _authority(self, db, req, channel, *, permission=True):
        channel.check()
        record = self.service.repository.get(db, channel.peer)
        if (not self.enabled or self.service.closed or req.source_device_id != channel.peer
                or req.target_device_id != self.service.local_id):
            raise ConnectError('device_unavailable')
        if not record or record['trust_state'] != 'paired' or record.get('public_identity') != channel.public:
            raise ConnectError('device_revoked')
        metadata = next(c for c in self.service.capabilities_from_db(db) if c['capability'] == CAPABILITY)
        decision = PermissionService.evaluate_device(record['permissions'], CAPABILITY)
        if metadata['policy_disabled']:
            decision = PermissionDecision.DENY
        if permission and decision == PermissionDecision.DENY:
            raise ConnectError('permission_denied')
        return record, decision

    def _job_authority(self, db, job):
        record, decision = self._authority(db, job.request, job.channel)
        if record['permissions'] != job.rules:
            raise ConnectError('permission_denied')
        if job.state == 'awaiting_approval' and decision == PermissionDecision.ASK:
            approvals = self.service.approvals
            if not approvals or not approvals.check(job.request, job.channel.public, record,
                    target_name=self.service.repository.get(db, self.service.local_id)['display_name']):
                raise ConnectError('confirmation_required')
        return record

    def _audit(self, db, job, state):
        self.service.repository.audit(db, job.peer, job.request.job_id, CAPABILITY,
            int(self.service.clock()), 'remote_ai_' + state)

    def _finish(self, job, state, error=None, *, db=None):
        if job.state in TERMINAL:
            return
        job.state, job.error, job.ended = state, error, self.clock()
        # Prompt/context lives only while its job does. Receipt retains digest only.
        if db is None:
            try:
                with self.service.repository.transaction(timeout=.25) as transaction:
                    self.store.finish(transaction, job, state, error, job.ended - job.born)
                    self._audit(transaction, job, state)
            except Exception:
                # The already-committed claim still prevents replay after restart.
                # Receipt contention must never prevent cancellation/lease release.
                pass
        else:
            self.store.finish(db, job, state, error, job.ended - job.born)
            self._audit(db, job, state)
        if self.service.approvals:
            self.service.approvals.discard(job.peer, job.request.request_id)

    def _cancel(self, job):
        # Called under self.lock. Cancelling a concurrent Future marks it done
        # before its coroutine unwinds. Keep that future intact; cancel the actual
        # task once, so repeated Stop/invalidation cannot interrupt async cleanup.
        if job.future is not None and not job.cancel_requested and not job.released.is_set():
            job.cancel_requested = True
            self.loop.call_soon_threadsafe(self._cancel_task, job)

    @staticmethod
    def _cancel_task(job):
        # Runs on the model loop, like _run, so `closing` cannot change underneath.
        # A run that already ended on its own (permission seen by _offer, output
        # limit, timeout) is only closing its stream and slot: a late Stop must not
        # interrupt that, or the slot release can be dropped while `released` is set.
        if job.closing:
            return
        if job.task is not None and not job.task.done() and not job.task.cancelling():
            job.task.cancel()
        # Before task creation, _run observes the already-terminal job instead.

    @staticmethod
    def _wait_released(job):
        # Never wait while holding the service lock or a repository transaction.
        if not job.released.wait(5):
            raise ConnectError('generation_timeout')

    def receive(self, raw, channel, deliver):
        """C3 alone supplies channel. Serialize result transmission with authority writes.

        The short bounded framed write stays inside the repository transaction:
        permission removal cannot commit ahead of an already-authorized delta.
        """
        req = None
        try:
            req = InferenceRequest.decode(raw)
            while True:
                with self.lock, self.service.repository.transaction(timeout=.25) as db:
                    record, decision = self._authority(db, req, channel, permission=req.operation not in ('status', 'capabilities', 'cancel', 'notes'))
                    now = int(self.service.clock())
                    if req.timestamp > now + 5 or req.expires_at <= now:
                        raise ConnectError('expired_request')
                    result = self._dispatch(db, req, channel, record, decision)
                    job = self.jobs.get((channel.peer, req.job_id))
                    if not (job and result.get('state') in TERMINAL and not job.released.is_set()):
                        deliver(canonical(dict(protocol_version=PROTOCOL, request_id=req.request_id,
                            job_id=req.job_id, result=result, error=None)))
                        return
                # Terminal metadata suppresses output immediately, but is not a
                # completion acknowledgement until stream, lease and task exit.
                self._wait_released(job)
                # Recheck current authority and refresh output under the original
                # transmission transaction after waiting (never reuse old data).
        except ConnectError as error:
            code = str(error)
            code = {'request_denied': 'permission_denied', 'approval_changed_request': 'changed_duplicate',
                    'connection_closed': 'connection_lost'}.get(code, code)
            if code not in ERRORS:
                code = 'invalid_request'
        except Exception:
            code = 'inference_failed'
        # Malformed requests have no safe correlation; close their channel.
        if req is None:
            raise ConnectError(code)
        deliver(canonical(dict(protocol_version=PROTOCOL, request_id=req.request_id,
            job_id=req.job_id, result=None, error=code)))

    def _dispatch(self, db, req, channel, record, decision):
        if req.operation == 'capabilities':
            # Optional read-only C9.3 query. Existing status bytes are unchanged.
            # C3 trust remains mandatory; no model permission or action is granted.
            names = ('sync.tasks', 'sync.calendar', 'sync.reminders', 'sync.chat', 'files.receive', 'files.send')
            metadata = {c['capability']: c for c in self.service.capabilities_from_db(db)}
            supported = {name: (self.service.sync is not None and
                (name != 'sync.chat' or self.service.sync.store.chat is not None))
                if name.startswith('sync.') else self.service.files is not None for name in names}
            permissions = {name: PermissionDecision.DENY.value if not supported[name]
                or metadata.get(name, {}).get('policy_disabled', False)
                else PermissionService.evaluate_device(record['permissions'], name).value for name in names}
            supported['studio'] = self.service.studio is not None
            return dict(connect_version=1, permissions=permissions, supported=supported, studio_scope='workspace')
        if req.operation == 'notes':
            # Optional read-only probe so a phone never sends Notes frames to a
            # desktop that cannot parse them. Trust stays mandatory (C3).
            if self.service.notes is None:
                raise ConnectError('capability_unavailable')
            from ..notes.limits import PROTOCOL as NOTES_PROTOCOL, CAPABILITY as NOTES_CAPABILITY
            metadata = {c['capability']: c for c in self.service.capabilities_from_db(db)}
            allowed = (not metadata.get(NOTES_CAPABILITY, {}).get('policy_disabled', False) and
                PermissionService.evaluate_device(record['permissions'], NOTES_CAPABILITY) == PermissionDecision.ALLOW)
            return dict(notes_protocol=NOTES_PROTOCOL, permission='allow' if allowed else 'deny')
        if req.operation == 'status':
            return dict(presets=self.runtime.availability(), permission=decision.value,
                        busy=self.active is not None or self.runtime.local_busy())
        key = (channel.peer, req.job_id)
        receipt = self.store.get(db, *key)
        job = self.jobs.get(key)
        if req.operation == 'start':
            if receipt and receipt['fingerprint'] != req.fingerprint():
                if job:
                    self._finish(job, 'failed', 'changed_duplicate', db=db)
                    job.events.clear()
                    self._cancel(job)
                raise ConnectError('changed_duplicate')
            if receipt and not job:
                return dict(state=receipt['state'], events=[], error=receipt['error'])
            if job and job.channel is not channel:
                # Old stream never migrates to a new authenticated connection.
                raise ConnectError('connection_lost')
            if job and job.state != 'awaiting_approval':
                self._job_authority(db, job)
                return dict(state=job.state, events=[], error=job.error)
            if job is None:
                # Sequential Chat is limited by available capacity, not a
                # per-minute question quota. C3 retains its per-peer frame
                # budget across reconnects; concurrent jobs remain bounded.
                live = [j for j in self.jobs.values() if j.state not in TERMINAL or not j.released.is_set()]
                if (len(self.jobs) >= 32 or any(j.peer == channel.peer for j in live)
                        or sum(j.state == 'awaiting_approval' for j in live) >= self.APPROVALS):
                    raise ConnectError('busy')
                if not self.runtime.availability()[req.arguments['preset']]:
                    raise ConnectError('model_unavailable')
                self.store.claim(db, req, input_size(req.arguments['messages']), int(self.service.clock()))
                job = Job(req, channel, record['permissions'], self.clock(), last_poll=self.clock())
                self.jobs[key] = job
                self._audit(db, job, 'requested')
            job.last_poll = self.clock()
            try:
                self._job_authority(db, job)
            except ConnectError as error:
                if str(error) == 'confirmation_required':
                    return dict(state='awaiting_approval', events=[], error=None)
                self._finish(job, 'failed', 'permission_denied', db=db)
                raise
            queued = sum(j.state == 'queued' for j in self.jobs.values())
            if queued >= self.QUEUED:
                self._finish(job, 'failed', 'busy', db=db)
                raise ConnectError('busy')
            self._audit(db, job, 'approved')
            job.state = 'queued'
            job.queued_at = self.clock()
            job.released.clear()
            self.owners[key] = job
            job.future = asyncio.run_coroutine_threadsafe(self._run(job), self.loop)
            return dict(state=job.state, events=[], error=None)
        if not receipt:
            raise ConnectError('unknown_request')
        if job is None:
            return dict(state=receipt['state'], events=[], error=receipt['error'])
        if job.channel is not channel:
            raise ConnectError('connection_lost')
        if req.operation == 'cancel':
            self._finish(job, 'cancelled', 'cancelled', db=db)
            job.events.clear()
            self._cancel(job)
            return dict(state=job.state, events=[], error=job.error)
        self._job_authority(db, job)
        after = req.arguments['after']
        if after < job.acknowledged or after > job.sequence:
            raise ConnectError('stream_invalid')
        job.acknowledged = after
        while job.events and job.events[0]['sequence'] <= after:
            job.events.popleft()
        job.last_poll = self.clock()
        return dict(state=job.state, events=list(job.events), error=job.error)

    def _admit(self, job):
        with self.lock, self.service.repository.transaction(timeout=.25) as db:
            receipt = self.store.get(db, job.peer, job.request.job_id)
            if not receipt or receipt['fingerprint'] != job.request.fingerprint():
                raise ConnectError('request_indeterminate')
            if job.state in TERMINAL:
                raise ConnectError(job.error or 'cancelled')
            self._job_authority(db, job)
            if self.service.clock() >= job.request.expires_at:
                raise ConnectError('expired_request')
            if self.clock() - job.queued_at >= self.QUEUE_SECONDS:
                raise ConnectError('busy')
            if self.active is not None or self.runtime.local_busy():
                return False
            self.active = job
            job.state = 'starting'
            self._audit(db, job, 'started')
            return True

    def _offer(self, job, text):
        with self.lock, self.service.repository.transaction(timeout=.25) as db:
            if job.state in TERMINAL:
                raise ConnectError(job.error or 'cancelled')
            self._job_authority(db, job)
            if len(job.events) < 8:
                job.sequence += 1
                job.events.append(dict(sequence=job.sequence, text=text))
                job.state = 'streaming'
                return True
            return False

    async def _emit(self, job, text):
        while not await asyncio.to_thread(self._offer, job, text):
            await asyncio.sleep(.05)  # bounded backpressure; monitor cancels absent readers

    def _end(self, job, state, error=None):
        with self.lock:
            self._finish(job, state, error)

    def _release(self, job):
        with self.lock:
            if self.active is job:
                self.active = None

    def _job_done(self, job, task):
        with self.lock:
            self.owners.pop((job.peer, job.request.job_id), None)
            self.tasks.discard(task)
            if self.active is job:
                # _run's finally normally cleared it; an externally cancelled
                # task (e.g. loop shutdown) must still never leave a released job
                # owning the slot.
                self.active = None
            job.released.set()  # Task done, after stream close and residency release.

    async def _run(self, job):
        task = asyncio.current_task()
        job.task = task
        self.tasks.add(task)
        task.add_done_callback(lambda done: self._job_done(job, done))
        stream = None
        outcome = ('completed', None)
        try:
            while not await asyncio.to_thread(self._admit, job):
                await asyncio.sleep(.05)
            # Deadline covers start, residency wait and generation; provider cancellation
            # closes its HTTP stream and releases the existing shared model lease.
            async with asyncio.timeout(job.request.arguments['seconds']):
                stream = self.runtime.stream(job.request.arguments)
                pending = ''
                last = self.clock()
                first = True
                while True:
                    try:
                        # Same task/context on all supported Python versions;
                        # model-role ContextVar ownership spans generator yields.
                        async with asyncio.timeout(60 if first else 30):
                            text = await anext(stream)
                    except StopAsyncIteration:
                        break
                    first = False
                    if type(text) is not str or len(text) > job.request.arguments['max_output_bytes']:
                        raise ConnectError('output_limit')
                    size = len(text.encode('utf-8'))
                    if job.output_bytes + size > job.request.arguments['max_output_bytes']:
                        raise ConnectError('output_limit')
                    job.output_bytes += size
                    pending += text
                    # Split by characters conservatively: every UTF-8 character <=4 bytes.
                    while len(pending) >= CHUNK_BYTES // 4:
                        await self._emit(job, pending[:CHUNK_BYTES // 4])
                        pending = pending[CHUNK_BYTES // 4:]
                        last = self.clock()
                    if pending and (len(pending) >= 256 or self.clock() - last >= .1):
                        await self._emit(job, pending)
                        pending, last = '', self.clock()
                if pending:
                    await self._emit(job, pending)
                if not job.output_bytes:
                    raise ConnectError('inference_failed')
        except asyncio.CancelledError:
            outcome = ('cancelled', 'cancelled')
        except TimeoutError:
            outcome = ('timed_out', 'generation_timeout')
        except Exception as error:
            code = str(error) if isinstance(error, ConnectError) and str(error) in ERRORS else 'inference_failed'
            outcome = ('failed', code)
        # No await since generation's last one: from here _cancel_task declines,
        # so terminal receipt, provider stream close and slot release all complete
        # before _job_done signals `released` (Stop/shutdown acknowledgement).
        job.closing = True
        try:
            await asyncio.to_thread(self._end, job, *outcome)
        finally:
            try:
                if stream:
                    await stream.aclose()
            finally:
                await asyncio.to_thread(self._release, job)

    async def _monitor(self):
        task = self.monitor_task = asyncio.current_task()
        try:
            while self.enabled:
                await asyncio.sleep(.1)
                await asyncio.to_thread(self._sweep)
        finally:
            if self.monitor_task is task:
                self.monitor_task = None

    def _sweep(self):
        with self.lock:
            now = self.clock()
            for key, job in list(self.jobs.items()):
                if job.state in TERMINAL:
                    if now - job.ended >= self.RETENTION and job.released.is_set():
                        del self.jobs[key]
                    continue
                reason = None
                if job.channel.stop.is_set():
                    reason = 'connection_lost'
                elif now - job.last_poll > self.INACTIVITY:
                    reason = 'connection_lost'
                elif job.state == 'awaiting_approval' and (now - job.born >= 120 or self.service.clock() >= job.request.expires_at):
                    reason = 'generation_timeout'
                else:
                    try:
                        with self.service.repository.transaction(timeout=.25) as db:
                            self._authority(db, job.request, job.channel)
                            record = self.service.repository.get(db, job.peer)
                            if record['permissions'] != job.rules:
                                reason = 'permission_denied'
                    except Exception:
                        reason = 'permission_denied'
                if reason:
                    self._finish(job, 'connection_lost' if reason == 'connection_lost' else 'failed', reason)
                    job.events.clear()
                    self._cancel(job)

    def stop(self, peer, job_id):
        with self.lock:
            job = self.jobs.get((peer, job_id))
            if job:
                self._finish(job, 'cancelled', 'cancelled')
                job.events.clear()
                self._cancel(job)
        if job:
            self._wait_released(job)

    def invalidate(self, peer=None, reason='permission_denied', channel=None):
        with self.lock:
            for job in self.jobs.values():
                if (peer is None or job.peer == peer) and (channel is None or job.channel is channel):
                    if job.state not in TERMINAL:
                        state = 'revoked' if reason == 'device_revoked' else 'connection_lost' if reason == 'connection_lost' else 'cancelled'
                        self._finish(job, state, reason)
                    job.events.clear()
                    self._cancel(job)

    def snapshot(self, peer):
        with self.lock:
            return dict(presets=self.runtime.availability(), jobs=[dict(job_id=j.request.job_id,
                preset=j.request.arguments['preset'], state=j.state) for j in self.jobs.values()
                if j.peer == peer and j.state not in TERMINAL], recent=self.store.recent(peer))

    def close(self):
        self.enabled = False
        self.invalidate(reason='cancelled')
        with self.lock:
            self.jobs.clear()
        if self.monitor:
            self.monitor.cancel()

    async def shutdown(self):
        await asyncio.to_thread(self.close)
        with self.lock:
            owners = list(self.owners.values())
        # Same acknowledgement as requester/target Stop, including scheduled
        # tasks not yet registered in self.tasks. Timeout never recancels cleanup.
        await asyncio.gather(*(asyncio.to_thread(self._wait_released, job) for job in owners))
        if self.monitor_task is not None:
            await asyncio.wait_for(asyncio.shield(asyncio.gather(self.monitor_task, return_exceptions=True)), 5)
        if self.active is not None:
            raise TimeoutError('remote_inference_shutdown_timeout')
