"""Venv-side private native helper ownership and cancellation, without GI imports."""
import asyncio
import json
import signal
from pathlib import Path
import subprocess
import threading


class NativeClient:
    def __init__(self, stop, on_event=None, python='/usr/bin/python3'):
        self.stop = stop
        self.on_event = on_event or (lambda event: None)
        self.python = python
        self.process = None
        self.loop = None
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.pending = {}
        self.sequence = 0
        self.generation = 0
        self.reader = self.heartbeat = None
        self.verified_stop = False

    def start(self):
        if self.process:
            return
        if not Path(self.python).is_file():
            raise RuntimeError('Distribution Python with GObject is unavailable')
        self.loop = asyncio.get_running_loop()
        self.closed = threading.Event()
        self.generation += 1
        self.verified_stop = False
        worker = Path(__file__).with_name('worker.py')
        self.process = subprocess.Popen([self.python, '-I', str(worker)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.reader = threading.Thread(target=self._read, args=(self.process, self.generation), daemon=True, name='olive-native-replies')
        self.heartbeat = threading.Thread(target=self._heartbeat, daemon=True, name='olive-native-lease')
        self.reader.start()
        self.heartbeat.start()

    def send(self, value):
        wire = (json.dumps(value, ensure_ascii=True, allow_nan=False) + '\n').encode()
        if len(wire) > 65536:
            raise ValueError('Native request too large')
        with self.lock:
            if not self.process or self.closed.is_set() or self.process.poll() is not None:
                raise RuntimeError('Native helper is unavailable')
            view = memoryview(wire)
            while view:
                written = self.process.stdin.write(view)
                if not written:
                    raise BrokenPipeError("Native command channel closed")
                view = view[written:]

    def _heartbeat(self):
        while not self.closed.wait(.4):
            try:
                self.send({'method': 'heartbeat'})
            except (OSError, RuntimeError):
                return

    def _read(self, process, generation):
        try:
            while line := process.stdout.readline(6 * 1024 * 1024):
                value = json.loads(line)
                if generation != self.generation:
                    return
                if 'event' in value:
                    self.stop.set()  # Bypasses model, asyncio and persistence.
                    if value['event'] == 'global-stop':
                        self.verified_stop = True
                    elif value['event'] == 'shortcut-revoked':
                        self.verified_stop = False
                    self.loop.call_soon_threadsafe(self._event, value['event'], generation)
                else:
                    self.loop.call_soon_threadsafe(self._reply, value, generation)
        except (OSError, ValueError):
            if generation == self.generation:
                self.request_stop()
        finally:
            if generation == self.generation:
                self.request_stop()
            if generation == self.generation and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self._failed, generation)

    def _event(self, event, generation):
        if generation == self.generation:
            self.on_event(event)

    def _reply(self, value, generation=None):
        if generation is not None and generation != self.generation:
            return
        future = self.pending.pop(value.get('id'), None)
        if future and not future.done():
            if 'error' in value:
                future.set_exception(RuntimeError(value.get('message', 'Native operation failed')))
            else:
                future.set_result(value['result'])

    def _failed(self, generation=None):
        if generation is not None and generation != self.generation:
            return
        self.verified_stop = False
        for future in self.pending.values():
            if not future.done():
                future.set_exception(RuntimeError('Native helper exited; task must not replay'))
        self.pending.clear()
        if not self.closed.is_set():
            self.on_event('helper-exited')

    async def call(self, method, arguments=None, timeout=10):
        self.start()
        if self.pending:
            raise RuntimeError('Native helper has an outstanding operation')
        self.sequence += 1
        key = self.sequence
        future = self.loop.create_future()
        self.pending[key] = future
        try:
            self.send({'id': key, 'method': method, 'arguments': arguments or {}})
            return await asyncio.wait_for(asyncio.shield(future), timeout)
        except (asyncio.CancelledError, TimeoutError):
            # Never release/reuse a timed-out input session.
            self.request_stop()
            raise
        finally:
            self.pending.pop(key, None)
            if not future.done():
                future.cancel()

    def request_stop(self):
        self.stop.set()
        if self.process and not self.closed.is_set():
            try:
                # Separate OS signal path; never waits for the command pipe lock.
                self.process.send_signal(signal.SIGUSR1)
            except (OSError, ProcessLookupError):
                pass

    async def close(self):
        self.request_stop()
        self.closed.set()
        process = self.process
        if not process:
            return
        with self.lock:
            process.stdin.close()
        try:
            await asyncio.to_thread(process.wait, 4)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 2)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
        process.stdout.close()
        await asyncio.to_thread(self.reader.join, 1)
        await asyncio.to_thread(self.heartbeat.join, 1)
        self.process = None
        self._failed()
