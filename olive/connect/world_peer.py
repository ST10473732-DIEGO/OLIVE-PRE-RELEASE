"""The client (phone) role of OLIVE Connect World for a Python Connect peer.

Used by the World integration harness, the Mac test host and the desktop UI
check. It is an ordinary client: it gets its route only from a provisioning
answer over an authenticated channel, dials out to the relay, then runs the
normal pinned Connect TLS handshake. It cannot bypass any desktop authority.
"""
import asyncio
import socket
import threading

from .contracts import ConnectError
from .world import parse_provisioning, provisioning_request
from ..world import wire


def provision(channel, service, peer, *, have=None):
    """Ask ``peer`` for its World route over an authenticated channel. Returns the result."""
    response = channel.request(provisioning_request(service.local_id, peer, have=have))
    if response.get('state') != 'completed':
        raise ConnectError(response.get('error') or 'world_provisioning_failed')
    return parse_provisioning(response['result'])


class WorldPeer:
    def __init__(self, service, peer, *, dev=False, test_lan=False):
        self.service, self.peer, self.dev, self.test_lan = service, peer, dev, test_lan
        self.credentials = None       # {relay_url, route_id, route_secret}; memory only here.
        self.loop = None
        self.thread = None
        self.bridges = []
        self.websockets = []
        self.lock = threading.Lock()

    def store(self, result):
        """Keep a 'provisioned' answer; a 'current' one only refreshes the relay URL."""
        if result['state'] == 'provisioned':
            self.credentials = dict(relay_url=result['relay_url'], route_id=result['route_id'],
                                    route_secret=result['route_secret'])
        elif result['state'] == 'current' and self.credentials:
            self.credentials['relay_url'] = result['relay_url']
        elif result['state'] == 'unavailable':
            pass
        return self.credentials

    def have(self):
        return self.credentials['route_id'] if self.credentials else None

    def _ensure_loop(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return self.loop
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def run():
                asyncio.set_event_loop(loop)
                loop.call_soon(ready.set)
                loop.run_forever()
                loop.close()
            self.loop = loop
            self.thread = threading.Thread(target=run, name='olive-world-peer', daemon=True)
            self.thread.start()
            ready.wait(5)
            return loop

    async def _open(self, credentials, wait):
        from ..world.client import open_relay, rendezvous
        ws = await open_relay(credentials['relay_url'], dev=self.dev, test_lan=self.test_lan)
        try:
            secret = bytes.fromhex(credentials['route_secret'])
            await rendezvous(ws, 'phone', bytes.fromhex(credentials['route_id']), wire.relay_credential(secret),
                             timeout=wait)
        except BaseException:
            ws.abort()
            raise
        return ws

    def connect(self, *, credentials=None, wait=20.0, timeout=None):
        """Dial the relay, join this pair's route and authenticate. Returns the Channel."""
        from ..world.client import bridge
        credentials = credentials or self.credentials
        if not credentials:
            raise ConnectError('world_not_provisioned')
        network = self.service.network
        if network is None:
            raise ConnectError('network_disabled')
        loop = self._ensure_loop()
        try:
            ws = asyncio.run_coroutine_threadsafe(self._open(credentials, wait), loop).result(wait + 15)
        except Exception as error:
            from ..world.client import category_for
            raise ConnectError(category_for(error)) from None
        ours, theirs = socket.socketpair()
        task = asyncio.run_coroutine_threadsafe(bridge(ws, ours), loop)
        with self.lock:
            self.bridges.append(task)
            self.websockets.append(ws)
        return network.connect_world(self.peer, theirs, timeout=timeout)

    def drop(self):
        """Simulate losing the network: abort every relay socket without a close handshake."""
        with self.lock:
            sockets = list(self.websockets)
            self.websockets.clear()
        if self.loop is not None:
            for ws in sockets:
                self.loop.call_soon_threadsafe(ws.abort)

    def close(self):
        self.drop()
        with self.lock:
            loop, thread = self.loop, self.thread
            self.bridges.clear()
        if loop is None or thread is None or not thread.is_alive():
            return

        async def shutdown():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            loop.stop()
        asyncio.run_coroutine_threadsafe(shutdown(), loop)
        thread.join(5)
