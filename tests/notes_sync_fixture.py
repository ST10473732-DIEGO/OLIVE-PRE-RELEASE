"""Deterministic simulated OLIVE Connect for Notes sync tests.

Each SimDevice is a real NotesService (its own SQLite file) plus a real
NotesSyncEngine. SimNetwork carries real olive-notes/1 bytes between them and
can take links offline, drop requests or responses, duplicate, hold and reorder
deliveries, and restart devices. Authorization mirrors Connect: a device only
answers peers it has explicitly allowed.
"""
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from olive.notes import protocol
from olive.notes.service import NotesService
from olive.notes.sync_engine import NotesSyncEngine, NotesSyncError


class SimDevice:
    def __init__(self, root, name):
        self.name = name
        self.id = str(uuid.uuid4())
        self.path = Path(root) / name / 'notes.sqlite3'
        self.allowed = set()
        self.events = []
        self._start()

    def _start(self):
        self.service = NotesService(self.path, device_id=self.id, timers=False,
                                    publish=lambda topic, data: self.events.append((topic, data)))
        self.engine = NotesSyncEngine(self.service, self.id)

    def restart(self):
        """Clean restart: transient engine state (cached vectors, transfers) is lost."""
        self.service.close()
        self._start()

    def crash(self):
        """Hard stop without flushing search/history/events (durable data only)."""
        self.service.worker.stop()
        self._start()

    def run(self, name, *args, **kwargs):
        return self.service.run(getattr(self.service, name), *args, **kwargs)

    def text(self, note_id):
        return self.run('read_text', note_id)['text']

    def notes(self, view='notes'):
        return self.run('list_notes', view)['notes']

    def close(self):
        self.service.close()


class SimNetwork:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='olive-notes-sim-')
        self.devices = []
        self.offline = set()
        self.faults = []            # queued callables: fault(kind) -> action
        self.held = []              # (receiver, sender_id, raw) captured for reordering
        self.hold = False
        self.latencies = []

    def device(self, name):
        device = SimDevice(self.root, name)
        self.devices.append(device)
        return device

    def pair(self, a, b):
        a.allowed.add(b.id)
        b.allowed.add(a.id)

    def disconnect(self, a, b):
        self.offline.add(frozenset((a.id, b.id)))

    def reconnect(self, a, b):
        self.offline.discard(frozenset((a.id, b.id)))

    def online(self, a, b):
        return frozenset((a.id, b.id)) not in self.offline

    def fault(self, kind, count=1):
        self.faults.extend([kind] * count)

    def _take(self, kind):
        if self.faults and self.faults[0] == kind:
            self.faults.pop(0)
            return True
        return False

    def deliver(self, receiver, sender_id, raw):
        """The receiving side of Connect: authorize, validate, handle, respond."""
        try:
            request = protocol.decode_request(raw)
        except protocol.NotesProtocolError as failure:
            return protocol.encode_response(None, error=str(failure))
        try:
            if request['source_device_id'] != sender_id:
                raise protocol.NotesProtocolError('source_mismatch')
            if request['target_device_id'] != receiver.id:
                raise protocol.NotesProtocolError('wrong_target')
            if sender_id not in receiver.allowed:
                raise protocol.NotesProtocolError('permission_off')
            protocol.check_fresh(request, int(time.time()))
            result = receiver.service.run(receiver.engine.handle, sender_id, request)
            return protocol.encode_response(request['request_id'], result=result)
        except protocol.NotesProtocolError as failure:
            return protocol.encode_response(request['request_id'], error=str(failure))

    def sender(self, a, b):
        def send(operation, arguments):
            if not self.online(a, b):
                raise NotesSyncError('device_offline')
            raw = protocol.encode_request(str(uuid.uuid4()), a.id, b.id, operation, arguments, int(time.time()))
            if self._take('drop_request'):
                raise NotesSyncError('connection_lost')
            if self.hold:
                self.held.append((b, a.id, raw))
                raise NotesSyncError('connection_lost')
            started = time.perf_counter()
            response = self.deliver(b, a.id, raw)
            self.latencies.append(time.perf_counter() - started)
            if self._take('duplicate'):
                response = self.deliver(b, a.id, raw)
            if self._take('drop_response'):
                raise NotesSyncError('connection_lost')
            value = protocol.decode_response(response)
            if value['state'] != 'completed':
                raise NotesSyncError(value['error'])
            return value['result']
        return send

    def release(self, order=None):
        """Deliver held requests (optionally reordered); their answers are lost."""
        held, self.held = self.held, []
        for index in (order or range(len(held))):
            receiver, sender_id, raw = held[index]
            self.deliver(receiver, sender_id, raw)

    def sync(self, a, b, *, hello=False):
        return a.engine.pump(b.id, self.sender(a, b), hello=hello)

    def connect(self, a, b):
        """What Connect does when a channel becomes ready: hello + pump both ways."""
        self.sync(a, b, hello=True)
        self.sync(b, a, hello=True)

    def settle(self, devices=None, rounds=8):
        """Pump every online pair until nobody has pending changes."""
        devices = devices or self.devices
        for _ in range(rounds):
            busy = False
            for a in devices:
                for b in devices:
                    if a is b or b.id not in a.allowed or not self.online(a, b):
                        continue
                    if a.engine.pending(b.id):
                        busy = True
                        self.sync(a, b)
            if not busy:
                return True
        return False

    def close(self):
        for device in self.devices:
            try:
                device.close()
            except Exception:
                pass
        shutil.rmtree(self.root, ignore_errors=True)
