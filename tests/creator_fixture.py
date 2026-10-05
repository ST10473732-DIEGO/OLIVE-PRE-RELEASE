"""Fixtures for the Creator runtime "Option B" tests: wheels with RECORDs, a runtime archive with
a scripted probe interpreter, and a manifest entry with NVIDIA-style direct downloads.
Nothing here touches the network or a real runtime."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import zipfile

from tests.setup_installer_fixture import sha, tar_bytes

SITE = 'python/lib/python3.14/site-packages'
DIRECT_LICENCE = 'LicenseRef-NVIDIA-Proprietary'


def record_hash(data: bytes) -> str:
    return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()


def wheel_bytes(name: str, version: str, files: dict[str, bytes], *, executable=(), licence='MIT',
                record_override: dict[str, str] | None = None, unrecorded=(), extra_members: dict[str, bytes] | None = None,
                purelib=True) -> bytes:
    """A wheel whose RECORD lists every file with its SHA-256 (record_override replaces one hash,
    unrecorded leaves files out of RECORD, extra_members are added without any check)."""
    dist = f'{name.replace("-", "_")}-{version}.dist-info'
    members = dict(files)
    members[f'{dist}/METADATA'] = (f'Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n'
                                   f'License-Expression: {licence}\nLicense-File: License.txt\n\n').encode()
    members[f'{dist}/licenses/License.txt'] = f'{name} licence text (fixture)\n'.encode()
    members[f'{dist}/WHEEL'] = (f'Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: {str(purelib).lower()}\n'
                                'Tag: py3-none-any\n').encode()
    record = io.StringIO()
    writer = csv.writer(record, lineterminator='\n')
    for path, data in members.items():
        if path in unrecorded:
            continue
        writer.writerow([path, (record_override or {}).get(path, record_hash(data)), len(data)])
    writer.writerow([f'{dist}/RECORD', '', ''])
    members[f'{dist}/RECORD'] = record.getvalue().encode()
    members.update(extra_members or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, data in members.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o100755 if path in executable else 0o100644) << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def direct_wheel(package='nvidia-fixture-cu13', version='1.0') -> tuple[str, bytes]:
    module = package.split('-')[1]
    data = wheel_bytes(package, version, {f'nvidia/{module}/lib/lib{module}.so.1': b'\x7fELF fixture ' * 64,
                                          f'nvidia/{module}/__init__.py': b''},
                       executable={f'nvidia/{module}/lib/lib{module}.so.1'}, licence=DIRECT_LICENCE)
    return f'{package.replace("-", "_")}-{version}-py3-none-manylinux_2_27_x86_64.whl', data


def probe_line(**overrides) -> str:
    result = {'stage': 'done', 'python': '3.14.8', 'torch': '2.14.0+cu130', 'torch_cuda': '13.0',
              'cuda_available': True, 'cudnn': 92400, 'device': 'Fixture GPU', 'comfyui': '0.35.0',
              'core_nodes': 70, 'leaks': []}
    result.update(overrides)
    return 'OLIVE-PROBE ' + json.dumps(result)


def runtime_archive(probe_file, direct: list[tuple[str, bytes]], *, extra: dict[str, bytes] | None = None,
                    declared: list[tuple[str, str]] | None = None, mode='w:gz') -> bytes:
    """A Creator archive whose python/bin/python3 prints the probe line found in probe_file."""
    marker = {'schema': 'olive-creator-runtime/1', 'id': 'creator-image-fixture', 'version': 'fixture',
              'target': 'linux-x86_64', 'definition_sha256': 'd' * 64, 'source_date_epoch': 1788930166,
              'comfyui': {'tag': 'v0.35.0', 'commit': '40c4fcdf513a4523e39d54a9d391908af8df8171'},
              'direct_downloads': {'wheels': [{'name': n, 'sha256': s} for n, s in
                                              (declared if declared is not None else [(n, sha(d)) for n, d in direct])]}}
    members = {
        'python/bin/python3': f'#!/bin/sh\ncat "{probe_file}"\n'.encode(),
        f'{SITE}/torch/__init__.py': b'__version__ = "fixture"\n',
        f'{SITE}/torch/bin/torch_shm_manager': b'#!/bin/sh\nexit 0\n',
        'ComfyUI/main.py': b'print("fixture ComfyUI")\n',
        'ComfyUI/comfyui_version.py': b'__version__ = "0.35.0"\n',
        'OLIVE-RUNTIME.json': json.dumps(marker).encode(),
    }
    members.update(extra or {})
    return tar_bytes(members, mode=mode, executable={'python/bin/python3', f'{SITE}/torch/bin/torch_shm_manager'})


def creator_entry(files, archive: bytes, direct: list[tuple[str, bytes]], *, entry_id='fixture-creator-image',
                  installed_bytes=1 << 20) -> dict:
    wheels = [{'name': name, 'package': name.split('-')[0].replace('_', '-'), 'version': name.split('-')[1],
               'url': files.add('/pypi/' + name, data), 'sha256': sha(data), 'size_bytes': len(data),
               'installed_bytes': 4096, 'licence': DIRECT_LICENCE} for name, data in direct]
    return {
        'id': entry_id, 'kind': 'archive', 'provides': 'image-engine', 'name': 'Fixture Creator image engine',
        'version': 'fixture', 'platforms': ['linux-x86_64'], 'validated_platforms': ['linux-x86_64'], 'enabled': True,
        'source': {'publisher': 'fixture', 'url': files.add('/creator-image.tar.gz', archive), 'hosts': ['127.0.0.1']},
        'sha256': sha(archive), 'size_bytes': len(archive),
        'install': {'destination': 'runtime/comfy', 'format': 'tar.gz', 'installed_bytes': installed_bytes,
                    'executables': ['python/bin/python3'], 'modes': 'archive',
                    'register': {'runtime': 'comfy', 'paths': {'root': 'ComfyUI', 'python': 'python/bin/python3'}},
                    'direct_wheels_target': SITE, 'verify': 'comfyui-cuda'},
        'direct_wheels': {'linux-x86_64': wheels}, 'direct_hosts': ['127.0.0.1'],
        'direct_source': 'PyPI', 'direct_summary': 'including NVIDIA CUDA dependencies',
        'licence': {'spdx': 'GPL-3.0-only', 'name': 'fixture', 'url': None, 'acceptance_required': False,
                    'distribution': 'olive-hosted-archive', 'identified': True, 'engineering_reviewed': True},
        'reason': None}
