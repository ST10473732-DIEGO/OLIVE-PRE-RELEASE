"""Literal typing vs keyboard locks, against a real compositor-style XKB keymap (no desktop input)."""
import ctypes as C
import ctypes.util
import os
import sys
from types import SimpleNamespace
import unittest

from olive.desktop.linux.keymap import KEYPAD, strokes


def keymap_text():
    xkb = C.CDLL('libxkbcommon.so.0')
    xkb.xkb_context_new.restype, xkb.xkb_context_new.argtypes = C.c_void_p, [C.c_int]
    xkb.xkb_keymap_new_from_names.restype = C.c_void_p
    xkb.xkb_keymap_new_from_names.argtypes = [C.c_void_p, C.c_void_p, C.c_int]
    xkb.xkb_keymap_get_as_string.restype, xkb.xkb_keymap_get_as_string.argtypes = C.c_void_p, [C.c_void_p, C.c_int]
    xkb.xkb_keymap_mod_get_index.restype, xkb.xkb_keymap_mod_get_index.argtypes = C.c_uint32, [C.c_void_p, C.c_char_p]

    class Names(C.Structure):
        _fields_ = [(name, C.c_char_p) for name in ('rules', 'model', 'layout', 'variant', 'options')]
    context = xkb.xkb_context_new(0)
    keymap = xkb.xkb_keymap_new_from_names(context, C.byref(Names(b'evdev', b'pc105', b'us', b'', b'')), 0)
    if not keymap:
        raise unittest.SkipTest('No XKB data available')
    text = C.string_at(xkb.xkb_keymap_get_as_string(keymap, 1))
    return text, 1 << xkb.xkb_keymap_mod_get_index(keymap, b'Lock'), 1 << xkb.xkb_keymap_mod_get_index(keymap, b'Mod2')


@unittest.skipUnless(sys.platform == 'linux' and ctypes.util.find_library('xkbcommon'), 'libxkbcommon on Linux')
class KeyboardLockTests(unittest.TestCase):
    def setUp(self):
        text, self.caps, self.num = keymap_text()
        self.fd = os.memfd_create('olive-test-keymap')
        os.write(self.fd, text + b'\0')
        self.addCleanup(os.close, self.fd)
        fn = lambda value: (lambda *args: value)
        lib = SimpleNamespace(ei_device_keyboard_get_keymap=fn(1), ei_keymap_get_fd=fn(self.fd),
                              ei_keymap_get_size=fn(len(text) + 1), ei_keymap_get_type=fn(1))
        self.eis = SimpleNamespace(lib=lib, keyboard_group=0)

    def test_no_lock_types_main_keys_only(self):
        sequence = strokes(self.eis, 1, 'Hi 1/2*3-4+5.')
        self.assertEqual(len(sequence), 13)
        self.assertFalse(any(code in KEYPAD for code, _ in sequence))

    def test_num_lock_alone_does_not_block_or_use_the_keypad(self):
        sequence = strokes(self.eis, 1, 'hello 123', self.num)
        self.assertFalse(any(code in KEYPAD for code, _ in sequence))

    def test_caps_lock_blocks_with_an_exact_reason(self):
        with self.assertRaisesRegex(PermissionError, 'Caps Lock is on'):
            strokes(self.eis, 1, 'hello', self.caps | self.num)

    def test_other_locks_still_block(self):
        with self.assertRaisesRegex(PermissionError, 'other than Num Lock'):
            strokes(self.eis, 1, 'hello', 1 << 7)


if __name__ == '__main__':
    unittest.main()
