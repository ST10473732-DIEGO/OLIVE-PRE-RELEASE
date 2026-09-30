"""Remote Chat v2 owner: every OLIVE Chat mode for a paired phone, content only.

Separate from TLS, trust, permission and model authority. The peer comes from
the authenticated channel, never from the message. Requests reuse the Remote AI
(``models.remote``) permission and its Ask approvals; nothing here reaches the
tool registry, the natural-language orchestrator, Memory, desktop control,
terminals or arbitrary files. Attachments are untrusted content, staged in an
OLIVE-owned area and consumed only by the mode that the phone asked for.

Unlike v1 (olive-inference/1), a job is not bound to the channel that started
it: it keeps running across a Wi-Fi drop, and its outcome (text, structured
sources, media artifact descriptors) is a durable receipt that any later
authenticated channel from the same phone may read by job id.
"""
import asyncio
import re
import time
from dataclasses import dataclass, field
from threading import Event, RLock

from ..agent.permission_service import PermissionDecision, PermissionService
from .chat_protocol import (CAPABILITY, CHUNK_BYTES, ERRORS, MAX_OUTPUT, MAX_TEXT_DELTA, PHASES, PROTOCOL,
                            TERMINAL, ChatRequest, attachment_ref, artifact_item, attribution, response,
                            source_item, unpack)
from .chat_store import AttachmentStaging, ChatStore
from .contracts import ConnectError, identifier

TIMEOUTS = {'fast': 240, 'normal': 240, 'max': 300, 'uncensored': 300, 'now': 300, 'deep': 480,
            'reimagine': 660, 'audio': 360, 'video': 1260}


@dataclass
class Job:
    peer: str
    job_id: str
    conversation: str
    mode: str
    arguments: dict
    fingerprint: str
    channel: object
    rules: list
    born: float
    inputs: list = field(default_factory=list)
    state: str = 'awaiting_approval'
    phase: str = 'approval'
    error: str | None = None
    text: str = ''
    text_bytes: int = 0
    sources: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    attribution: dict = field(default_factory=dict)
    future: object = None
    task: object = None
    cancel: object = None  # asyncio.Event on the model loop, created when scheduled.
    cancel_requested: bool = False
    released: Event = field(default_factory=Event)
    last_poll: float = 0
    ended: float = 0

    def __post_init__(self):
        self.released.set()


class Sink:
    """What a running mode may report. Everything is bounded and validated here."""

    def __init__(self, owner, job):
        self.owner, self.job = owner, job

    @property
    def cancelled(self):
        return self.job.cancel

    def phase(self, code):
        if code in PHASES:
            with self.owner.lock:
                if self.job.state not in TERMINAL:
                    self.job.phase = code

    def text(self, delta):
        if type(delta) is not str or not delta:
            return
        size = len(delta.encode('utf-8'))
        with self.owner.lock:
            if self.job.state in TERMINAL:
                raise asyncio.CancelledError()
            if self.job.text_bytes + size > MAX_OUTPUT:
                raise ConnectError('output_limit')
            self.job.text += delta
            self.job.text_bytes += size
            self.job.phase = ''

    def sources(self, values):
        items = [source_item(v) for v in list(values)[:12] if type(v) is dict]
        with self.owner.lock:
            if self.job.state not in TERMINAL:
                self.job.sources = items

    def attribute(self, tier=''):
        with self.owner.lock:
            self.job.attribution = attribution(self.job.mode, tier)

    def artifact(self, artifact):
        item = artifact_item(artifact, self.job.mode)
        with self.owner.lock:
            # Stop wins: a result that arrives after cancellation never attaches.
            if self.job.state in TERMINAL or self.job.cancel_requested:
                raise asyncio.CancelledError()
            self.job.artifacts = (self.job.artifacts + [item])[-4:]


