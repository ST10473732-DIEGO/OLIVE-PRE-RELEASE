"""TEST HOST ONLY: a real OLIVE desktop Connect service for physical-iPhone Draw and Chat acceptance.

With ``--chat`` it also attaches the production Remote Chat v2 service
(olive-chat/1: modes, attachments, artifacts, receipts) backed by the TEST-ONLY
deterministic runtime (tests/fixtures/chat_test_runtime.py). No model runs:
results from this host are transport/UI verification, never real-model results.

Runs the production Python ``DesktopDeviceService`` (Connect TLS listener,
Bonjour advertisement, frames 13-16, ``sync.draw`` permission) with a real
``DrawService`` on a fresh TEMPORARY profile and an in-memory key vault. It is
used when the user's real desktop cannot be driven from this machine. The phone
pairs with it under its separate acceptance identity (``--c92-pairing-check``),
so the phone's real pairing is never touched.

The host stands in for the human at the desktop: ``pair`` confirms the
comparison value this host itself displays, and permissions/edits are driven
by commands. Never point it at a real profile; it refuses an existing one.

Control: JSON lines on 127.0.0.1 (``--port``); ``python draw_phone_test_host.py --send '{"cmd": "status"}'``.
"""
import argparse
import json
import socket
import socketserver
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from olive.connect.identity import DeviceKeyStore  # noqa: E402
from olive.connect.service import DesktopDeviceService  # noqa: E402
from olive.draw.service import DrawService  # noqa: E402
from olive.notes.service import NotesService  # noqa: E402
from tests.test_connect_pairing import MemoryVault  # noqa: E402

COLORS = {'red': '#e53935', 'green': '#43a047', 'blue': '#1e63e9', 'purple': '#8e24aa', 'black': '#000000'}


def lan_address():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('192.0.2.1', 9))      # TEST-NET; no packet is sent for UDP connect
        return probe.getsockname()[0]
    finally:
        probe.close()


class NoModels:
    """Remote AI runtime stand-in: no preset is available, nothing is busy."""
    def availability(self):
        from olive.connect.inference_protocol import PRESETS
        return {preset: False for preset in PRESETS}

    def local_busy(self):
        return False


