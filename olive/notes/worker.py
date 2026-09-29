"""One owner thread for every Notes document and database operation.

Bridge requests, Connect channel threads and timers all submit work here, so
the CRDT documents are never touched concurrently and local edits, remote
updates and compaction are naturally serialized.
"""
from concurrent.futures import Future
import heapq
import itertools
import queue
import threading
import time


class NotesWorker:
    def __init__(self, name='olive-notes'):
        self._queue = queue.Queue()
        self._timers = []
        self._timer_keys = {}
        self._counter = itertools.count()
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    @property
    def is_current(self):
        return threading.current_thread() is self._thread

    def submit(self, function, *args, **kwargs):
        future = Future()
        if self._stopping:
            future.set_exception(RuntimeError('notes_stopped'))
            return future
        self._queue.put((function, args, kwargs, future))
        return future

    def call(self, function, *args, timeout=30, **kwargs):
        if self.is_current:
            return function(*args, **kwargs)
        return self.submit(function, *args, **kwargs).result(timeout=timeout)

    def schedule(self, key, delay, function):
        """Run `function` on this thread after `delay`; keeps the earliest per key."""
        deadline = time.monotonic() + delay
        def add():
            current = self._timer_keys.get(key)
            if current is not None and current <= deadline:
                return
            self._timer_keys[key] = deadline
            heapq.heappush(self._timers, (deadline, next(self._counter), key, function))
        self.call(add) if self.is_current else self._queue.put((add, (), {}, None))

    def run_due(self, *, all_timers=False):
        """Run due timers now (tests pass all_timers=True to skip waiting)."""
        def due():
            now = time.monotonic()
            while self._timers and (all_timers or self._timers[0][0] <= now):
                deadline, _, key, function = heapq.heappop(self._timers)
                if self._timer_keys.get(key) != deadline:
                    continue  # Superseded by an earlier deadline for the same key.
                del self._timer_keys[key]
                try:
                    function()
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning('Notes timer failed: %s', key)
        return self.call(due)

    def _run(self):
        while True:
            timeout = None
            if self._timers:
                timeout = max(0, self._timers[0][0] - time.monotonic())
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                item = None
            if item is not None:
                function, args, kwargs, future = item
                if function is None:
                    break
                if future is None:
                    function(*args, **kwargs)
                elif future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function(*args, **kwargs))
                    except BaseException as error:
                        future.set_exception(error)
            now = time.monotonic()
            while self._timers and self._timers[0][0] <= now:
                deadline, _, key, function = heapq.heappop(self._timers)
                if self._timer_keys.get(key) != deadline:
                    continue
                del self._timer_keys[key]
                try:
                    function()
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning('Notes timer failed: %s', key)

    def stop(self, timeout=5):
        if self._stopping:
            return
        self._stopping = True
        self._queue.put((None, (), {}, None))
        if not self.is_current:
            self._thread.join(timeout)
