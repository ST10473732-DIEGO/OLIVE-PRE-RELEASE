"""OLIVE Connect World on the desktop: provisioning, route keys and relay presence.

World extends the existing paired-device relationship; it is not a second
trust system. A paired peer receives a per-pair route secret over an already
authenticated Connect channel. With it, both devices dial OUT to the relay,
which joins them; the existing pinned TLS 1.3 session then runs end to end
through the relay (see olive/world/wire.py). Revocation, permissions and
replay protection stay exactly where they were: in Connect.

Secrets: one 32-byte World master key lives in the OS credential vault
(reference ``connect-world-v1``), next to the Connect identity key. Per-pair
route secrets are derived from it (and this Connect identity) on demand and
never written to disk, logs, diagnostics or the UI.
"""
import asyncio
from collections import deque
import base64
import json
import logging
import os
import socket
import tempfile
import threading
import time

from .contracts import ConnectError, PROTOCOL, identifier
from ..world import wire
from ..world.backoff import Backoff

WORLD_PROTOCOL = wire.PROTOCOL
VAULT_REFERENCE = 'connect-world-v1'
MAX_PEERS = 64
UNAVAILABLE_REASONS = ('disabled', 'relay_not_configured', 'secure_storage_unavailable')
CONFLICT_REPLACEMENTS = 3       # 'replaced' this often within the window -> another copy of this profile.
CONFLICT_WINDOW = 120.0
CONFLICT_BACKOFF = 300.0
# The computer kept a healthy Direct channel instead of this tunnel. That is a
# path decision, not a relay or tunnel failure: be reachable again soon, without
# escalating backoff or reporting an error.
DIRECT_PREFERRED_DELAY = 1.0
# Per-tunnel outcomes. They describe one pair's tunnel, never the relay itself.
TUNNEL_ERRORS = frozenset({'tunnel_failed'})
logger = logging.getLogger('olive.connect.paths')


class WorldSettingsStore:
    """Non-secret preferences: On/Off, relay URL and per-peer route generations."""

    def __init__(self, profile):
        self.path = profile / 'connect' / 'world-v1.json'

    @staticmethod
    def default():
        return dict(version=1, enabled=False, relay_url=None, peers={})

    @staticmethod
    def validate(value):
        def require(condition):
            if not condition:
                raise ValueError()
        try:
            require(type(value) is dict and set(value) == {'version', 'enabled', 'relay_url', 'peers'})
            require(value['version'] == 1 and type(value['version']) is int and type(value['enabled']) is bool)
            require(value['relay_url'] is None or (type(value['relay_url']) is str and len(value['relay_url']) <= wire.MAX_URL))
            peers = value['peers']
            require(type(peers) is dict and len(peers) <= MAX_PEERS)
            for peer, entry in peers.items():
                identifier(peer)
                require(type(entry) is dict and set(entry) == {'generation', 'state', 'issued_at', 'confirmed'})
                require(type(entry['generation']) is int and 1 <= entry['generation'] < 2 ** 53)
                require(entry['state'] in ('active', 'revoked'))
                require(entry['issued_at'] is None or (type(entry['issued_at']) is int and entry['issued_at'] >= 0))
                require(type(entry['confirmed']) is bool)
        except (ValueError, TypeError, KeyError, ConnectError):
            raise ConnectError('world_settings_invalid') from None
        return value

    def load(self):
        try:
            with self.path.open('rb') as source:
                raw = source.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            return self.validate(json.loads(raw))
        except FileNotFoundError:
            return self.default()
        except (OSError, ValueError, UnicodeError):
            raise ConnectError('world_settings_invalid') from None

    def save(self, value):
        self.validate(value)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.world-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class WorldKeyStore:
    """The World master key in the same OS vault as the Connect identity key."""

    def __init__(self, vault):
        self.vault = vault
        self._cached = None

    def master(self, *, create):
        if self._cached is not None:
            return self._cached
        try:
            self.vault.require_available()
            if not self.vault.contains(VAULT_REFERENCE):
                if not create:
                    return None
                self.vault.put(VAULT_REFERENCE, 'world/1:' + base64.b64encode(os.urandom(32)).decode('ascii'))
            value = self.vault.read_for_provider(VAULT_REFERENCE)
            if type(value) is not str or not value.startswith('world/1:'):
                raise ValueError()
            key = base64.b64decode(value[8:], validate=True)
            if len(key) != 32:
                raise ValueError()
        except Exception:
            raise ConnectError('secure_storage_unavailable') from None
        self._cached = key
        return key


