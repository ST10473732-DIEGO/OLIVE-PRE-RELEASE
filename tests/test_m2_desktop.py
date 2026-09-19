"""Desktop adapters use inert providers/owned files; never the real desktop."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.bridge.desktop_routes import capture_preview


class DesktopBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-m2-desktop-')
        self.host = Host(lambda event: None)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def test_status_does_not_observe_and_disabled_operations_fail_before_provider(self):
        self.s.desktop.provider.observe = AsyncMock(side_effect=AssertionError('Real observation forbidden'))
        value = await self.host.execute('desktop.status', {})
        self.assertFalse(value['active'])
        self.assertFalse(value['can_resume'])
        self.assertFalse(value['can_pause'])
        self.assertIsNone(value['session'])
        self.s.desktop.settings = {}
        self.s.desktop.launcher.open = AsyncMock(side_effect=AssertionError('Real launch forbidden'))
        with self.assertRaises((PermissionError, InterruptedError)):
            await self.host.execute('desktop.open_application', {'application_id': 'fixture'})
        self.s.desktop.provider.observe.assert_not_awaited()
        self.s.desktop.launcher.open.assert_not_awaited()

    async def test_emergency_stop_cancels_owned_operation_without_model_reasoning(self):
        pending = asyncio.create_task(asyncio.Event().wait())
        self.s.desktop.operation = pending
        self.host.emergency_stop()
        self.assertTrue(self.s.desktop.stop_event.is_set())
        await self.host.execute('desktop.stop', {})
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.s.desktop.operation = None
        await self.host.execute('desktop.reset', {})
        self.assertFalse(self.s.desktop.stop_event.is_set())

    async def test_manual_fields_reach_existing_controller_unchanged(self):
        self.s.desktop.perform = AsyncMock(return_value={'verified':False,'state':'fixture'})
        args = {'action':'invoke','target':{'runtime_id':[1,2]},'arguments':{},'expected':{'name':'Fixture complete'}}
        result = await self.host.execute('desktop.perform', args)
        self.s.desktop.perform.assert_awaited_once_with(**args)
        self.assertFalse(result['verified'])

    async def test_capture_preview_requires_owned_record_and_bounds_transport(self):
        from PIL import Image
        root = self.s.desktop.screenshots.root
        root.mkdir(parents=True)
        path = root / 'fixture.png'
        Image.new('RGB', (1600,1200), 'navy').save(path)
        self.s.desktop.screenshots.records['fixture'] = {'path':str(path),'width':1600,'height':1200}
        value = capture_preview(self.s, 'fixture')
        self.assertTrue(value['image'].startswith('data:image/jpeg;base64,'))
        self.assertLessEqual(value['width'],1200)
        self.assertLess(len(value['image']),800050)
        self.assertNotIn('path',value)
        with self.assertRaises(ValueError):
            capture_preview(self.s, 'unapproved-path')
        outside = Path(self.temp.name) / 'outside.png'
        Image.new('RGB',(2,2)).save(outside)
        self.s.desktop.screenshots.records['outside'] = {'path':str(outside),'width':2,'height':2}
        with self.assertRaises(ValueError):
            capture_preview(self.s, 'outside')
