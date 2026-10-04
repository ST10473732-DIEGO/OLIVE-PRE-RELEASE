"""The OLIVE-owned image engine stops after an idle period, and never while it is in use."""
import asyncio
import unittest
from unittest import mock

from olive.services.media_engines import ComfyEngine, MediaEngines
from olive.services.media_workflows import IMAGE_WORKFLOWS


class FakeRuntime:
    def __init__(self, owned=True):
        self.host, self.port, self.root, self.state = 'http://127.0.0.1:8188', 8188, '/fixture/ComfyUI', 'idle'
        self.running = owned
        self.mine = owned
        self.closed = 0
        self.started = 0
        self.close_gate = None

    def owned(self):
        return self.mine and self.running

    def installed(self):
        return True

    async def ready(self):
        return self.running

    async def start_for(self, url):
        self.started += 1
        self.running = self.mine = True

    async def close(self):
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.mine:
            self.running = False
            self.closed += 1


class FakeClient:
    def __init__(self):
        self.queued = False
        self.fail = False

    async def busy(self):
        if self.fail:
            raise RuntimeError('unreachable')
        return self.queued

    async def inventory(self, workflows):
        return {'version': '0.35.0', 'inputs': {}, 'modules': {}}

    async def release_idle(self):
        return None


class IdleLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def engine(self, owned=True, seconds=0.02):
        engine = ComfyEngine('image', FakeRuntime(owned), IMAGE_WORKFLOWS, idle_stop=True)
        engine.client = FakeClient()
        engine.lease = asyncio.Lock()
        engine.idle_seconds = lambda: seconds
        return engine

    def setUp(self):
        patcher = mock.patch.multiple(ComfyEngine, IDLE_FLOOR=0, IDLE_RETRY=0.02)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_grace_follows_the_model_keep_alive_with_a_floor(self):
        with mock.patch.object(ComfyEngine, 'IDLE_FLOOR', 60):
            engine = self.engine(seconds=300)
            self.assertEqual(engine.grace(), 300)
            engine.idle_seconds = lambda: 0  # keep_alive 0 still gives the engine a minute.
            self.assertEqual(engine.grace(), 60)
            engine.idle_seconds = lambda: 1 / 0
            self.assertEqual(engine.grace(), 300)

    async def test_an_idle_owned_engine_stops(self):
        engine = self.engine()
        engine.touch()
        await asyncio.sleep(.1)
        self.assertEqual(engine.runtime.closed, 1)
        self.assertEqual(engine.idle_stops, 1)
        self.assertFalse(engine.status()['owned'])
        self.assertNotIn(engine.status()['state'], ('ready', 'busy', 'failed'))  # Starts again on the next request.

    async def test_an_active_job_prevents_shutdown(self):
        engine = self.engine()
        engine.active = True
        self.assertEqual(await engine.stop_if_idle(), 'busy')
        self.assertEqual(engine.runtime.closed, 0)

    async def test_a_held_lease_prevents_shutdown(self):
        engine = self.engine()
        async with engine.lease:  # Chat, Media tools, remote Connect and text inference all hold this.
            self.assertEqual(await engine.stop_if_idle(), 'busy')
        self.assertEqual(engine.runtime.closed, 0)

    async def test_work_queued_by_another_client_prevents_shutdown(self):
        engine = self.engine()
        engine.client.queued = True
        self.assertEqual(await engine.stop_if_idle(), 'busy')
        engine.client.queued, engine.client.fail = False, True
        self.assertEqual(await engine.stop_if_idle(), 'busy')  # Unverifiable is not idle.
        self.assertEqual(engine.runtime.closed, 0)
        self.assertFalse(engine.lease.locked())

    async def test_busy_is_retried_until_idle(self):
        engine = self.engine()
        engine.client.queued = True
        engine.touch()
        await asyncio.sleep(.1)
        self.assertEqual(engine.runtime.closed, 0)
        engine.client.queued = False
        await asyncio.sleep(.1)
        self.assertEqual(engine.runtime.closed, 1)

    async def test_an_external_engine_is_never_stopped(self):
        engine = self.engine(owned=False)
        engine.runtime.running = True  # Someone else's server on the port.
        engine.touch()
        self.assertIsNone(engine._idle_task)
        self.assertEqual(await engine.stop_if_idle(), 'not_owned')
        self.assertTrue(engine.runtime.running)

    async def test_disabled_for_the_video_engine(self):
        engine = self.engine()
        engine.idle_stop = False
        engine.touch()
        self.assertIsNone(engine._idle_task)

    async def test_new_use_restarts_the_countdown(self):
        engine = self.engine(seconds=0.4)
        engine.touch()
        for _ in range(4):
            await asyncio.sleep(.1)
            engine.touch()
        self.assertEqual(engine.runtime.closed, 0)
        await asyncio.sleep(.8)
        self.assertEqual(engine.runtime.closed, 1)

    async def test_next_generation_restarts_a_stopped_engine(self):
        engine = self.engine()
        self.assertEqual(await engine.stop_if_idle(), 'stopped')
        engine.used = True
        await engine.prepare(lambda text: None)
        self.assertEqual(engine.runtime.started, 1)
        self.assertTrue(engine.runtime.owned())
        self.assertIsNotNone(engine._idle_task)  # The restarted engine has a countdown again.
        engine._cancel_idle()

    async def test_shutdown_race_a_job_waits_then_restarts(self):
        engine = self.engine()
        engine.used = True
        engine.runtime.close_gate = asyncio.Event()
        order = []

        async def job():
            async with engine.lease:  # As ChatMediaService.generate does.
                order.append('job')
                await engine.prepare(lambda text: None)
        stopping = asyncio.create_task(engine.stop_if_idle())
        await asyncio.sleep(0)
        self.assertTrue(engine.lease.locked())  # The stop holds the lease while the process goes away.
        waiting = asyncio.create_task(job())
        await asyncio.sleep(.02)
        self.assertEqual(order, [])  # The job did not start on a half-stopped engine.
        engine.runtime.close_gate.set()
        self.assertEqual(await stopping, 'stopped')
        await waiting
        self.assertEqual(order, ['job'])
        self.assertEqual((engine.runtime.closed, engine.runtime.started), (1, 1))
        engine._cancel_idle()

    async def test_cancelling_the_countdown_during_a_stop_still_finishes_the_stop(self):
        engine = self.engine()
        engine.runtime.close_gate = asyncio.Event()
        stopping = asyncio.create_task(engine.stop_if_idle())
        await asyncio.sleep(0)
        stopping.cancel()
        engine.runtime.close_gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await stopping
        await asyncio.sleep(0)
        self.assertEqual(engine.runtime.closed, 1)  # Shielded: never a half-stopped process.
        self.assertFalse(engine.lease.locked())

    async def test_app_shutdown_cancels_the_countdown_and_stops_the_owned_process(self):
        engine = self.engine(seconds=10)
        engine.touch()
        task = engine._idle_task
        await engine.close()
        await asyncio.sleep(0)
        self.assertTrue(task.cancelled())
        self.assertEqual(engine.runtime.closed, 1)

    async def test_media_engines_share_the_residency_lease_and_keep_alive(self):
        class Residency:
            lock = asyncio.Lock()

            def policy(self):
                return {'keep_alive': 420}
        from olive.services.runtime_discovery import from_environment
        engines = MediaEngines('/nonexistent-olive-test', from_environment({}))
        engines.share_lease(Residency())
        self.assertIs(engines.image.lease, Residency.lock)
        self.assertIs(engines.video.lease, Residency.lock)
        with mock.patch.object(ComfyEngine, 'IDLE_FLOOR', 60):
            self.assertEqual(engines.image.grace(), 420)
        self.assertTrue(engines.image.idle_stop)
        self.assertFalse(engines.video.idle_stop)


if __name__ == '__main__':
    unittest.main()
