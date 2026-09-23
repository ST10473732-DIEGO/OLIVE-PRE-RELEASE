"""Translate literal text through the compositor-provided XKB keymap.

No assumed QWERTY layout. Preflight the entire string before typing; unsupported
characters produce no input. Clipboard and user's keyboard settings are untouched.
"""
import ctypes as C
import os


def strokes(eis, device, text):
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
    }
    for name, (result, args) in definitions.items():
        function = getattr(xkb, name)
        function.restype, function.argtypes = result, args
    context, mapping = xkb.xkb_context_new(0), None
    try:
        mapping = xkb.xkb_keymap_new_from_string(context, data, 1, 0)
        if not mapping:
            raise ValueError('Compositor keymap could not be read')
        characters = {}
        for code in range(xkb.xkb_keymap_min_keycode(mapping), xkb.xkb_keymap_max_keycode(mapping)+1):
            for level in (0, 1):
                syms = C.POINTER(C.c_uint32)()
                count = xkb.xkb_keymap_key_get_syms_by_level(mapping, code, eis.keyboard_group, level, C.byref(syms))
                if count == 1:
                    char = xkb.xkb_keysym_to_utf32(syms[0])
                    if char >= 32:
                        characters.setdefault(chr(char), (code-8, level == 1))
        characters['\n'], characters['\t'] = (28, False), (15, False)
        if any(char not in characters for char in text):
            raise PermissionError('Literal text includes characters unavailable in the current keyboard layout')
        return [characters[char] for char in text]
    finally:
        if mapping:
            xkb.xkb_keymap_unref(mapping)
        xkb.xkb_context_unref(context)
