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


class CapsLockReleaseTests(unittest.TestCase):
    """Caps Lock is released only around OLIVE's literal text and always restored."""

    def client(self, locked):
        from unittest.mock import patch
        client = EIS.__new__(EIS)
        client.lib, client.stopped, client.ready = Mock(), threading.Event(), set()
        client.lib.ei_device_has_capability.return_value = False
        client.keyboard_pressed, client.keyboard_locked = 0, locked
        client.pump, client.device = Mock(), Mock(return_value='keyboard')
        client.presses, client.chords = [], []
        def press(device, kind, code):
            client.presses.append(code)
            client.keyboard_locked ^= 2 if code == 58 else 0
        client.press = press
        client.synchronize = Mock()
        client.chord_codes = lambda codes: client.chords.append(list(codes))
        return client

    def run_text(self, client, value='hi'):
        from unittest.mock import patch
        with patch('olive.desktop.linux.keymap.caps_lock', return_value=(2, 58)), \
                patch('olive.desktop.linux.keymap.strokes', side_effect=lambda eis, d, text, locked: [(35, False), (23, False)]):
            client.text(value)

    def test_caps_lock_released_for_typing_and_restored(self):
        client = self.client(locked=2)
        self.run_text(client)
        self.assertEqual(client.presses, [58, 58])
        self.assertEqual(client.keyboard_locked, 2)
        self.assertEqual(client.chords, [[35], [23]])

    def test_no_toggle_when_caps_lock_is_off(self):
        client = self.client(locked=0)
        self.run_text(client)
        self.assertEqual(client.presses, [])

    def test_restored_even_when_typing_is_stopped(self):
        client = self.client(locked=2)
        client.stopped.set()
        with self.assertRaises(InterruptedError):
            self.run_text(client)
        self.assertEqual(client.presses, [58, 58])


class KeystrokesFirstTests(unittest.TestCase):
    client = CapsLockReleaseTests.client

    def test_keystrokes_are_used_even_when_native_text_is_advertised(self):
        from unittest.mock import patch
        client = self.client(locked=0)
        client.ready = {'text-device'}
        client.lib.ei_device_has_capability.return_value = True
        with patch('olive.desktop.linux.keymap.caps_lock', return_value=(2, 58)), \
                patch('olive.desktop.linux.keymap.strokes', return_value=[(35, False)]):
            client.text('h')
        self.assertEqual(client.chords, [[35]])
        client.lib.ei_device_text_utf8.assert_not_called()

    def test_native_text_only_for_characters_the_layout_cannot_type(self):
        from unittest.mock import patch
        client = self.client(locked=0)
        client.ready = {'text-device'}
        client.lib.ei_device_has_capability.return_value = True
        client.frame = Mock()
        with patch('olive.desktop.linux.keymap.strokes', side_effect=PermissionError('unavailable')):
            client.text('😀')
        client.lib.ei_device_text_utf8.assert_called_once()
        self.assertEqual(client.chords, [])
