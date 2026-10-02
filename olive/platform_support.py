"""Explicit native capability limits; shared services stay platform neutral."""
import sys


class PlatformUnavailable(RuntimeError):
    """A curated capability message safe to display in the application."""


# Non-Windows platforms a Windows-only feature can be reached from, as users name them.
PLATFORM_LABELS = {'linux': 'Linux', 'darwin': 'macOS'}


def platform_label(platform=None):
    platform = sys.platform if platform is None else platform
    return PLATFORM_LABELS.get(platform, platform)


def unavailable_message(feature, label=None):
    """Truthful on every platform; bridge/public_errors.py allowlists the same text."""
    return f'{feature} is not available on {label or platform_label()} in this build yet.'


def require_windows(feature):
    if sys.platform != 'win32':
        raise PlatformUnavailable(unavailable_message(feature))


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
        raise PlatformUnavailable('Opening files and folders requires xdg-open on Linux.' if sys.platform == 'linux'
                                  else unavailable_message('Opening files and folders'))
    subprocess.run([opener, str(path)], check=True, timeout=15,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
