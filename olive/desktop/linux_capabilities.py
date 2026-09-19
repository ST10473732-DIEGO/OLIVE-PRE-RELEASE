"""Honest session capabilities; discovery never grants desktop authority."""
import os


def capabilities(env=None):
    env = os.environ if env is None else env
    session = env.get('XDG_SESSION_TYPE', '').lower()
    if session not in {'wayland', 'x11'}:
        session = 'wayland' if env.get('WAYLAND_DISPLAY') else 'x11' if env.get('DISPLAY') else 'unknown'
    return {'session': session, 'compositor': env.get('XDG_CURRENT_DESKTOP', 'unknown'),
        'window_enumeration': 'Not yet integrated' if session == 'x11' else 'Not yet available on this Wayland compositor',
        'screen_capture': 'Requires desktop permission; portal capture not yet integrated',
        'accessibility': 'AT-SPI not yet integrated',
        'remote_input': 'Requires desktop permission; portal input not yet integrated',
        'clipboard': 'Available through explicit application copy/paste; Agent control unavailable',
        'file_dialogs': 'Available through native Electron dialogs',
        'file_open': 'Available through native desktop handlers',
        'application_control': 'Unavailable; no Linux focus/observe/verify adapter',
        'reason': f'Linux {session}: Desktop Control is not yet available. Portal capture and input require desktop permission and are not integrated. File dialogs and explicit copy/paste remain available.'}
