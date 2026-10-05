"""Write a staged Creator runtime as a byte-reproducible .tar.zst (standard library only).

build_creator_runtime.py runs this under the PINNED python-build-standalone interpreter, never
the build machine's Python:

    <pinned>/bin/python3 -I -B -S -X utf8 pack_archive.py STAGE OUTPUT SPEC_JSON

so the tar writer and the zstd compressor (python-build-standalone compiles libzstd into the
interpreter) are covered by the interpreter's pinned SHA-256. The build machine's zstd, its
CPU count and its locale cannot change a byte.

SPEC_JSON is {"epoch": <int>, "zstd_version": "<x.y.z>", "parameters": {<CompressionParameter
name>: <int>, ...}}. Nothing is written when this interpreter's libzstd is not zstd_version.
Prints one JSON line: the compressor identity and the uncompressed tar's SHA-256 and size.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile


class _HashingWriter:
    """Forwards the tar stream to the compressor and hashes it on the way."""

    def __init__(self, raw):
        self.raw, self.digest, self.size = raw, hashlib.sha256(), 0

    def write(self, data):
        self.digest.update(data)
        self.size += len(data)
        return self.raw.write(data)

    def tell(self):
        return self.size


def compressor():
    from compression import zstd  # Python 3.14+
    return {'implementation': f'CPython {sys.version.split()[0]} compression.zstd',
            'zstd_version': zstd.zstd_version,
            # Compiled into the interpreter (python-build-standalone), so no system libzstd is loaded.
            'builtin': '_zstd' in sys.builtin_module_names}


def pack(stage: Path, output: Path, spec: dict) -> dict:
    """Sorted paths, uid/gid 0, no owner names, mtime = the pinned epoch, normalised modes."""
    from compression import zstd
    identity = compressor()
    if identity['zstd_version'] != spec['zstd_version']:
        raise SystemExit(f"this interpreter's libzstd is {identity['zstd_version']}, the pinned compressor is "
                         f"{spec['zstd_version']}; nothing was written")
    options = {zstd.CompressionParameter[name]: value for name, value in spec['parameters'].items()}
    epoch = spec['epoch']
    paths = sorted(stage.rglob('*'), key=lambda p: p.relative_to(stage).as_posix())
    with zstd.open(output, 'wb', options=options) as raw:
        writer = _HashingWriter(raw)
        with tarfile.open(fileobj=writer, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for path in paths:
                relative = path.relative_to(stage).as_posix()
                info = tar.gettarinfo(str(path), arcname=relative)
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                info.mtime = epoch
                info.pax_headers = {}
                if info.isdir():
                    info.mode = 0o755
                    tar.addfile(info)
                elif info.issym():
                    tar.addfile(info)
                elif info.isreg():
                    info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                    with open(path, 'rb') as stream:
                        tar.addfile(info, stream)
                else:
                    raise SystemExit(f'Unsupported file type in the runtime: {relative}')
    return {**identity, 'parameters': spec['parameters'], 'tar_sha256': writer.digest.hexdigest(),
            'tar_bytes': writer.size}


def main(argv=None):
    stage, output, spec = (argv or sys.argv[1:])
    print(json.dumps(pack(Path(stage), Path(output), json.loads(spec)), sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
