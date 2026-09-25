"""Translate literal text through the compositor-provided XKB keymap.

No assumed QWERTY layout. Preflight the entire string before typing; unsupported
characters produce no input. Clipboard and user's keyboard settings are untouched
(a temporarily released Caps Lock is restored by the caller).
"""
from contextlib import contextmanager
import ctypes as C
import os


# Keypad keys (evdev codes) depend on Num Lock; literal text never uses them.
KEYPAD = frozenset({55, *range(71, 84), 96, 98, 117, 118, 121, 179, 180})
CAPS_LOCK_KEYSYM = 0xffe5


@contextmanager
def _keymap(eis, device):
    lib = eis.lib
    pointer = C.c_void_p
    for name, result, args in (
        ('ei_device_keyboard_get_keymap', pointer, [pointer]),
        ('ei_keymap_get_fd', C.c_int, [pointer]),
        ('ei_keymap_get_size', C.c_size_t, [pointer]),
        ('ei_keymap_get_type', C.c_int, [pointer])):
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args
    keymap = lib.ei_device_keyboard_get_keymap(device)
    if not keymap or lib.ei_keymap_get_type(keymap) != 1:
        raise PermissionError('EIS has no supported XKB keymap')
    size = lib.ei_keymap_get_size(keymap)
    if not 1 <= size <= 4 * 1024 * 1024:
        raise ValueError('Invalid EIS keymap size')
    data = os.pread(lib.ei_keymap_get_fd(keymap), size, 0)
    xkb = C.CDLL('libxkbcommon.so.0')
    definitions = {
        'xkb_context_new': (pointer, [C.c_int]), 'xkb_context_unref': (None, [pointer]),
        'xkb_keymap_new_from_string': (pointer, [pointer, C.c_char_p, C.c_int, C.c_int]),
        'xkb_keymap_unref': (None, [pointer]),
        'xkb_keymap_min_keycode': (C.c_uint32, [pointer]),
        'xkb_keymap_max_keycode': (C.c_uint32, [pointer]),
        'xkb_keymap_key_get_syms_by_level': (C.c_int, [pointer, C.c_uint32, C.c_uint32, C.c_uint32, C.POINTER(C.POINTER(C.c_uint32))]),
        'xkb_keysym_to_utf32': (C.c_uint32, [C.c_uint32]),
        'xkb_keymap_mod_get_index': (C.c_uint32, [pointer, C.c_char_p]),
        'xkb_state_new': (pointer, [pointer]), 'xkb_state_unref': (None, [pointer]),
        'xkb_state_update_mask': (C.c_int, [pointer] + [C.c_uint32] * 6),
        'xkb_state_key_get_utf32': (C.c_uint32, [pointer, C.c_uint32]),
    }
    for name, (result, args) in definitions.items():
        function = getattr(xkb, name)
        function.restype, function.argtypes = result, args
    context, mapping = xkb.xkb_context_new(0), None
    try:
        mapping = xkb.xkb_keymap_new_from_string(context, data, 1, 0)
        if not mapping:
            raise ValueError('Compositor keymap could not be read')
        yield xkb, mapping
    finally:
        if mapping:
            xkb.xkb_keymap_unref(mapping)
        xkb.xkb_context_unref(context)


def caps_lock(eis, device):
    """(Caps Lock modifier mask, evdev code of the key that toggles it or None)."""
    with _keymap(eis, device) as (xkb, mapping):
        index = xkb.xkb_keymap_mod_get_index(mapping, b'Lock')
        mask = 1 << index if index < 32 else 0
        for code in range(xkb.xkb_keymap_min_keycode(mapping), xkb.xkb_keymap_max_keycode(mapping) + 1):
            syms = C.POINTER(C.c_uint32)()
            count = xkb.xkb_keymap_key_get_syms_by_level(mapping, code, eis.keyboard_group, 0, C.byref(syms))
            if count == 1 and syms[0] == CAPS_LOCK_KEYSYM:
                return mask, code - 8
        return mask, None


def strokes(eis, device, text, locked=0):
    with _keymap(eis, device) as (xkb, mapping):
        index = xkb.xkb_keymap_mod_get_index(mapping, b'Shift')
        if index >= 32:
            raise PermissionError('The keyboard layout has no Shift modifier; nothing was typed')
        shift = 1 << index
        # Resolve every character under the compositor's current locks (Caps Lock,
        # Num Lock, ...): with Caps Lock on, a lowercase letter is Shift+key. The
        # typed text is still read back and verified.
        state = xkb.xkb_state_new(mapping)
        if not state:
            raise ValueError('Keyboard state could not be created')
        characters = {}
        try:
            for code in range(xkb.xkb_keymap_min_keycode(mapping), xkb.xkb_keymap_max_keycode(mapping)+1):
                if code - 8 in KEYPAD:
                    continue
                for shifted in (False, True):
                    xkb.xkb_state_update_mask(state, shift if shifted else 0, 0, locked, 0, 0, eis.keyboard_group)
                    char = xkb.xkb_state_key_get_utf32(state, code)
                    if char >= 32:
                        characters.setdefault(chr(char), (code - 8, shifted))
        finally:
            xkb.xkb_state_unref(state)
        characters['\n'], characters['\t'] = (28, False), (15, False)
        if any(char not in characters for char in text):
            raise PermissionError('Literal text includes characters unavailable in the current keyboard layout')
        return [characters[char] for char in text]