class WorldService:
    def __init__(self, service, *, dev=None, environ=os.environ):
        self.service = service
        self.settings = WorldSettingsStore(service.profile)
        self.keys = WorldKeyStore(service.identities.key_store.vault)
        # Explicit development mode (loopback ws:// relay). Never implied by a URL.
        self.dev = environ.get('OLIVE_WORLD_DEV') == '1' if dev is None else dev
        # TEST-ONLY: a plaintext relay on a private LAN address (Mac test host). Never a default.
        self.test_lan = environ.get('OLIVE_WORLD_TEST_LAN') == '1'
        self.managed_url = environ.get('OLIVE_WORLD_RELAY_URL') or None
        self.lock = threading.RLock()
        self.routes = {}            # peer -> live route state (never secrets)
        self.relay_error = None     # Relay-level failures only (unreachable, TLS, refused).
        self.relay_reached = False  # This computer registered at the relay since its last relay failure.
        self.presence = WorldPresence(self)

    # ------------------------------------------------------------------ settings
    def relay_url(self, value=None):
        value = value or self.settings.load()
        url = value['relay_url'] or self.managed_url
        if not url:
            return None
        try:
            wire.parse_relay_url(url, dev=self.dev, test_lan=self.test_lan)
        except wire.WorldError:
            return None
        return url

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ConnectError('invalid_world_setting')
        with self.lock:
            value = self.settings.load()
            value['enabled'] = enabled
            self.settings.save(value)
        self.refresh()
        return self.status()

    def set_relay_url(self, url):
        if url is not None:
            try:
                wire.parse_relay_url(url, dev=self.dev, test_lan=self.test_lan)
            except wire.WorldError as error:
                raise ConnectError(str(error)) from None
        with self.lock:
            value = self.settings.load()
            value['relay_url'] = url
            self.settings.save(value)
        self.refresh()
        return self.status()

    # ------------------------------------------------------------------ route keys
    def _identity(self):
        from .identity import fingerprint
        return fingerprint(self.service.cryptographic_identity())

    def _credentials(self, peer, generation, *, create=False):
        master = self.keys.master(create=create)
        if master is None:
            raise ConnectError('secure_storage_unavailable')
        identity = self._identity()
        local = self.service.local_id
        secret = wire.route_secret(master, local, peer, generation, identity)
        return wire.route_id(master, local, peer, generation, identity), secret

    def _paired(self, peer):
        try:
            record = self.service.device(peer, timeout=.25)
        except ConnectError:
            return False
        return record.get('trust_state') == 'paired' and record.get('revoked_at') is None and peer != self.service.local_id

    # ------------------------------------------------------------------ provisioning (olive-connect/1 'world' op)
    def provision(self, peer, arguments):
        """Answer an authenticated paired peer. Idempotent: the same generation is
        returned until a rotation or revocation; nothing is created per request."""
        have = arguments.get('have') if type(arguments) is dict else None
        if type(arguments) is not dict or set(arguments) - {'have'} or (
                have is not None and (type(have) is not str or len(have) != 32
                                      or any(c not in '0123456789abcdef' for c in have))):
            raise ConnectError('invalid_arguments')
        with self.lock:
            value = self.settings.load()
            url = self.relay_url(value)
            base = dict(world_protocol=WORLD_PROTOCOL)
            if not value['enabled']:
                return dict(base, state='unavailable', reason='disabled')
            if url is None:
                return dict(base, state='unavailable', reason='relay_not_configured')
            entry = value['peers'].get(peer)
            if entry is not None and entry['state'] == 'revoked':
                raise ConnectError('device_not_paired')
            if entry is None:
                if len(value['peers']) >= MAX_PEERS:
                    raise ConnectError('capacity_reached')
                entry = dict(generation=1, state='active', issued_at=None, confirmed=False)
            try:
                route, secret = self._credentials(peer, entry['generation'], create=True)
            except ConnectError:
                return dict(base, state='unavailable', reason='secure_storage_unavailable')
            changed = False
            if have == route.hex():
                if not entry['confirmed']:
                    entry['confirmed'], changed = True, True
                result = dict(base, state='current', route_id=route.hex(), relay_url=url)
            else:
                if entry['issued_at'] is None or entry['confirmed']:
                    entry['issued_at'], entry['confirmed'], changed = int(self.service.clock()), False, True
                result = dict(base, state='provisioned', route_id=route.hex(), route_secret=secret.hex(),
                              relay_url=url, generation=entry['generation'])
            if changed or peer not in value['peers']:
                value['peers'][peer] = entry
                self.settings.save(value)
        if changed:
            self.refresh()
        return result

    def rotate(self, peer):
        """New route for this pair; the old route can no longer meet this computer."""
        identifier(peer)
        if not self._paired(peer):
            raise ConnectError('device_not_paired')
        with self.lock:
            value = self.settings.load()
            entry = value['peers'].get(peer)
            if entry is None or entry['state'] != 'active':
                raise ConnectError('world_not_provisioned')
            entry.update(generation=entry['generation'] + 1, issued_at=None, confirmed=False)
            self.settings.save(value)
        self.refresh()
        return self.status()

    def revoke(self, peer):
        """Called on device revocation: the route is retired and never re-issued."""
        with self.lock:
            value = self.settings.load()
            entry = value['peers'].get(peer)
            if entry is not None:
                entry.update(generation=entry['generation'] + 1, state='revoked', issued_at=None, confirmed=False)
                self.settings.save(value)
            self.routes.pop(peer, None)
        self.refresh()

    # ------------------------------------------------------------------ presence
    def desired_routes(self):
        """{peer: (generation, route, credential)} for which this computer is reachable."""
        if self.service.network is None or self.service.closed:
            return {}
        with self.lock:
            value = self.settings.load()
            if not value['enabled'] or self.relay_url(value) is None:
                return {}
            entries = {p: e for p, e in value['peers'].items() if e['state'] == 'active' and e['issued_at'] is not None}
        routes = {}
        for peer, entry in entries.items():
            if not self._paired(peer):
                continue
            try:
                route, secret = self._credentials(peer, entry['generation'])
            except ConnectError:
                with self.lock:
                    self.relay_error = 'secure_storage_unavailable'
                return {}
            routes[peer] = (entry['generation'], route, wire.relay_credential(secret))
        return routes

    def refresh(self):
        """Reconcile relay presence with settings, trust and the Connect network."""
        try:
            desired = self.desired_routes()
        except ConnectError:
            desired = {}
        self.presence.reconcile(desired)

    def route_event(self, peer, generation, **changes):
        with self.lock:
            state = self.routes.setdefault(peer, dict(generation=generation, state='connecting', error=None,
                last_connected_at=None, reconnects=0, bytes_in=0, bytes_out=0, live=None))
            if state['generation'] != generation:
                if generation < state['generation']:
                    return  # A retired route's late callback never overwrites the current one.
                state.update(generation=generation, state='connecting', error=None)
            for key in ('bytes_in', 'bytes_out', 'reconnects'):
                if key in changes:
                    state[key] += changes.pop(key)
            state.update(changes)
            if changes.get('error') is not None and changes['error'] not in TUNNEL_ERRORS:
                self.relay_error, self.relay_reached = changes['error'], False
            elif changes.get('state') in ('registered', 'tunnel', 'connected'):
                self.relay_error, self.relay_reached = None, True

    def drop_route(self, peer, generation):
        with self.lock:
            state = self.routes.get(peer)
            if state is not None and state['generation'] == generation:
                self.routes.pop(peer)

    # ------------------------------------------------------------------ status (no secrets)
    def status(self):
        value = self.settings.load()
        url = self.relay_url(value)
        network = self.service.network
        with self.lock:
            routes = {}
            for peer, state in self.routes.items():
                route = dict(state)
                live = route.pop('live', None)
                if live is not None:   # Plain integer reads of the running tunnel's counters.
                    route['bytes_in'] += live.bytes_in
                    route['bytes_out'] += live.bytes_out
                routes[peer] = route
            relay_error, reached = self.relay_error, self.relay_reached
        peers = {}
        for peer, entry in value['peers'].items():
            live = routes.get(peer, {})
            channel = network.status(peer) if network else dict(state='offline', connection=None)
            online = channel.get('state') == 'online'
            peers[peer] = dict(
                # The path this peer uses right now: Direct is preferred while healthy.
                path={'local': 'direct', 'world': 'world'}.get(channel.get('connection')) if online else None,
                provisioned=entry['state'] == 'active' and entry['issued_at'] is not None,
                confirmed=entry['confirmed'], revoked=entry['state'] == 'revoked',
                route=live.get('state', 'idle'), error=live.get('error'),
                connected=channel.get('state') == 'online' and channel.get('connection') == 'world',
                last_connected_at=live.get('last_connected_at'), reconnects=live.get('reconnects', 0),
                bytes_in=live.get('bytes_in', 0), bytes_out=live.get('bytes_out', 0))
        if not value['enabled']:
            relay = 'off'
        elif url is None:
            relay = 'not_configured'
        elif network is None:
            relay = 'connect_off'
        elif not routes:
            relay = 'idle'
        elif (any(r['state'] in ('registered', 'tunnel', 'connected') for r in routes.values())
              or (reached and relay_error is None)):
            # The relay is reachable. Whether a peer is present is per-route state.
            relay = 'connected'
        elif any(r['state'] == 'conflict' for r in routes.values()):
            relay = 'conflict'
        elif relay_error:
            relay = 'unavailable'
        else:
            relay = 'connecting'
        return dict(name='OLIVE Connect World', protocol=WORLD_PROTOCOL, enabled=value['enabled'],
                    relay=relay, relay_host=wire.relay_host(url) if url else None,
                    relay_custom=value['relay_url'] is not None, managed=self.managed_url is not None,
                    error=relay_error if relay in ('unavailable', 'conflict') else None,
                    dev=self.dev, peers=peers)

    def close(self):
        self.presence.stop()


