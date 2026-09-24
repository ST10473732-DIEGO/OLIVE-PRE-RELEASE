import unittest
from unittest.mock import AsyncMock
from olive.services.gui_model_service import wait_for_vram


class HandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_observes_delayed_release_without_replaying_inference(self):
        clock = [0.]
        async def wait(seconds): clock[0] += seconds
        query = AsyncMock(side_effect=[7000, 8000, 15000])
        self.assertEqual(await wait_for_vram(query,clock=lambda:clock[0],wait=wait),[7000,8000,15000])
        self.assertAlmostEqual(clock[0],.2)

    async def test_external_allocation_exhausts_finite_observation_budget(self):
        clock = [0.]
        async def wait(seconds): clock[0] += seconds
        with self.assertRaises(MemoryError):
            await wait_for_vram(AsyncMock(return_value=7000),clock=lambda:clock[0],wait=wait)
        self.assertAlmostEqual(clock[0],3.)
