"""Deterministic simulated OLIVE Connect for Draw sync tests.

Each SimDrawDevice is a real DrawService (its own SQLite file) plus a real
DrawSyncEngine. SimDrawNetwork carries real olive-draw/1 bytes between them
and can take links offline, drop requests or answers, duplicate deliveries,
hold and reorder them, and restart devices. Authorization mirrors Connect: a
device only answers peers it explicitly allows (``sync.draw`` Allow).
"""
import hashlib
import io
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from olive.draw import protocol
from olive.draw.service import DrawService
from olive.draw.sync_engine import DrawSyncEngine, DrawSyncError


def stroke(points, *, color='#000000', width=4, opacity=1, pressure=False):
    return {'type': 'stroke', 'id': uuid.uuid4().hex, 'tool': 'pen', 'color': color, 'width': width,
            'opacity': opacity, 'pressure': pressure, 'points': points}


def erase(points, width=20):
    return {'type': 'erase', 'id': uuid.uuid4().hex, 'width': width, 'points': points}


def clear():
    return {'type': 'clear', 'id': uuid.uuid4().hex}


def background(value):
    return {'type': 'background', 'id': uuid.uuid4().hex, 'value': value}


def png(width, height, color=(255, 0, 0, 255), *, transparent_corner=False):
    from PIL import Image
    image = Image.new('RGBA', (width, height), color)
    if transparent_corner:
        for x in range(width // 2):
            for y in range(height // 2):
                image.putpixel((x, y), (0, 0, 0, 0))
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


class SimDrawDevice:
    def __init__(self, root, name):
        self.name = name
        self.id = str(uuid.uuid4())
        self.path = Path(root) / name / 'drawings.sqlite3'
        self.allowed = set()
        self.events = []
        self._start()

    def _start(self):
        self.service = DrawService(self.path, device_id=self.id,
                                   publish=lambda topic, data: self.events.append((topic, data)))
        self.engine = DrawSyncEngine(self.service, self.id)

    def restart(self):
        """Process restart: transient engine state (staged transfers) is lost."""
        self._start()

    # Convenience views ------------------------------------------------------------
    def drawings(self, view='drawings'):
        return self.service.list_drawings(view)['drawings']

    def ops(self, did):
        return self.service.visible_ops(did)

    def state(self, did):
        """Canonical, comparable state of one drawing on this replica."""
        info = self.service.get(did)
        return {'title': info['title'], 'trashed': info['trashed'], 'width': info['width'], 'height': info['height'],
                'background': effective_background(info['background'], self.ops(did)),
                'ops': [op['id'] for op in self.ops(did)]}


def effective_background(initial, ops):
    for op in reversed(ops):
        if op['type'] == 'background':
            return op['value']
    return initial


class SimDrawNetwork:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='olive-draw-sim-')
        self.devices = []
        self.offline = set()
        self.faults = []
        self.held = []
        self.hold = False
        self.messages = []       # (operation, request bytes, response bytes)
        self.block_assets = False   # Asset chunks fail to arrive (receiver keeps a placeholder).
        self.kill_after_chunks = None   # Receiver process dies after N accepted asset chunks.

    def device(self, name):
        device = SimDrawDevice(self.root, name)
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
        except protocol.DrawProtocolError as failure:
            return protocol.encode_response(None, error=str(failure))
        try:
            if request['source_device_id'] != sender_id:
                raise protocol.DrawProtocolError('source_mismatch')
            if request['target_device_id'] != receiver.id:
                raise protocol.DrawProtocolError('wrong_target')
            if sender_id not in receiver.allowed:
                raise protocol.DrawProtocolError('permission_off')
            protocol.check_fresh(request, int(time.time()))
            result = receiver.engine.handle(sender_id, request)
            return protocol.encode_response(request['request_id'], result=result)
        except protocol.DrawProtocolError as failure:
            return protocol.encode_response(request['request_id'], error=str(failure))

    def sender(self, a, b):
        def send(operation, arguments):
            if not self.online(a, b):
                raise DrawSyncError('device_offline')
            raw = protocol.encode_request(str(uuid.uuid4()), a.id, b.id, operation, arguments, int(time.time()))
            if self._take('drop_request'):
                raise DrawSyncError('connection_lost')
            if self.hold:
                self.held.append((b, a.id, raw))
                raise DrawSyncError('connection_lost')
            if operation == 'asset' and self.block_assets:
                raise DrawSyncError('connection_lost')
            if operation == 'asset' and self.kill_after_chunks is not None:
                if self.kill_after_chunks == 0:
                    self.kill_after_chunks = None
                    b.restart()         # Receiver dies mid-transfer: staged chunks are gone.
                    raise DrawSyncError('connection_lost')
                self.kill_after_chunks -= 1
            response = self.deliver(b, a.id, raw)
            if self._take('duplicate'):
                response = self.deliver(b, a.id, raw)
            self.messages.append((operation, raw, response))
            if self._take('drop_response'):
                raise DrawSyncError('connection_lost')
            value = protocol.decode_response(response)
            if value['state'] != 'completed':
                raise DrawSyncError(value['error'])
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

    def settle(self, devices=None, rounds=12):
        """Pump every online, allowed pair until nobody has anything pending."""
        devices = devices or self.devices
        for _ in range(rounds):
            busy = False
            for a in devices:
                for b in devices:
                    if a is b or b.id not in a.allowed or a.id not in b.allowed or not self.online(a, b):
                        continue
                    if a.engine.pending(b.id) or b.engine.wants():
                        before = (a.engine.pending(b.id), len(b.engine.wants()))
                        self.sync(a, b, hello=True)
                        if (a.engine.pending(b.id), len(b.engine.wants())) != before:
                            busy = True
            if not busy:
                return True
        return False

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


# --- a deterministic software renderer (tests only) ------------------------------------
def render(device, did):
    """Pixels of the drawing on this replica, from its visible operations, using
    Pillow (deterministic, no GPU). Returns the SHA-256 of the RGBA bytes."""
    from PIL import Image, ImageChops, ImageDraw
    info = device.service.get(did)
    width, height = info['width'], info['height']
    ops = device.ops(did)
    layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    def line(draw, op, fill):
        pts = op['points']
        stride = 3 if op.get('pressure') else 2
        xy = [(pts[i], pts[i + 1]) for i in range(0, len(pts), stride)]
        w = max(1, round(op['width']))
        if len(xy) > 1:
            draw.line(xy, fill=fill, width=w, joint='curve')
        for x, y in (xy[0], xy[-1]):
            draw.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=fill)

    for op in ops:
        if op['type'] == 'stroke':
            ink = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            color = tuple(int(op['color'][i:i + 2], 16) for i in (1, 3, 5))
            line(ImageDraw.Draw(ink), op, color + (255,))
            if op['opacity'] < 1:
                alpha = ink.getchannel('A').point(lambda v, o=op['opacity']: round(v * o))
                ink.putalpha(alpha)
            layer = Image.alpha_composite(layer, ink)
        elif op['type'] == 'erase':
            mask = Image.new('L', (width, height), 0)
            line(ImageDraw.Draw(mask), op, 255)
            layer.putalpha(ImageChops.subtract(layer.getchannel('A'), mask))
        elif op['type'] == 'clear':
            layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        elif op['type'] == 'image':
            asset = device.service.asset_info(op['asset_id'])
            if asset is None:
                continue   # Placeholder until the asset arrives.
            chunk = device.service.asset_chunk(op['asset_id'], 0)
            import base64
            data = b''.join(base64.b64decode(device.service.asset_chunk(op['asset_id'], i)['data'])
                            for i in range(chunk['count']))
            picture = Image.open(io.BytesIO(data)).convert('RGBA').resize((round(op['width']), round(op['height'])))
            placed = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            placed.paste(picture, (round(op['x']), round(op['y'])))
            layer = Image.alpha_composite(layer, placed)
    ground = effective_background(info['background'], ops)
    if ground != 'transparent':
        base = Image.new('RGBA', (width, height), (255, 255, 255, 255))
        layer = Image.alpha_composite(base, layer)
    return hashlib.sha256(layer.tobytes()).hexdigest()