class WorldPresence:
    """Outbound relay registrations, one per provisioned pair, on one event-loop thread.

    Idempotent: reconcile() and start() never create a second loop, thread or
    route task for the same pair and generation.
    """

    def __init__(self, world):
        self.world = world
        self.lock = threading.Lock()
        self.loop = None
        self.thread = None
        self.tasks = {}           # peer -> (generation, task); touched on the loop thread only
        self.stopped = False

    def _ensure(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return self.loop
            self.stopped = False
            loop = asyncio.new_event_loop()
            started = threading.Event()

            def run():
                asyncio.set_event_loop(loop)
                loop.call_soon(started.set)
                loop.run_forever()
                loop.close()

            self.loop = loop
            self.thread = threading.Thread(target=run, name='olive-connect-world', daemon=True)
            self.thread.start()
            started.wait(5)
            return loop

    def reconcile(self, desired):
        with self.lock:
            idle = self.thread is None or not self.thread.is_alive()
        if idle and not desired:
            return
        loop = self._ensure()
        loop.call_soon_threadsafe(self._reconcile, dict(desired))

    def _reconcile(self, desired):
        for peer, (generation, task) in list(self.tasks.items()):
            if desired.get(peer, (None,))[0] != generation:
                task.cancel()
                del self.tasks[peer]
                self.world.drop_route(peer, generation)
        for peer, (generation, route, credential) in desired.items():
            if peer not in self.tasks:
                task = asyncio.ensure_future(self._route(peer, generation, route, credential))
                self.tasks[peer] = (generation, task)

    def active_tasks(self):
        """Test/diagnostic view: {peer: generation}."""
        result = {}
        if self.loop is None or not self.thread or not self.thread.is_alive():
            return result
        done = threading.Event()

        def read():
            result.update({p: g for p, (g, t) in self.tasks.items() if not t.done()})
            done.set()
        self.loop.call_soon_threadsafe(read)
        done.wait(2)
        return result

    async def _route(self, peer, generation, route, credential):
        from ..world.client import RelayRefused, bridge, category_for, open_relay, rendezvous
        world = self.world
        backoff = Backoff()
        replaced = deque()
        loop = asyncio.get_running_loop()
        event = lambda **changes: world.route_event(peer, generation, **changes)
        while True:
            url = world.relay_url()
            network = world.service.network
            if url is None or network is None:
                return
            event(state='connecting')
            ws = None
            bridged = None
            delay = None
            try:
                ws = await open_relay(url, dev=world.dev, test_lan=world.test_lan)
                await rendezvous(ws, 'desktop', route, credential, on_waiting=lambda: event(state='registered', error=None))
                logger.info('world relay peer=%s paired', peer[:8])
                event(state='tunnel', error=None, live=ws)   # Live counters while the tunnel runs.
                ours, theirs = socket.socketpair()
                try:
                    channel = await loop.run_in_executor(None, network.attach_world, theirs, peer)
                except Exception:
                    ours.close()
                    raise
                started = loop.time()
                bridged = asyncio.ensure_future(bridge(ws, ours))
                # Observe (never cancel) the channel's own readiness future.
                ready = asyncio.Event()

                def wake(_):
                    try:
                        loop.call_soon_threadsafe(ready.set)
                    except RuntimeError:
                        pass  # Presence already stopped; nothing waits any more.
                channel.ready.add_done_callback(wake)
                waiter = asyncio.ensure_future(ready.wait())
                await asyncio.wait([bridged, waiter], return_when=asyncio.FIRST_COMPLETED)
                waiter.cancel()
                outcome = _outcome(channel)
                backoff_reset_after = outcome == 'authenticated'
                if backoff_reset_after:
                    event(state='connected', last_connected_at=int(world.service.clock()), error=None)
                reason = await bridged
                logger.info('world tunnel peer=%s gen=%s outcome=%s bridge=%s lived=%.1fs',
                    peer[:8], channel.generation[:8], outcome, reason, loop.time() - started)
                event(bytes_in=ws.bytes_in, bytes_out=ws.bytes_out, reconnects=1, live=None,
                      state='registered' if backoff_reset_after else 'connecting')
                ws = None
                if backoff_reset_after:
                    # The peer authenticated, then left: be reachable again at once. Failed
                    # tunnels (wrong identity, stolen route) keep backing off instead.
                    backoff.settled(loop.time() - started)
                    delay = 0.05
                elif outcome == 'direct_preferred':
                    event(error=None)
                    delay = DIRECT_PREFERRED_DELAY
                else:
                    event(error='tunnel_failed' if reason not in ('peer_left',) else None)
            except asyncio.CancelledError:
                if bridged is not None and not bridged.done():
                    bridged.cancel()
                    await asyncio.gather(bridged, return_exceptions=True)
                if ws is not None:
                    ws.abort()
                raise
            except RelayRefused as refused:
                if refused.category == 'replaced':
                    now = loop.time()
                    replaced.append(now)
                    while replaced and replaced[0] < now - CONFLICT_WINDOW:
                        replaced.popleft()
                    if len(replaced) >= CONFLICT_REPLACEMENTS:
                        # Another running copy of this profile holds the same World route.
                        event(state='conflict', error='world_identity_conflict')
                        delay = CONFLICT_BACKOFF
                if delay is None:
                    event(state='connecting', error=refused.category)
                logger.info('world relay peer=%s refused=%s', peer[:8], refused.category)
            except Exception as error:
                event(state='connecting', error=category_for(error))
                logger.info('world relay peer=%s failed=%s', peer[:8], category_for(error))
            finally:
                if ws is not None:
                    ws.abort()
            await asyncio.sleep(delay if delay is not None else backoff.next())

    def stop(self):
        with self.lock:
            loop, thread = self.loop, self.thread
            self.stopped = True
        if loop is None or thread is None or not thread.is_alive():
            return

        async def shutdown():
            self.tasks.clear()
            # Route tasks and the bridges they started: nothing is left pending.
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            loop.stop()
        asyncio.run_coroutine_threadsafe(shutdown(), loop)
        thread.join(5)
        with self.lock:
            if self.thread is thread:
                self.thread, self.loop = None, None


def _outcome(channel):
    """Fixed word for how a tunnelled channel ended its handshake (never exception text)."""
    if not channel.ready.done():
        return 'pending'
    error = channel.ready.exception()
    if error is None:
        return 'authenticated'
    return str(error) if isinstance(error, ConnectError) else 'tunnel_failed'


def provisioning_request(source, target, *, have=None, now=None):
    """The phone-side request (olive-connect/1, connect.ping / world). Used by test peers."""
    import uuid
    from .contracts import canonical
    now = int(time.time()) if now is None else now
    return canonical(dict(request_id=str(uuid.uuid4()), protocol_version=PROTOCOL, source_device_id=source,
                          target_device_id=target, capability='connect.ping', operation='world',
                          arguments={} if have is None else {'have': have}, timestamp=now, expires_at=now + 60))


def parse_provisioning(result):
    """Strict client-side parse of the 'world' result (mirrors WorldWire.swift)."""
    def require(condition):
        if not condition:
            raise ConnectError('invalid_response')
    require(type(result) is dict and result.get('world_protocol') == WORLD_PROTOCOL)
    state = result.get('state')
    if state == 'unavailable':
        require(set(result) == {'world_protocol', 'state', 'reason'} and result['reason'] in UNAVAILABLE_REASONS)
    elif state == 'current':
        require(set(result) == {'world_protocol', 'state', 'route_id', 'relay_url'})
    elif state == 'provisioned':
        require(set(result) == {'world_protocol', 'state', 'route_id', 'route_secret', 'relay_url', 'generation'})
        require(type(result['route_secret']) is str and len(result['route_secret']) == 64)
        bytes.fromhex(result['route_secret'])
        require(type(result['generation']) is int and result['generation'] >= 1)
    else:
        require(False)
    if state != 'unavailable':
        require(type(result['route_id']) is str and len(result['route_id']) == 32)
        bytes.fromhex(result['route_id'])
        require(type(result['relay_url']) is str)
    return result