class RemoteChatService:
    RETENTION = 600
    APPROVAL_SECONDS = 120

    def __init__(self, service, runtime, loop, staging_root, *, clock=time.monotonic):
        self.service, self.runtime, self.loop, self.clock = service, runtime, loop, clock
        self.lock = RLock()
        self.store = ChatStore(service.repository)
        self.staging = AttachmentStaging(staging_root, clock=service.clock)
        self.jobs = {}
        self.enabled = False
        self.monitor = None
        self.last_collect = 0.0

    # ------------------------------------------------------------ lifecycle
    def activate(self):
        with self.lock:
            self.enabled = True
            if self.monitor is None or self.monitor.done():
                self.monitor = asyncio.run_coroutine_threadsafe(self._monitor(), self.loop)

    def close(self):
        """Network off or OLIVE closing: live work stops (not a user Stop); receipts stay."""
        self.enabled = False
        self.invalidate(reason='computer_stopped')
        if self.monitor:
            self.monitor.cancel()

    async def shutdown(self):
        await asyncio.to_thread(self.close)
        with self.lock:
            live = [job for job in self.jobs.values() if not job.released.is_set()]
        await asyncio.gather(*(asyncio.to_thread(job.released.wait, 10) for job in live))

    def invalidate(self, peer=None, reason='permission_denied'):
        with self.lock:
            for job in list(self.jobs.values()):
                if peer is None or job.peer == peer:
                    if job.state not in TERMINAL:
                        self._finish(job, 'cancelled' if reason == 'cancelled' else 'failed', reason)
                    self._cancel(job)

    def forget_peer(self, peer):
        """Device removed: drop its staged inputs and remote document indexes."""
        self.invalidate(peer, 'device_revoked')
        self.staging.forget(peer)
        try:
            with self.service.repository.transaction() as db:
                rows = self.store.forget_peer(db, peer)
            forget = getattr(self.runtime, 'forget_conversations', None)
            if forget:
                forget([state for _, state in rows])
        except Exception:
            pass

    # ------------------------------------------------------------ authority
    def _authority(self, db, req, channel, *, permission=True):
        channel.check()
        record = self.service.repository.get(db, channel.peer)
        if (not self.enabled or self.service.closed or req.source_device_id != channel.peer
                or req.target_device_id != self.service.local_id):
            raise ConnectError('device_unavailable')
        if not record or record['trust_state'] != 'paired' or record.get('public_identity') != channel.public:
            raise ConnectError('device_revoked')
        metadata = next((c for c in self.service.capabilities_from_db(db) if c['capability'] == CAPABILITY), None)
        decision = PermissionService.evaluate_device(record['permissions'], CAPABILITY)
        if metadata is None or metadata['policy_disabled']:
            decision = PermissionDecision.DENY
        if permission and decision == PermissionDecision.DENY:
            raise ConnectError('permission_denied')
        now = int(self.service.clock())
        if req.timestamp > now + 5 or req.expires_at <= now:
            raise ConnectError('expired_request')
        return record, decision

    # ------------------------------------------------------------ entry
    def receive(self, raw, channel, deliver):
        """C3 supplies channel. Malformed, uncorrelated input closes the channel."""
        req = None
        try:
            try:
                req = ChatRequest.decode(raw)
            except ConnectError as error:
                rid = self._correlation(raw)
                if rid is None:
                    raise
                deliver(response(rid, error=str(error) if str(error) in ERRORS else 'invalid_request'))
                return
            result, binary = self._dispatch(req, channel)
            deliver(response(req.request_id, result=result, binary=binary))
            return
        except ConnectError as error:
            code = {'request_denied': 'permission_denied', 'approval_changed_request': 'changed_duplicate',
                    'connection_closed': 'device_unavailable', 'approval_capacity_reached': 'busy'}.get(str(error), str(error))
            if code not in ERRORS:
                code = 'invalid_request'
        except Exception:
            code = 'inference_failed'
        if req is None:
            raise ConnectError(code)
        deliver(response(req.request_id, error=code))

    @staticmethod
    def _correlation(raw):
        try:
            value, _ = unpack(raw)
            if type(value) is dict and value.get('protocol_version') == PROTOCOL:
                return identifier(value.get('request_id'))
        except ConnectError:
            pass
        return None

    def _dispatch(self, req, channel):
        op, a = req.operation, req.arguments
        if op == 'capabilities':
            with self.service.repository.transaction(timeout=.25, read_only=True) as db:
                _, decision = self._authority(db, req, channel, permission=False)
            modes = self.runtime.capabilities()
            return dict(chat_protocol=PROTOCOL, permission=decision.value, modes=modes,
                        limits=dict(chunk_bytes=CHUNK_BYTES, max_attachments=4, max_output_bytes=MAX_OUTPUT)), b''
        if op == 'attachment_offer':
            with self.service.repository.transaction(timeout=.25, read_only=True) as db:
                self._authority(db, req, channel)
            state, received = self.staging.offer(channel.peer, attachment_ref(dict(a)))
            return dict(attachment_id=a['attachment_id'], state=state, received=received), b''
        if op == 'attachment_chunk':
            with self.service.repository.transaction(timeout=.25, read_only=True) as db:
                self._authority(db, req, channel)
            state, received = self.staging.chunk(channel.peer, a['attachment_id'], a['offset'], req.binary)
            return dict(attachment_id=a['attachment_id'], state=state, received=received), b''
        if op == 'artifact_chunk':
            return self._artifact_chunk(req, channel)
        with self.lock, self.service.repository.transaction(timeout=.25) as db:
            record, decision = self._authority(db, req, channel, permission=op != 'cancel')
            if op == 'start':
                return self._start(db, req, channel, record, decision), b''
            if op == 'poll':
                return self._poll(db, channel.peer, a['job_id'], a['after']), b''
            return self._cancel_request(db, channel.peer, a['job_id']), b''

    # ------------------------------------------------------------ start / poll / cancel
    def _start(self, db, req, channel, record, decision):
        a = req.arguments
        peer, job_id = channel.peer, a['job_id']
        receipt = self.store.get(db, peer, job_id)
        job = self.jobs.get((peer, job_id))
        if receipt and receipt['fingerprint'] != req.fingerprint():
            if receipt['fingerprint'] == '':
                return self._view(receipt, 0, job_id)  # Stopped before this start arrived.
            raise ConnectError('changed_duplicate')
        if receipt and (job is None or job.state != 'awaiting_approval'):
            # A resend after a lost acknowledgement never starts the work twice.
            return self._view(job or receipt, 0, job_id)
        if job is None:
            live = [j for j in self.jobs.values() if j.peer == peer and j.state not in TERMINAL]
            if live:
                raise ConnectError('busy')
            # Validate everything that can be validated before any receipt exists,
            # so a corrected request may be retried with the same job id.
            refs = [attachment_ref(dict(r)) for r in a['attachments']]
            self.runtime.validate(a['mode'], refs, a['messages'])
            inputs = []
            for ref in refs:
                path = self.staging.present(peer, ref)
                if path is None:
                    raise ConnectError('attachment_missing')
                inputs.append(dict(ref=ref, path=path))
            self.store.claim(db, peer, job_id, req.fingerprint(), a['conversation_id'], a['mode'],
                             'awaiting_approval', int(self.service.clock()))
            job = Job(peer, job_id, a['conversation_id'], a['mode'], a, req.fingerprint(), channel,
                      record['permissions'], self.clock(), inputs=inputs, last_poll=self.clock())
            self.jobs[(peer, job_id)] = job
            self._audit(db, job, 'requested')
        job.last_poll = self.clock()
        job.channel = channel
        if decision == PermissionDecision.ASK:
            approvals = self.service.approvals
            try:
                approved = approvals is not None and approvals.check(req, channel.public, record,
                    target_name=self.service.repository.get(db, self.service.local_id)['display_name'])
            except ConnectError:
                self._finish(job, 'failed', 'permission_denied', db=db)
                raise ConnectError('permission_denied') from None
            if not approved:
                return self._view(job, 0, job_id)
        self._audit(db, job, 'approved')
        job.state, job.phase = 'queued', 'queued'
        job.released.clear()
        job.future = asyncio.run_coroutine_threadsafe(self._run(job), self.loop)
        return self._view(job, 0, job_id)

    def _poll(self, db, peer, job_id, after):
        job = self.jobs.get((peer, job_id))
        if job is not None:
            job.last_poll = self.clock()
            return self._view(job, after, job_id)
        receipt = self.store.get(db, peer, job_id)
        if receipt is None:
            return self._view(None, after, job_id)
        return self._view(receipt, after, job_id)

    def _cancel_request(self, db, peer, job_id):
        job = self.jobs.get((peer, job_id))
        if job is not None:
            if job.state not in TERMINAL:
                self._finish(job, 'cancelled', 'cancelled', db=db)
                self._cancel(job)
            return self._view(job, 0, job_id, text=False)
        receipt = self.store.get(db, peer, job_id)
        if receipt is None:
            # Stop may overtake its own start. Leave a tombstone so a late
            # duplicate start is answered "cancelled" and never runs.
            self.store.claim(db, peer, job_id, '', job_id, 'fast', 'cancelled', int(self.service.clock()))
            self.store.update(db, peer, job_id, state='cancelled', error='cancelled', now=int(self.service.clock()))
            receipt = self.store.get(db, peer, job_id)
        return self._view(receipt, 0, job_id, text=False)

    def _view(self, value, after, job_id, *, text=True):
        if value is None:
            return dict(job_id=job_id, state='not_received', phase='', text='', offset=after, total=0,
                        sources=[], artifacts=[], attribution={}, error=None)
        if isinstance(value, Job):
            state, phase, error, full = value.state, value.phase, value.error, value.text
            sources, artifacts, attrib = value.sources, value.artifacts, value.attribution
        else:
            state, phase, error, full = value['state'], '', value['error'], value['text']
            sources, artifacts, attrib = value['sources'], value['artifacts'], value['attribution']
        encoded = full.encode('utf-8')
        if after > len(encoded) or (after < len(encoded) and (encoded[after] & 0xC0) == 0x80):
            raise ConnectError('invalid_request')
        cut = min(len(encoded), after + MAX_TEXT_DELTA)
        while cut > after and cut < len(encoded) and (encoded[cut] & 0xC0) == 0x80:
            cut -= 1
        delta = encoded[after:cut].decode('utf-8') if text else ''
        return dict(job_id=job_id, state=state, phase=phase if state not in TERMINAL else '',
                    text=delta, offset=after, total=len(encoded), sources=list(sources), artifacts=list(artifacts),
                    attribution=dict(attrib) if attrib else {}, error=error if error in ERRORS else (None if error is None else 'inference_failed'))

    def _artifact_chunk(self, req, channel):
        a = req.arguments
        with self.service.repository.transaction(timeout=.25, read_only=True) as db:
            self._authority(db, req, channel)
            if not self.store.artifact_owned(db, channel.peer, a['artifact_id']):
                raise ConnectError('artifact_unavailable')
        info = self.runtime.artifact_file(a['artifact_id'])
        size = info['size']
        if a['offset'] >= size:
            raise ConnectError('invalid_request')
        with open(info['path'], 'rb') as stream:
            stream.seek(a['offset'])
            data = stream.read(min(a['length'], CHUNK_BYTES, size - a['offset']))
        # Authority is rechecked immediately before bytes leave this computer.
        with self.service.repository.transaction(timeout=.25, read_only=True) as db:
            self._authority(db, req, channel)
        return dict(artifact_id=a['artifact_id'], offset=a['offset'], size=size, sha256=info['sha256']), data

    # ------------------------------------------------------------ job ownership
    def _audit(self, db, job, state):
        self.service.repository.audit(db, job.peer, job.job_id, CAPABILITY, int(self.service.clock()),
                                      'remote_chat_' + state)

    def _finish(self, job, state, error=None, *, db=None):
        if job.state in TERMINAL:
            return
        job.state, job.error, job.ended, job.phase = state, error, self.clock(), ''
        values = dict(state=state, error=error, text=job.text if state == 'completed' else job.text,
                      sources=job.sources, artifacts=job.artifacts if state == 'completed' else [],
                      attribution=job.attribution, now=int(self.service.clock()))
        if state != 'completed':
            job.artifacts = []
        try:
            if db is None:
                with self.service.repository.transaction(timeout=2) as transaction:
                    self.store.update(transaction, job.peer, job.job_id, **values)
                    self._audit(transaction, job, state)
            else:
                self.store.update(db, job.peer, job.job_id, **values)
                self._audit(db, job, state)
        except Exception:
            pass  # The claim already prevents replay; memory still answers polls.
        if self.service.approvals:
            self.service.approvals.discard(job.peer, job.job_id)

    def _cancel(self, job):
        if job.future is not None and not job.cancel_requested and not job.released.is_set():
            job.cancel_requested = True
            self.loop.call_soon_threadsafe(self._cancel_task, job)

    @staticmethod
    def _cancel_task(job):
        if job.cancel is not None:
            job.cancel.set()
        if job.task is not None and not job.task.done() and not job.task.cancelling():
            job.task.cancel()

    def _admit(self, job):
        with self.lock, self.service.repository.transaction(timeout=2, read_only=True) as db:
            if job.state in TERMINAL:
                raise ConnectError(job.error or 'cancelled')
            record = self.service.repository.get(db, job.peer)
            if not record or record['trust_state'] != 'paired' or record['permissions'] != job.rules:
                raise ConnectError('permission_denied')
            job.state, job.phase = 'running', 'thinking'

    def _end(self, job, state, error=None):
        with self.lock:
            self._finish(job, state, error)

    async def _run(self, job):
        task = asyncio.current_task()
        job.task = task
        job.cancel = asyncio.Event()
        if job.cancel_requested:
            job.cancel.set()
        try:
            await asyncio.to_thread(self._admit, job)
            async with asyncio.timeout(TIMEOUTS[job.mode]):
                await self.runtime.run(job, Sink(self, job))
            if not job.text.strip() and not job.artifacts:
                raise ConnectError('inference_failed')
            await asyncio.to_thread(self._end, job, 'completed')
        except asyncio.CancelledError:
            await asyncio.to_thread(self._end, job, 'cancelled', 'cancelled')
        except TimeoutError:
            await asyncio.to_thread(self._end, job, 'failed', 'generation_timeout')
        except Exception as error:
            await asyncio.to_thread(self._end, job, 'failed', public_error(error))
        finally:
            job.released.set()

    async def _monitor(self):
        try:
            while self.enabled:
                await asyncio.sleep(1)
                await asyncio.to_thread(self._sweep)
        except asyncio.CancelledError:
            pass

    def _sweep(self):
        now = self.clock()
        with self.lock:
            for key, job in list(self.jobs.items()):
                if job.state in TERMINAL:
                    if now - job.ended >= self.RETENTION and job.released.is_set():
                        del self.jobs[key]
                elif job.state == 'awaiting_approval' and now - job.last_poll >= self.APPROVAL_SECONDS:
                    self._finish(job, 'failed', 'confirmation_required')
        if now - self.last_collect >= 3600:
            self.last_collect = now
            try:
                self.staging.collect()
                collect = getattr(self.runtime, 'collect', None)
                if collect:
                    collect(self)
            except Exception:
                pass

    def snapshot(self, peer):
        with self.lock:
            return [dict(job_id=j.job_id, mode=j.mode, state=j.state) for j in self.jobs.values()
                    if j.peer == peer and j.state not in TERMINAL]


def public_error(error):
    """Fixed public codes only; never exception text, paths or provider detail."""
    code = getattr(error, 'code', None)
    if type(code) is str and code in ERRORS:
        return code
    if isinstance(error, ConnectError) and str(error) in ERRORS:
        return str(error)
    text = str(error)
    if re.search(r'Insufficient context', text):
        return 'input_too_large'
    if re.search(r'indexing|No readable|readable indexed', text, re.I):
        return 'document_unreadable'
    if re.search(r'vision', text, re.I):
        return 'vision_unavailable'
    return 'inference_failed'
