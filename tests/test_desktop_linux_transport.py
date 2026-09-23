"""Deterministic private helper transport ownership; never inject host input."""
import asyncio
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest.mock import Mock

from olive.desktop.linux.client import NativeClient
from olive.desktop.task_authority import TaskAuthority


@unittest.skipUnless(os.name == 'posix', 'Linux signal transport contract')
class NativeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_pipe_stop_is_immediate_and_strict(self):
        from olive.bridge.__main__ import stop_from_frame
        host = Mock()
        valid = dict(v=1, id='stop-fixture', method='desktop.stop', args={})
        for value in ({**valid, 'args': {'approved': True}},
                      {**valid, 'method': 'desktop.reset'}, {'method': 'desktop.stop'}):
            stop_from_frame(host, json.dumps(value).encode())
        host.emergency_stop.assert_not_called()
        stop_from_frame(host, json.dumps(valid).encode())
        host.emergency_stop.assert_called_once_with()

    async def test_stop_bypasses_blocked_command_pipe_lock(self):
        stopped = threading.Event()
        client = NativeClient(stopped)
        client.process = Mock()
        # Holding the writer lock in this thread must not deadlock Stop.
        with client.lock:
            client.request_stop()
        self.assertTrue(stopped.is_set())
        client.process.send_signal.assert_called_once_with(signal.SIGUSR1)
        client.process.stdin.write.assert_not_called()

    async def test_old_reply_cannot_complete_replacement(self):
        client = NativeClient(threading.Event())
        first, second = asyncio.get_running_loop().create_future(), asyncio.get_running_loop().create_future()
        first.cancel()
        client.pending = {2: second}
        client._reply({'id': 1, 'result': 'old'})
        self.assertFalse(second.done())
        client._reply({'id': 2, 'result': 'new'})
        self.assertEqual(await second, 'new')

    async def test_old_callback_cannot_cancel_replacement(self):
        callback = Mock()
        client = NativeClient(threading.Event(), callback)
        client.generation = 2
        future = asyncio.get_running_loop().create_future()
        client.pending = {1: future}
        client._event('stop', 1)
        client._failed(1)
        client._reply({'id': 1, 'result': 'old'}, 1)
        callback.assert_not_called()
        self.assertFalse(future.done())
        future.cancel()

    async def test_shutdown_failure_does_not_report_success(self):
        client = NativeClient(threading.Event())
        future = asyncio.get_running_loop().create_future()
        client.pending = {1: future}
        client._failed()
        with self.assertRaisesRegex(RuntimeError, 'must not replay'):
            await future
        self.assertEqual(client.pending, {})

    async def test_old_reader_eof_cannot_stop_new_session(self):
        stopped = threading.Event()
        client = NativeClient(stopped)
        client.loop = asyncio.get_running_loop()
        client.generation = 2
        previous = Mock(stdout=io.BytesIO(b''))
        client._read(previous, 1)
        self.assertFalse(stopped.is_set())

    async def test_old_reader_malformed_data_cannot_stop_new_session(self):
        stopped = threading.Event()
        client = NativeClient(stopped)
        client.loop = asyncio.get_running_loop()
        client.generation = 2
        client._read(Mock(stdout=io.BytesIO(b'broken\n')), 1)
        self.assertFalse(stopped.is_set())

    async def test_cancel_does_not_wait_for_effect_database(self):
        from olive.desktop.effect_ledger import EffectLedger
        policy = dict(enabled=True, trusted_tasks=True, keyboard_policy='allow', mouse_policy='allow')
        authority = TaskAuthority(threading.Event())
        grant = authority.issue('Open Kate', 'message', policy, local_user=True)
        with tempfile.TemporaryDirectory() as directory:
            ledger = EffectLedger(Path(directory) / 'ledger.sqlite')
            with ledger.connect() as writer:
                writer.execute('BEGIN IMMEDIATE')
                authority.cancel()
                with self.assertRaises(InterruptedError):
                    authority.check(grant, policy)
                # This writer remains held until after cancellation was effective.
