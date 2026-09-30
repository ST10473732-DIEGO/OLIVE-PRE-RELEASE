"""Exact-request adapter to OLIVE's existing trusted local confirmation service.

A remote caller receives confirmation_required promptly and may retry the same
strict envelope. No wire token, approval flag or permission mutation exists.
"""
import asyncio
from threading import RLock
import time

from ..agent.confirmation_service import ConfirmationRequest
from .contracts import ConnectError
from .identity import fingerprint

LABELS = {**{'studio.' + action: 'Remote Studio: ' + action for action in ('view', 'edit', 'build', 'test', 'run', 'debug')}, 'files.receive': 'Receive an untrusted file into OLIVE Inbox',
          'models.remote': 'Remote AI: tool-free text inference',
          'files.send': 'Send this selected file to the paired device', 'connect.ping': 'Connect ping', 'device.status': 'Device status',
          'chat.metadata.read': 'Chat availability metadata',
          'sync.tasks': 'Tasks: send and receive up to 8 records in this exact exchange',
          'sync.calendar': 'Calendar: send and receive up to 8 records in this exact exchange',
          'sync.chat': 'Selected chats: send and receive up to 8 records in this exact exchange',
          'sync.reminders': 'Reminders: send and receive up to 8 records in this exact exchange'}


class ConnectApprovals:
    def __init__(self, service, confirm, loop):
        self.service, self.confirm, self.loop = service, confirm, loop
        self.lock = RLock()
        self.entries = {}
        self.closed = False

    def check(self, request, public, record, *, target_name):
        key = (request.source_device_id, request.request_id)
        binding = (request.fingerprint(), fingerprint(public), record['revision'])
        with self.lock:
            if self.closed:
                return False
            now = time.monotonic()
            for old, value in list(self.entries.items()):
                if now >= value['deadline']:
                    value['future'].cancel()
                    del self.entries[old]
            entry = self.entries.get(key)
            if entry:
                if entry['binding'] != binding:
                    entry['future'].cancel()
                    entry['state'] = 'invalid'
                    raise ConnectError('approval_changed_request')
                if entry['state'] in {'denied', 'invalid'}:
                    raise ConnectError('request_denied')
                return entry['state'] == 'approved'
            if len(self.entries) >= 32:
                raise ConnectError('approval_capacity_reached')
            deadline = now + min(120, request.expires_at - self.service.clock())
            chat = getattr(request, 'protocol_version', '') == 'olive-chat/1'
            summary = ('Remote AI: OLIVE ' + request.arguments['mode'].upper() + ' on this computer (no tools)'
                       if chat else LABELS[request.capability])
            prompt = ConfirmationRequest(task_id=request.request_id, tool_name='connect.request',
                summary=summary, risk_level='medium' if request.capability.startswith(('sync.', 'files.', 'studio.')) else 'low',
                targets=[record['display_name']], allow_remember=False,
                arguments=dict(source_device_id=record['device_id'],
                    public_fingerprint=binding[1], request_id=request.request_id,
                    capability=request.capability, operation=request.operation,
                    envelope_fingerprint=binding[0], revision=record['revision'],
                    source_name=record['display_name'], target_name=target_name,
                    **({'studio': dict(workspace_id=request.workspace_id, operation=request.operation,
                        path=request.arguments.get('path', ''), share_revision=request.share_revision,
                        expected_hash=request.arguments.get('expected_hash', ''))} if request.capability.startswith('studio.') else {}),
                    **({'file': dict(request.arguments)} if request.capability.startswith('files.') else {}),
                    **({'chat': dict(mode=request.arguments['mode'],
                        message_count=len(request.arguments['messages']),
                        input_bytes=sum(len(m['content'].encode('utf-8')) for m in request.arguments['messages']),
                        attachments=len(request.arguments['attachments']),
                        attachment_bytes=sum(a['size'] for a in request.arguments['attachments']),
                        expires_at=request.expires_at)} if chat else {}),
                    **({'inference': dict(preset=request.arguments['preset'],
                        message_count=len(request.arguments['messages']),
                        input_bytes=sum(len(m['content'].encode('utf-8')) for m in request.arguments['messages']),
                        max_tokens=request.arguments['max_tokens'], expires_at=request.expires_at)}
                       if request.capability == 'models.remote' and not chat else {})))
            entry = dict(binding=binding, deadline=deadline, state='pending', future=None)
            self.entries[key] = entry
            entry['future'] = asyncio.run_coroutine_threadsafe(self._ask(key, entry, prompt), self.loop)
            return False

    async def _ask(self, key, entry, prompt):
        try:
            response = await asyncio.wait_for(self.confirm(prompt), max(.01, entry['deadline'] - time.monotonic()))
            with self.lock:
                if self.closed or entry['state'] != 'pending':
                    return
                entry['state'] = 'approved' if response.approved else 'denied'
            with self.service.repository.transaction() as db:
                self.service.repository.audit(db, key[0], key[1], prompt.arguments['capability'],
                    int(self.service.clock()), 'request_approved' if response.approved else 'request_denied')
        except (TimeoutError, asyncio.CancelledError):
            with self.lock:
                entry['state'] = 'denied'

    def completed(self, request, record):
        with self.lock:
            entry = self.entries.get((request.source_device_id, request.request_id))
            if entry and entry['state'] == 'approved':
                entry['binding'] = (*entry['binding'][:2], record['revision'])

    def discard(self, source, request_id):
        """End one local prompt without invalidating unrelated peer requests."""
        with self.lock:
            entry = self.entries.pop((source, request_id), None)
            if entry:
                entry['state'] = 'invalid'
                entry['future'].cancel()

    def invalidate(self, peer=None):
        with self.lock:
            for key, entry in self.entries.items():
                if peer is None or key[0] == peer:
                    entry['state'] = 'invalid'
                    entry['future'].cancel()

    def close(self):
        with self.lock:
            self.closed = True
            self.invalidate()
            self.entries.clear()
