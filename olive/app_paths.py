"""One authority for where OLIVE is installed and where it may write outside the profile.

The profile (chats, settings, stores) keeps its own resolver:
olive.identity.resolve_profile. Everything else OLIVE writes outside the profile
(OLIVE-owned runtimes, media model stores, Studio toolchains, start locks) lives
under one per-user data root. In a packaged build the installation (Program Files,
an AppImage mount, a macOS .app bundle, resources/backend) is read-only to OLIVE.

    user data root   Linux    $XDG_DATA_HOME/olive (default ~/.local/share/olive)
                     Windows  %LOCALAPPDATA%\\OLIVE
                     macOS    ~/Library/Application Support/OLIVE
    runtimes         <root>/runtime
    media models     <root>/models
    toolchains       <root>/toolchains
    start locks      Linux: $XDG_RUNTIME_DIR, else ~/.cache/olive; elsewhere <root>/locks
    temporary jobs   the OS temporary directory, or profile-owned staging folders

The Linux locations are the ones the source launcher has always used, so an
existing machine keeps its runtimes and models in place.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
import sys
import tempfile

PACKAGE = Path(__file__).resolve().parent
INSTALL_ROOT = PACKAGE.parent  # Repository checkout, or the packaged backend root.
BACKEND_MANIFEST = 'olive-backend.json'
DIRECTORY = {'win32': 'OLIVE', 'darwin': 'OLIVE'}  # Linux keeps the lowercase XDG name.


def _platform(platform=None):
    return sys.platform if platform is None else platform


def _path_type(platform, sample=None):
    # Native Path for the host; pure paths when asked about another OS (tests, docs).
    # A host-absolute sample means "lay that OS's folders out on this machine" (tests).
    if (platform == 'win32') == (os.name == 'nt'):
        return Path
    if sample and os.name != 'nt' and PurePosixPath(str(sample)).is_absolute():
        return Path
    return PureWindowsPath if platform == 'win32' else PurePosixPath


def packaged(root=None) -> bool:
    """True for a packaged backend artefact, which always carries its build manifest."""
    return (Path(root) if root is not None else INSTALL_ROOT).joinpath(BACKEND_MANIFEST).is_file()


def backend_manifest(root=None) -> dict | None:
    try:
        return json.loads((Path(root) if root is not None else INSTALL_ROOT).joinpath(BACKEND_MANIFEST)
                          .read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def user_data_root(environ=None, platform=None, home=None) -> PurePath:
    env = os.environ if environ is None else environ
    platform = _platform(platform)
    if platform == 'win32':
        local = env.get('LOCALAPPDATA', '')
        kind = _path_type(platform, local or home)
        base_home = kind(home) if home is not None else kind(Path.home())
        absolute = bool(local) and (PureWindowsPath(local).is_absolute() or (kind is Path and Path(local).is_absolute()))
        base = kind(local) if absolute else base_home / 'AppData' / 'Local'
        return base / DIRECTORY['win32']
    kind = _path_type(platform)
    base_home = kind(home) if home is not None else kind(Path.home())
    if platform == 'darwin':
        return base_home / 'Library' / 'Application Support' / DIRECTORY['darwin']
    xdg = env.get('XDG_DATA_HOME', '')
    base = kind(xdg) if xdg and PurePosixPath(xdg).is_absolute() else base_home / '.local' / 'share'
    return base / 'olive'


def runtime_root(environ=None, platform=None, home=None) -> PurePath:
    return user_data_root(environ, platform, home) / 'runtime'


def media_models_root(environ=None, platform=None, home=None) -> PurePath:
    return user_data_root(environ, platform, home) / 'models'


def toolchains_root(environ=None, platform=None, home=None) -> PurePath:
    return user_data_root(environ, platform, home) / 'toolchains'


def lock_directory(environ=None, platform=None, home=None) -> PurePath:
    env = os.environ if environ is None else environ
    platform = _platform(platform)
    kind = _path_type(platform)
    if platform.startswith('linux'):
        runtime = env.get('XDG_RUNTIME_DIR', '')
        if runtime and PurePosixPath(runtime).is_absolute():
            return kind(runtime)
        return (kind(home) if home is not None else kind(Path.home())) / '.cache' / 'olive'
    return user_data_root(env, platform, home) / 'locks'


def temporary_root() -> Path:
    return Path(tempfile.gettempdir())


def source_toolchains(root=None) -> Path | None:
    """The repository's ignored .toolchains folder: a source-checkout fallback only."""
    root = Path(root) if root is not None else INSTALL_ROOT
    return None if packaged(root) else root / '.toolchains'


def toolchain_directories(environ=None, platform=None, home=None, root=None) -> list[Path]:
    """Where to look for installed developer toolchains, most preferred first."""
    found = [Path(toolchains_root(environ, platform, home))]
    legacy = source_toolchains(root)
    if legacy is not None:
        found.append(legacy)
    return found


def inside_installation(path, root=None) -> bool:
    root = Path(root) if root is not None else INSTALL_ROOT
    try:
        Path(path).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def require_writable_location(path, root=None):
    """Refuse writes into a packaged installation (read-only by contract)."""
    if packaged(root) and inside_installation(path, root):
        raise PermissionError('OLIVE does not write inside its installation; use the per-user data folder')
    return Path(path)


def app_executable(environ=None) -> str:
    """The launcher a desktop entry or login item should start (set by the Electron shell)."""
    env = os.environ if environ is None else environ
    return env.get('OLIVE_APP_EXECUTABLE', '')
