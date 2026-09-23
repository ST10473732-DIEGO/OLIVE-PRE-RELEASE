"""Install only the pinned, separately approved repository-local Linux JDK.

Read docs/evidence/backend-v3-acquisition.json and obtain download approval
before invoking. Text weights are acquired with Ollama, never by this script.
Existing destinations are never overwritten; no system configuration is edited.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def provision_jdk():
    if platform.system() != 'Linux' or platform.machine() not in {'x86_64', 'AMD64'}:
        raise SystemExit('This pinned archive is Linux x64 only; use the platform SDK installation on other hosts.')
    item = json.loads((ROOT/'docs/evidence/backend-v3-acquisition.json').read_text())['jdk']
    target = ROOT/item['destination']
    if target.exists() or target.is_symlink():
        raise SystemExit('JDK destination already exists; preserved. Inspect it rather than overwriting.')
    tools = ROOT/'.toolchains'
    tools.mkdir(exist_ok=True)
    archive = tools/Path(item['url']).name
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix+'.partial')
        with partial.open('xb') as output, urllib.request.urlopen(item['url'], timeout=90) as response:
            shutil.copyfileobj(response, output, 1024*1024)
        with partial.open('rb') as source:
            if partial.stat().st_size != item['bytes'] or hashlib.file_digest(source, 'sha256').hexdigest() != item['sha256']:
                raise SystemExit('Archive verification failed; partial preserved for inspection, not installed.')
        partial.rename(archive)
    with archive.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != item['sha256']:
            raise SystemExit('Archive checksum mismatch; not installed.')
    stage = tools/('temurin-'+item['revision'].removeprefix('jdk-'))
    stage.mkdir()  # Fail closed if a prior extraction exists.
    with tarfile.open(archive) as bundle:
        bundle.extractall(stage, filter='data')
    children = list(stage.iterdir())
    if len(children) != 1 or not (children[0]/'bin/javac').is_file():
        raise SystemExit('Unexpected JDK layout; extraction preserved, not activated.')
    target.symlink_to(children[0].relative_to(target.parent), target_is_directory=True)
    print('Verified JDK installed locally. No global defaults changed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-jdk', action='store_true', required=True,
                        help='Install the manifest JDK after explicit download approval')
    parser.parse_args()
    provision_jdk()
