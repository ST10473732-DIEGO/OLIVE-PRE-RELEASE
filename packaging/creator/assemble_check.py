"""Internal check: assemble a throwaway Creator runtime the way setup does, without a GPU.

    python packaging/creator/assemble_check.py out/<id>.manifest-entry.json out/<id>.tar.zst WORK_DIR

Uses setup's own primitives: safe_archive.extract for the archive (archive modes kept), then
secure_download (HTTPS, the entry's direct host list only, pinned size and SHA-256) and
safe_archive.install_wheel for each direct-download wheel (all 20 for the image engine) into the runtime's
site-packages. Finally the assembled interpreter imports torch in isolated mode, which loads
libtorch_cuda and therefore proves the CUDA libraries sit where torch's RPATH expects them
(no driver or GPU is needed for the import itself).

WORK_DIR receives the direct-download wheels' bytes (NVIDIA components among them), so the caller
deletes it and never uploads it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
from olive.services import safe_archive  # noqa: E402
from olive.services.secure_download import Artefact, Downloader  # noqa: E402

SMOKE = ('import json, os, sys, torch; root = os.path.realpath(sys.argv[1]); '
         'leaks = [m.__file__ for m in list(sys.modules.values()) if getattr(m, "__file__", None) '
         'and not os.path.realpath(m.__file__).startswith(root)]; '
         'print(json.dumps({"torch": torch.__version__, "cuda": torch.version.cuda, "leaks": leaks[:5]}))')


def assemble(entry: dict, archive: Path, work: Path) -> dict:
    install = entry['install']
    runtime = work / 'runtime'
    safe_archive.extract(archive, install['format'], runtime, max_bytes=int(install['installed_bytes'] * 1.25),
                         executables=install['executables'], keep_exec=install.get('modes') == 'archive')
    downloader = Downloader(work / 'downloads')
    site = runtime.joinpath(*install['direct_wheels_target'].split('/'))
    for wheel in next(iter(entry['direct_wheels'].values())):
        path = downloader.fetch(Artefact(wheel['url'], wheel['sha256'], wheel['size_bytes'], tuple(entry['direct_hosts']),
                                         wheel['name']))
        safe_archive.install_wheel(path, site, max_bytes=int((wheel['installed_bytes'] or wheel['size_bytes'] * 4) * 1.25))
        path.unlink()
    python = runtime.joinpath(*install['register']['paths']['python'].split('/'))
    result = subprocess.run([str(python), '-I', '-B', '-c', SMOKE, str(runtime)], capture_output=True, text=True,
                            timeout=600, env={'PATH': '/usr/bin:/bin'})
    if result.returncode != 0:
        raise SystemExit('The assembled runtime could not import torch:\n' + result.stderr[-2000:])
    smoke = json.loads(result.stdout.strip().splitlines()[-1])
    if smoke['leaks']:
        raise SystemExit(f'The assembled runtime imported code from outside itself: {smoke["leaks"]}')
    return smoke


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('entry', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('work', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(assemble(json.loads(args.entry.read_text(encoding='utf-8')), args.archive, args.work)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
