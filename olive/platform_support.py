"""Explicit native capability limits; shared services stay platform neutral."""
import sys


class PlatformUnavailable(RuntimeError):
    """A curated capability message safe to display in the application."""


def require_windows(feature):
    if sys.platform != 'win32':
        raise PlatformUnavailable(f'{feature} for Linux is not available in this build yet.')


def venv_python():
    return '.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python'


def open_path(path):
    """Ask the native desktop to open an already-authorized local path."""
    import os
    import shutil
    import subprocess
    if sys.platform == 'win32':
        os.startfile(str(path))
        return
    opener = shutil.which('xdg-open')
    if not opener:
        raise PlatformUnavailable('Opening files and folders requires xdg-open on Linux.')
    subprocess.run([opener, str(path)], check=True, timeout=15,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
