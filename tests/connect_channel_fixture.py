"""Event-driven transport diagnostics and exact-channel lifecycle test helpers."""
import asyncio
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from unittest.mock import patch


@asynccontextmanager
async def held_activity_writer(test, service):
    """Hold a real C4-style Activity write, with no timer-based synchronization."""
    entered, release = threading.Event(), threading.Event()
    def writer():
        with service.repository.transaction(component='activity_repository') as db:
            service.repository.audit(db, None, None, None, 0, 'request_denied')
            entered.set()
            if not release.wait(8):
                raise AssertionError('activity writer was not released')
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(writer)
        try:
            test.assertTrue(await asyncio.to_thread(entered.wait, 3))
            yield
        finally:
            release.set()
            await asyncio.to_thread(task.result, 4)


def note_failure(error, channel, requester, target):
    error.add_note('C3 test diagnostics: ' + json.dumps(dict(
        requested=channel.debug_snapshot(),
        requester=requester.network.debug_snapshot(target.local_id) if requester.network else {'disabled': True},
        target=target.network.debug_snapshot(requester.local_id) if target.network else {'disabled': True}), sort_keys=True))


async def close_service(test, service):
    network = service.network
    if network is None:
        await asyncio.to_thread(service.close)
        return
    with network.lock:
        owned = tuple(network.workers)
    await asyncio.to_thread(service.close)
    test.assertFalse(network.workers)
    test.assertFalse(network.thread.is_alive())
    test.assertFalse(network.reconnector.is_alive())
    test.assertTrue(all(not channel.thread.is_alive() and channel.sock.fileno() == -1 for channel in owned))


@asynccontextmanager
async def replacement_while_old_cleanup_waits(test, requester, target, channel):
    network = target.network
    old = network.channels[requester.local_id]
    entered, release = threading.Event(), threading.Event()
    finished = network.finished

    def held_finished(candidate, reason):
        if candidate is old:
            entered.set()
            if not release.wait(4):
                raise AssertionError('old target cleanup was not released')
        finished(candidate, reason)

    with patch.object(network, 'finished', held_finished):
        try:
            await asyncio.to_thread(requester.network.disconnect, target.local_id, wait=False)
            test.assertTrue(await asyncio.to_thread(entered.wait, 3))
            await asyncio.to_thread(channel.thread.join, 4)
            test.assertFalse(channel.thread.is_alive())
            replacement = await asyncio.to_thread(requester.network.connect,
                target.local_id, '127.0.0.1', network.port)
            test.assertNotEqual(channel.generation, replacement.generation)
            yield replacement, old, release
        finally:
            release.set()
            await asyncio.to_thread(old.thread.join, 4)
            test.assertFalse(old.thread.is_alive())
