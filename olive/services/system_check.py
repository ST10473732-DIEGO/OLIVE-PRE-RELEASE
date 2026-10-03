"""Read-only hardware facts for first-run setup.

Nothing here claims a configuration works unless OLIVE has validated it. A value
that cannot be measured is reported as None ("Not measurable"), never guessed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform as host_platform
import shutil
import subprocess
import sys

from .. import app_paths
from .runtime_manifest import platform_target

# Combinations OLIVE has validated end to end (the Linux reference machine).
VERIFIED = {('linux-x86_64', 'nvidia')}
PCI_VENDORS = {'0x10de': 'nvidia', '0x1002': 'amd', '0x8086': 'intel'}
VENDOR_LABELS = {'nvidia': 'NVIDIA', 'amd': 'AMD', 'intel': 'Intel', 'apple': 'Apple'}


def _run(argv, timeout=5) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False,
                                stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout if result.returncode == 0 else ''


def operating_system(platform=None) -> dict:
    platform = sys.platform if platform is None else platform
    name, version = host_platform.system(), host_platform.release()
    if platform.startswith('linux'):
        try:
            release = host_platform.freedesktop_os_release()
            name = release.get('PRETTY_NAME') or release.get('NAME') or 'Linux'
        except OSError:
            name = 'Linux'
    elif platform == 'darwin':
        name, version = 'macOS', host_platform.mac_ver()[0] or version
    elif platform == 'win32':
        name, version = 'Windows', host_platform.version()
    return {'name': name, 'version': version, 'architecture': host_platform.machine()}


def cpu(platform=None) -> dict:
    platform = sys.platform if platform is None else platform
    label = ''
    if platform.startswith('linux'):
        try:
            for line in Path('/proc/cpuinfo').read_text(encoding='utf-8', errors='replace').splitlines():
                if line.lower().startswith('model name'):
                    label = line.split(':', 1)[1].strip()
                    break
        except OSError:
            pass
    elif platform == 'darwin':
        label = _run(['/usr/sbin/sysctl', '-n', 'machdep.cpu.brand_string']).strip()
    if not label:
        label = host_platform.processor() or ''
    try:
        import psutil
        physical = psutil.cpu_count(logical=False)
    except Exception:
        physical = None
    return {'name': label or None, 'logical_cores': os.cpu_count(), 'physical_cores': physical}


def memory() -> int | None:
    try:
        import psutil
        return int(psutil.virtual_memory().total)
    except Exception:
        return None


def _nvidia() -> list[dict]:
    executable = shutil.which('nvidia-smi')
    if not executable:
        return []
    gpus = []
    for line in _run([executable, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits']).splitlines():
        fields = [v.strip() for v in line.split(',')]
        if len(fields) == 2 and fields[0]:
            try:
                vram = int(float(fields[1])) * 1024 * 1024
            except ValueError:
                vram = None
            gpus.append({'vendor': 'nvidia', 'name': fields[0], 'vram_bytes': vram, 'source': 'nvidia-smi'})
    return gpus


def _linux_drm(root=Path('/sys/class/drm')) -> list[dict]:
    gpus, seen = [], set()
    try:
        cards = sorted(p for p in root.iterdir() if p.name.startswith('card') and '-' not in p.name)
    except OSError:
        return gpus
    for card in cards:
        device = card / 'device'
        try:
            vendor = PCI_VENDORS.get((device / 'vendor').read_text().strip())
            key = os.path.realpath(device)
        except OSError:
            continue
        if not vendor or key in seen:
            continue
        seen.add(key)
        vram = None
        try:
            vram = int((device / 'mem_info_vram_total').read_text().strip())  # amdgpu only.
        except (OSError, ValueError):
            pass
        name = None
        try:
            slot = Path(key).name
            name = _run(['lspci', '-s', slot], timeout=3).split(': ', 1)[-1].strip() or None
        except Exception:
            name = None
        gpus.append({'vendor': vendor, 'name': name, 'vram_bytes': vram, 'source': 'sysfs'})
    return gpus


def _windows() -> list[dict]:
    script = ('Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility | '
              'ConvertTo-Json -Compress')
    output = _run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], timeout=8)
    try:
        value = json.loads(output) if output.strip() else []
    except ValueError:
        return []
    gpus = []
    for item in value if isinstance(value, list) else [value]:
        name = str(item.get('Name') or '')
        text = (name + ' ' + str(item.get('AdapterCompatibility') or '')).lower()
        vendor = 'nvidia' if 'nvidia' in text else 'amd' if ('amd' in text or 'radeon' in text) else (
            'intel' if 'intel' in text else None)
        # AdapterRAM is a 32-bit value that is wrong above 4 GiB: VRAM is "not measurable" here.
        gpus.append({'vendor': vendor, 'name': name or None, 'vram_bytes': None, 'source': 'cim'})
    return gpus


def _macos() -> list[dict]:
    try:
        value = json.loads(_run(['/usr/sbin/system_profiler', 'SPDisplaysDataType', '-json'], timeout=10) or '{}')
    except ValueError:
        return []
    gpus = []
    for item in value.get('SPDisplaysDataType', []):
        name = item.get('sppci_model') or item.get('_name')
        apple = 'apple' in str(item.get('spdisplays_vendor', '')).lower() or str(name or '').startswith('Apple')
        gpus.append({'vendor': 'apple' if apple else None, 'name': name, 'vram_bytes': None, 'shared_memory': apple,
                     'source': 'system_profiler'})
    return gpus


def gpus(platform=None) -> list[dict]:
    platform = sys.platform if platform is None else platform
    found = _nvidia()
    if platform.startswith('linux'):
        found += [g for g in _linux_drm() if g['vendor'] != 'nvidia' or not found]
    elif platform == 'win32' and not found:
        found = _windows()
    elif platform == 'darwin':
        found = _macos()
    return found


def free_bytes(path) -> int | None:
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def assessment(target, gpu_list) -> dict:
    if target is None:
        return {'state': 'unsupported', 'label': 'Unsupported',
                'detail': 'OLIVE 1.0 is built for Linux x86-64, Windows x86-64 and macOS on Apple Silicon.'}
    vendors = {g.get('vendor') for g in gpu_list}
    if any((target, vendor) in VERIFIED for vendor in vendors):
        return {'state': 'verified', 'label': 'Verified',
                'detail': 'OLIVE has been tested on this kind of computer.'}
    return {'state': 'not_verified', 'label': 'Not yet verified',
            'detail': 'OLIVE should run here, but this combination has not been tested yet.'}


def snapshot(environ=None, platform=None, models_path=None) -> dict:
    from ..identity import IDENTITY
    platform = sys.platform if platform is None else platform
    target = platform_target(platform)
    gpu_list = gpus(platform)
    data_root = app_paths.user_data_root(environ, platform)
    storage = [{'label': 'OLIVE data', 'path': str(data_root), 'free_bytes': free_bytes(data_root)}]
    if models_path:
        storage.append({'label': 'Ollama models', 'path': str(models_path), 'free_bytes': free_bytes(models_path)})
    manifest = app_paths.backend_manifest() or {}
    return {
        'os': operating_system(platform), 'target': target, 'cpu': cpu(platform), 'memory_bytes': memory(),
        'gpus': gpu_list, 'storage': storage,
        'application': {'name': IDENTITY.get('name', 'OLIVE'), 'version': IDENTITY.get('version', ''),
                        'packaged': app_paths.packaged(), 'backend_python': manifest.get('python')},
        'assessment': assessment(target, gpu_list),
    }