class Host:
    def __init__(self, profile, chat=False, video=None):
        import asyncio
        self.profile = Path(profile)
        self.chat_enabled, self.video = chat, video
        self.chat_runtime = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name='test-host-loop').start()
        self.vault = MemoryVault()
        self.lock = threading.RLock()
        self.log = []
        self.pair_state = {}
        self._start()

    def _start(self):
        self.service = DesktopDeviceService(self.profile, key_store=DeviceKeyStore(self.vault))
        self.draw = DrawService(self.profile / 'drawings.sqlite3', device_id=self.service.local_id,
                                publish=lambda topic, data: self.log.append((time.time(), topic, data.get('drawing_id'))))
        self.notes = NotesService(self.profile / 'notes.sqlite3', device_id=self.service.local_id)
        self.service.attach_notes(self.notes)
        self.service.attach_draw(self.draw)
        # The phone's Connect session starts with the C7 status request; this host
        # answers it with every preset unavailable (no model is ever run here).
        self.service.attach_inference(NoModels(), self.loop)
        if self.chat_enabled:
            from tests.fixtures.chat_test_runtime import ChatTestRuntime
            if self.chat_runtime is None:
                self.chat_runtime = ChatTestRuntime(self.profile / 'chat-artifacts', video=self.video, delay=0.05)
            self.service.attach_chat(self.chat_runtime, self.loop)
        self.network = None
        self.network_on()

    def network_on(self):
        if self.network is None:
            self.network = self.service.enable_network(lan_address(), discovery=True)
        return {'address': self.network.interface.address, 'port': self.network.port}

    def network_off(self):
        """The desktop goes offline (listener and channels closed; data kept)."""
        if self.network is not None:
            self.service.disable_network()
            self.network = None
        return True

    def restart(self):
        """Desktop process restart on the same profile and identity."""
        self.network_off()
        if self.service.chat is not None:
            import asyncio
            asyncio.run_coroutine_threadsafe(self.service.chat.shutdown(), self.loop).result(15)
        self.service.close()
        self.notes.close()
        self._start()
        return self.network_on()

    # --- pairing (the host confirms the value it displays itself) ------------------------
    def pair(self):
        offer = self.service.pairing_transport.create().decode('utf-8')
        sid = json.loads(offer)['session_id']
        self.pair_state = {'session_id': sid, 'state': 'offer_ready'}
        threading.Thread(target=self._confirm, args=(sid,), daemon=True).start()
        return {'offer': offer, 'session_id': sid}

    def _confirm(self, sid):
        deadline = time.time() + 300
        confirmed = False
        while time.time() < deadline:
            try:
                status = self.service.pairing_transport.status(sid)
            except Exception as failure:
                self.pair_state = {'session_id': sid, 'state': 'error', 'error': type(failure).__name__}
                return
            self.pair_state = {k: status.get(k) for k in ('session_id', 'state', 'comparison', 'candidate_name', 'error')}
            if status.get('comparison') and not confirmed:
                self.service.pairing.confirm(sid, status['comparison'])
                confirmed = True
            if status['state'] in ('completed', 'failed', 'cancelled', 'expired', 'interrupted'):
                return
            time.sleep(.2)

    def phone(self):
        devices = [d for d in self.service.paired_devices() if d['device_id'] != self.service.local_id
                   and d.get('trust_state') == 'paired' and d.get('revoked_at') is None]
        if not devices:
            raise RuntimeError('no paired phone')
        return devices[-1]['device_id']

    def status(self):
        result = {'local_id': self.service.local_id, 'pairing': self.pair_state, 'network': self.network is not None}
        try:
            phone = self.phone()
            result['phone'] = phone
            result['online'] = self.network is not None and phone in self.network.channels
            result['draw'] = self.service.draw.status(phone)
            result['announced'] = phone in self.service.draw.announced
            result['permissions'] = {c: self.service.permission(phone, c) for c in ('sync.draw', 'sync.notes')}
        except Exception as failure:
            result['phone_error'] = str(failure)
        return result

    def permission(self, capability, decision):
        phone = self.phone()
        self.service.set_permission(phone, capability, decision)
        return {capability: self.service.permission(phone, capability)}

    # --- drawings (synthetic only) ----------------------------------------------------------
    def find(self, title):
        for view in ('drawings', 'trash'):
            for d in self.draw.list_drawings(view)['drawings']:
                if d['title'] == title:
                    return d['drawing_id']
        return None

    def create(self, title, width=800, height=600, background='#ffffff'):
        return self.draw.create(title, width, height, background)['drawing_id']

    def stroke(self, title, color='red', y=0.5, width=12):
        did = self.find(title)
        info = self.draw.get(did)
        w, h = info['width'], info['height']
        points = [round(w * .1, 2), round(h * y, 2), round(w * .5, 2), round(h * y + 3, 2), round(w * .9, 2), round(h * y, 2)]
        op = {'type': 'stroke', 'id': uuid.uuid4().hex, 'tool': 'pen', 'color': COLORS.get(color, color), 'width': width,
              'opacity': 1, 'pressure': False, 'points': points}
        self.draw.append(did, op)
        return op['id']

    def image(self, title, color=(0, 128, 255, 255), size=(320, 200)):
        import io
        from PIL import Image
        did = self.find(title)
        picture = Image.new('RGBA', size, tuple(color))
        out = io.BytesIO()
        picture.save(out, format='PNG')
        info = self.draw.store_asset(out.getvalue())
        drawing = self.draw.get(did)
        op = {'type': 'image', 'id': uuid.uuid4().hex, 'asset_id': info['asset_id'], 'x': (drawing['width'] - size[0]) / 2,
              'y': (drawing['height'] - size[1]) / 2, 'width': size[0], 'height': size[1], 'opacity': 1}
        self.draw.append(did, op)
        return info['asset_id']

    def state(self, title):
        did = self.find(title)
        if did is None:
            return None
        info = self.draw.get(did)
        with self.draw.store.transaction(read_only=True) as db:
            rows = db.execute("SELECT r.body, r.device, COALESCE(v.hidden,0) FROM draw_records r LEFT JOIN draw_visibility v "
                              "ON v.target=r.record_id WHERE r.drawing_id=? AND r.kind='op' ORDER BY r.sort_key", (did,)).fetchall()
            wanted = [r[0] for r in db.execute('SELECT asset_id FROM draw_wanted WHERE drawing_id=?', (did,))]
        ops = []
        for body, device, hidden in rows:
            op = json.loads(body)['body']
            ops.append({'id': op['id'], 'type': op['type'], 'color': op.get('color'), 'asset_id': op.get('asset_id'),
                        'by': 'phone' if device != self.service.local_id else 'desktop', 'hidden': bool(hidden)})
        return {'drawing_id': did, 'title': info['title'], 'trashed': info['trashed'], 'background': info['background'],
                'ops': ops, 'visible': [o for o in ops if not o['hidden']], 'wanted': wanted}

    def assets(self, title):
        state = self.state(title)
        out = {}
        for op in state['ops']:
            if op['asset_id']:
                info = self.draw.asset_info(op['asset_id'])
                out[op['asset_id']] = info and {'size': info['size'], 'mime': info['mime'], 'width': info['width'], 'height': info['height']}
        return out

    def wait(self, title, condition, timeout=60):
        """Poll until a named predicate over the drawing state holds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.state(title)
            if state is not None and condition(state):
                return state
            time.sleep(.2)
        raise TimeoutError(f'{title}: condition not met; last={self.state(title)}')

    def handle(self, message):
        cmd, args = message['cmd'], message.get('args', {})
        with self.lock:
            if cmd == 'status':
                return self.status()
            if cmd == 'chat':
                # What the "desktop" ran and received: modes, attachment kinds and hashes (no content).
                runtime = self.chat_runtime
                return {'runs': [list(r) for r in runtime.runs], 'received': runtime.received,
                        'live': self.service.chat.snapshot(self.phone()) if self.service.chat else []}
            if cmd == 'chat_reset':
                self.chat_runtime.runs.clear(); self.chat_runtime.received.clear()
                return True
            if cmd == 'chat_video':
                self.chat_runtime.video = args['path']
                return True
            if cmd == 'chat_files':
                # Staged attachments for the phone (count and sizes only) and generated artifacts.
                staging = self.profile / 'connect' / 'chat-staging'
                staged = [dict(name=p.suffix, size=p.stat().st_size) for p in staging.rglob('*') if p.is_file() and p.suffix != '.json']
                return {'staged': staged, 'artifacts': len(self.chat_runtime.files)}
            if cmd == 'chat_unavailable':
                self.chat_runtime.unavailable = set(args.get('modes', []))
                return sorted(self.chat_runtime.unavailable)
            if cmd == 'pair':
                return self.pair()
            if cmd == 'permission':
                return self.permission(args['capability'], args['decision'])
            if cmd == 'network_off':
                return self.network_off()
            if cmd == 'network_on':
                return self.network_on()
            if cmd == 'restart':
                return self.restart()
            if cmd == 'create':
                return self.create(args['title'], args.get('width', 800), args.get('height', 600), args.get('background', '#ffffff'))
            if cmd == 'stroke':
                return self.stroke(args['title'], args.get('color', 'red'), args.get('y', 0.5), args.get('width', 12))
            if cmd == 'image':
                return self.image(args['title'], tuple(args.get('color', (0, 128, 255, 255))))
            if cmd in ('undo', 'redo'):
                return getattr(self.draw, cmd)(self.find(args['title']))['record'] is not None
            if cmd == 'rename':
                return self.draw.rename(self.find(args['title']), args['to'])['title']
            if cmd in ('trash', 'restore'):
                return getattr(self.draw, cmd)(self.find(args['title']))['trashed']
            if cmd == 'purge':
                return self.draw.purge(self.find(args['title']))
            if cmd == 'state':
                return self.state(args['title'])
            if cmd == 'assets':
                return self.assets(args['title'])
            if cmd == 'list':
                return [d['title'] for d in self.draw.list_drawings(args.get('view', 'drawings'))['drawings']]
        if cmd == 'wait_visible':
            # Visible op count (optionally by author) reaches N.
            by = args.get('by')
            return self.wait(args['title'], lambda s: len([o for o in s['visible'] if by is None or o['by'] == by]) == args['count'],
                             args.get('timeout', 60))
        if cmd == 'wait_title':
            return self.wait(args['title'], lambda s: True, args.get('timeout', 60))
        raise ValueError(f'unknown command {cmd}')


def serve(host, port):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                try:
                    reply = {'ok': True, 'result': host.handle(json.loads(line))}
                except Exception as failure:
                    reply = {'ok': False, 'error': f'{type(failure).__name__}: {failure}'}
                self.wfile.write((json.dumps(reply, default=str) + '\n').encode('utf-8'))
                self.wfile.flush()

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(('127.0.0.1', port), Handler) as server:
        server.serve_forever()


def send(port, message):
    with socket.create_connection(('127.0.0.1', port), timeout=600) as sock:
        sock.sendall((json.dumps(message) + '\n').encode('utf-8'))
        return json.loads(sock.makefile('r', encoding='utf-8').readline())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=48731)
    parser.add_argument('--profile', help='A NEW, empty directory (a temporary one by default)')
    parser.add_argument('--send', help='Send one JSON command to a running host and print the reply')
    parser.add_argument('--chat', action='store_true', help='Also serve olive-chat/1 with the deterministic TEST runtime')
    parser.add_argument('--chat-video', help='A synthetic MP4 the test runtime returns for VIDEO')
    args = parser.parse_args()
    if args.send:
        print(json.dumps(send(args.port, json.loads(args.send)), indent=1))
        return
    profile = Path(args.profile) if args.profile else Path(tempfile.mkdtemp(prefix='olive-draw-test-host-'))
    if profile.exists() and any(profile.iterdir()):
        parser.error('Refusing to use a non-empty profile: the test host only runs on a fresh temporary profile.')
    host = Host(profile, chat=args.chat, video=args.chat_video)
    print(json.dumps({'ready': True, 'profile': str(profile), 'local_id': host.service.local_id, **host.network_on()}), flush=True)
    serve(host, args.port)


if __name__ == '__main__':
    main()
