"""TEST-ONLY: a real OLIVE World relay on loopback (development ws://), in a thread."""
import asyncio
import threading

from olive.world_relay.server import Limits, Relay


class RelayThread:
    def __init__(self, *, limits=None, observer=None, port=0):
        self.limits, self.observer, self.port = limits, observer, port
        self.loop = None
        self.thread = None
        self.relay = None

    def start(self):
        self.loop = asyncio.new_event_loop()
        started = threading.Event()
        def run():
            asyncio.set_event_loop(self.loop)
            self.loop.call_soon(started.set)
            self.loop.run_forever()
            self.loop.close()
        self.thread = threading.Thread(target=run, name='test-world-relay', daemon=True)
        self.thread.start()
        started.wait(5)
        self.relay = Relay(self.limits or Limits(), observer=self.observer)
        self.port = self.call(self.relay.start('127.0.0.1', self.port))
        return self

    @property
    def url(self):
        return 'ws://127.0.0.1:%d' % self.port

    def call(self, coroutine, timeout=10):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    def run(self, function):
        done = threading.Event()
        box = []
        def wrapper():
            box.append(function())
            done.set()
        self.loop.call_soon_threadsafe(wrapper)
        done.wait(5)
        return box[0] if box else None

    def stop(self):
        if self.loop is None:
            return
        try:
            self.call(self.relay.shutdown(grace=2))
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)
            self.loop = None
