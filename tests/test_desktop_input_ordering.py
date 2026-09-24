"""Ordering and image-coordinate regression fixtures; no desktop control."""
import base64
import io
import threading
import unittest
from unittest.mock import Mock
from PIL import Image
from olive.desktop.linux.eis import EIS
from olive.desktop.linux.browser_navigation import document_frame


class InputOrderingTests(unittest.TestCase):
    def test_roundtrip_consumes_modifier_release_without_resetting_state(self):
        client = EIS.__new__(EIS)
        client.context = 1; client.lib = Mock(); client.stopped = threading.Event()
        client.last_pong = 0; client.keyboard_modifiers = 1
        client.lib.ei_new_ping.return_value = 12; client.lib.ei_ping_get_id.return_value = 9
        def dispatch():
            client.keyboard_modifiers = 0; client.last_pong = 9
        client.pump = Mock(side_effect=dispatch)
        client.synchronize()
        self.assertEqual(client.keyboard_modifiers, 0)
        client.lib.ei_ping.assert_called_once_with(12)
        client.lib.ei_ping_unref.assert_called_once_with(12)
        client.last_pong = 0; client.keyboard_modifiers = 1
        client.pump.side_effect = lambda: setattr(client, 'last_pong', 9)
        client.synchronize()
        self.assertEqual(client.keyboard_modifiers, 1)  # A real held modifier survives.

    def test_stop_interrupts_ordering_and_releases_ping(self):
        client = EIS.__new__(EIS)
        client.context = 1; client.lib = Mock(); client.stopped = threading.Event()
        client.last_pong = 0; client.lib.ei_ping_get_id.return_value = 9
        client.pump = Mock(side_effect=client.stopped.set)
        with self.assertRaises(InterruptedError): client.synchronize()
        client.lib.ei_ping_unref.assert_called_once()

    def test_document_crop_excludes_chrome_and_maps_scaled_global_bounds(self):
        pixels = Image.new('RGB',(800,600),'red')
        pixels.paste('green',(0,100,800,600)); buffer=io.BytesIO();pixels.save(buffer,format='PNG')
        frame={'png':base64.b64encode(buffer.getvalue()).decode(),'width':800,'height':600,
               'window':{'bounds':[1920,0,1600,1200]}}
        doc={'bounds':[1920,200,1600,1000],'ready':True}
        result=document_frame(frame,[doc])
        self.assertEqual((result['width'],result['height']),(800,500))
        with Image.open(io.BytesIO(base64.b64decode(result['png']))) as cropped:
            self.assertEqual(cropped.getpixel((0,0)),(0,128,0))
        for docs in ([],[doc,doc],[{**doc,'ready':False}]):
            with self.assertRaises(ValueError):document_frame(frame,docs)
