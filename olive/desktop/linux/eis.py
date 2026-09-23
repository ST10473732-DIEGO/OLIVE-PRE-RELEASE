"""libei sender. Only the portal-returned FD is accepted; no Notify fallback.

The installed libei 1.6 ABI is used explicitly. A paused/removed device invalidates
input. Each call emits a frame; release pairs are attempted before disconnect.
"""
import ctypes as C
import os
import select
import time


class EIS:
    def __init__(self, fd, stopped, on_pause, metadata):
        self.lib = C.CDLL('libei.so.1')
        self.stopped, self.on_pause = stopped, on_pause
        self.mapping_id = metadata.get('mapping_id')
        self.region = (*metadata.get('position', ()), *metadata.get('size', ()))
        p, u, b, d = C.c_void_p, C.c_uint32, C.c_bool, C.c_double
        signatures = {
            'ei_new_sender': (p, [p]), 'ei_unref': (p, [p]),
            'ei_configure_name': (None, [p, C.c_char_p]),
            'ei_setup_backend_fd': (C.c_int, [p, C.c_int]),
            'ei_get_fd': (C.c_int, [p]), 'ei_dispatch': (None, [p]),
            'ei_get_event': (p, [p]), 'ei_event_get_type': (C.c_int, [p]),
            'ei_event_get_device': (p, [p]), 'ei_event_get_seat': (p, [p]),
            'ei_event_unref': (p, [p]), 'ei_device_ref': (p, [p]),
            'ei_device_unref': (p, [p]), 'ei_device_has_capability': (b, [p, C.c_int]),
            'ei_device_start_emulating': (None, [p, u]),
            'ei_device_stop_emulating': (None, [p]),
            'ei_device_frame': (None, [p, C.c_uint64]), 'ei_now': (C.c_uint64, [p]),
            'ei_device_pointer_motion_absolute': (None, [p, d, d]),
            'ei_device_get_region_at': (p, [p, d, d]),
            'ei_region_get_mapping_id': (C.c_char_p, [p]),
            'ei_region_get_x': (C.c_int32, [p]),
            'ei_region_get_y': (C.c_int32, [p]),
            'ei_region_get_width': (u, [p]),
            'ei_region_get_height': (u, [p]),
            'ei_device_button_button': (None, [p, u, b]),
            'ei_device_keyboard_key': (None, [p, u, b]),
            'ei_device_scroll_delta': (None, [p, d, d]),
            'ei_device_text_utf8': (None, [p, C.c_char_p]),
        }
        for name, (result, arguments) in signatures.items():
            fn = getattr(self.lib, name)
            fn.restype, fn.argtypes = result, arguments
        self.lib.ei_seat_bind_capabilities.argtypes = [p]
        self.lib.ei_seat_bind_capabilities.restype = None
        self.context = self.lib.ei_new_sender(None)
        self.devices, self.ready, self.held = set(), set(), set()
        self.sequence = 0
        self.keyboard_group = 0
        self.keyboard_modifiers = 0
        self.lib.ei_configure_name(self.context, b'OLIVE local user-directed control')
        # Transfer a duplicate to libei; retain no portal FD in this caller.
        try:
            if self.lib.ei_setup_backend_fd(self.context, os.dup(fd)) != 0:
                raise RuntimeError('EIS connection failed')
        finally:
            os.close(fd)
        self.fd = self.lib.ei_get_fd(self.context)

    def pump(self):
        self.lib.ei_dispatch(self.context)
        while event := self.lib.ei_get_event(self.context):
            try:
                kind = self.lib.ei_event_get_type(event)
                device = self.lib.ei_event_get_device(event)
                if kind == 3:  # EI_EVENT_SEAT_ADDED
                    seat = self.lib.ei_event_get_seat(event)
                    self.lib.ei_seat_bind_capabilities(seat, C.c_int(2), C.c_int(4),
                        C.c_int(16), C.c_int(32), C.c_int(64), C.c_void_p())
                elif kind == 5:  # DEVICE_ADDED
                    self.devices.add(self.lib.ei_device_ref(device))
                elif kind == 8 and not self.stopped.is_set():  # DEVICE_RESUMED
                    self.sequence += 1
                    self.lib.ei_device_start_emulating(device, self.sequence)
                    self.ready.add(device)
                elif kind == 9:  # EI_EVENT_KEYBOARD_MODIFIERS
                    for suffix in ('mods_depressed', 'mods_latched', 'mods_locked', 'group'):
                        fn = getattr(self.lib, 'ei_event_keyboard_get_xkb_' + suffix)
                        fn.restype, fn.argtypes = C.c_uint32, [C.c_void_p]
                    self.keyboard_group = self.lib.ei_event_keyboard_get_xkb_group(event)
                    self.keyboard_modifiers = (self.lib.ei_event_keyboard_get_xkb_mods_depressed(event) |
                        self.lib.ei_event_keyboard_get_xkb_mods_latched(event) |
                        self.lib.ei_event_keyboard_get_xkb_mods_locked(event))
                elif kind in (2, 4, 6, 7):
                    # Never auto-resume after pause or topology change.
                    self.ready.discard(device)
                    self.stopped.set()
                    self.on_pause('input-paused')
            finally:
                self.lib.ei_event_unref(event)

    def device(self, capability):
        deadline = time.monotonic() + 2
        while True:
            self.pump()
            if self.stopped.is_set():
                raise InterruptedError('Input stopped or paused')
            matches = [d for d in self.ready if self.lib.ei_device_has_capability(d, capability)]
            if matches or time.monotonic() >= deadline:
                break
            # Complete the EIS connect/seat/device/resume handshake before input.
            # Waiting only on GLib's periodic pump starves inside native calls.
            select.select([self.fd], [], [], min(.05, max(0, deadline-time.monotonic())))
        if len(matches) != 1:
            raise PermissionError(f'EIS capability {capability}: {len(matches)} matching devices; {len(self.ready)} resumed devices')
        return matches[0]

    def frame(self, device):
        self.lib.ei_device_frame(device, self.lib.ei_now(self.context))
        self.lib.ei_dispatch(self.context)

    def move(self, x, y):
        pointer = self.device(2)
        region = self.lib.ei_device_get_region_at(pointer, x, y)
        if not region:
            raise ValueError('Point is outside the compositor input regions')
        mapping = self.lib.ei_region_get_mapping_id(region)
        if not self.mapping_id or not mapping or mapping.decode('utf-8') != self.mapping_id:
            raise PermissionError('EIS region is not bound to the approved capture stream')
        actual = tuple(getattr(self.lib, 'ei_region_get_' + key)(region)
                       for key in ('x', 'y', 'width', 'height'))
        if actual != self.region:
            raise PermissionError('Compositor display geometry changed; start a new observation session')
        self.lib.ei_device_pointer_motion_absolute(pointer, x, y)
        self.frame(pointer)

    def click(self, x, y):
        self.move(x, y)
        button = self.device(32)
        self.press(button, 'button', 272)

    def press(self, device, kind, code):
        fn = self.lib.ei_device_button_button if kind == 'button' else self.lib.ei_device_keyboard_key
        self.held.add((device, kind, code))
        try:
            fn(device, code, True)
            self.frame(device)
        finally:
            fn(device, code, False)
            self.frame(device)
            self.held.discard((device, kind, code))

    def key(self, name):
        keys = {'Tab': 15, 'Escape': 1, 'Enter': 28, 'Backspace': 14,
                'Down': 108, 'Up': 103, 'Left': 105, 'Right': 106}
        if name not in keys:
            raise ValueError('Unsupported key; commands and arbitrary chords are not accepted')
        self.press(self.device(4), 'key', keys[name])

    def text(self, value):
        if not isinstance(value, str) or not 1 <= len(value) <= 4000 or '\x00' in value:
            raise ValueError('Invalid literal input')
        # Native Unicode text only when advertised; no guessed keymap or clipboard.
        self.pump()
        if any(self.lib.ei_device_has_capability(d, 64) for d in self.ready):
            device = self.device(64)
            self.lib.ei_device_text_utf8(device, value.encode('utf-8'))
            self.frame(device)
            return
        from .keymap import strokes
        device = self.device(4)
        if self.keyboard_modifiers:
            raise PermissionError('Release keyboard modifiers before literal input')
        sequence = strokes(self, device, value)
        for code, shift in sequence:
            if self.stopped.is_set():
                raise InterruptedError('Literal input stopped')
            self.chord_codes([42, code] if shift else [code])
            # Bound event bursts for native completion/edit controls. Waiting on
            # Stop, rather than sleeping blindly, keeps cancellation immediate.
            if self.stopped.wait(.008):
                raise InterruptedError('Literal input stopped')

    def chord_codes(self, codes):
        device = self.device(4)
        held = []
        try:
            for code in codes:
                if self.stopped.is_set():
                    raise InterruptedError('Input stopped')
                held.append(code)
                self.held.add((device, 'key', code))
                self.lib.ei_device_keyboard_key(device, code, True)
                self.frame(device)
        finally:
            for code in reversed(held):
                self.lib.ei_device_keyboard_key(device, code, False)
                self.frame(device)
                self.held.discard((device, 'key', code))

    def browser_key(self, action):
        # Typed semantic operations; no caller-supplied arbitrary chords.
        codes = {'new_tab': [29, 20], 'address': [29, 38], 'submit': [28]}
        if action not in codes:
            raise ValueError('Unknown browser key operation')
        self.chord_codes(codes[action])

    def editor_key(self, action):
        codes = {'new_document': [29, 49], 'save_as': [29, 42, 31]}
        if action not in codes:
            raise ValueError('Unknown editor key operation')
        self.chord_codes(codes[action])

    def scroll(self, dy):
        if type(dy) not in (int, float) or not -600 <= dy <= 600:
            raise ValueError('Scroll out of bounds')
        device = self.device(16)
        self.lib.ei_device_scroll_delta(device, 0, dy)
        self.frame(device)

    def close(self):
        if not self.context:
            return
        for device, kind, code in tuple(self.held):
            fn = self.lib.ei_device_button_button if kind == 'button' else self.lib.ei_device_keyboard_key
            fn(device, code, False)
            self.frame(device)
        self.held.clear()
        for device in self.ready:
            self.lib.ei_device_stop_emulating(device)
        for device in self.devices:
            self.lib.ei_device_unref(device)
        self.lib.ei_unref(self.context)
        self.context = None
        self.devices.clear()
        self.ready.clear()
