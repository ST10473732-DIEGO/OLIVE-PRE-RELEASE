"""Compare V3 frozen bytes and explicit milestone exceptions, including additions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    baseline = json.loads((root / 'docs/evidence/linux-desktop-frozen.json').read_text())
    exception_path = root / 'docs/evidence/linux-desktop-frozen-exceptions.json'
    exceptions = json.loads(exception_path.read_text())['exceptions'] if exception_path.exists() else []
    approved = {item['path']: item['sha256'] for item in exceptions}
    current = {}
    for name in baseline['roots']:
        path = root / name
        for file in path.rglob('*') if path.is_dir() and not path.is_symlink() else [path]:
            if file.is_symlink():
                current[file.relative_to(root).as_posix()] = 'symlink:' + hashlib.sha256(os.readlink(file).encode()).hexdigest()
            elif file.is_file():
                current[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    for name, expected in baseline['sha256'].items():
        actual = subprocess.check_output(['git', 'show', baseline['baseline_head'] + ':' + name], cwd=root)
        if hashlib.sha256(actual).hexdigest() != expected:
            raise ValueError('Immutable V3 baseline mismatch: ' + name)
    expected = baseline['sha256']
    changes = sorted(name for name in current.keys() & expected.keys() if current[name] != expected[name])
    return {'baseline_head': baseline['baseline_head'], 'files': len(current),
            'added': sorted(current.keys() - expected.keys()), 'deleted': sorted(expected.keys() - current.keys()),
            'changed': [p for p in changes if current[p] != approved.get(p)],
            'approved_changes': [p for p in changes if current[p] == approved.get(p)]}


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(int(any(result[k] for k in ('added', 'deleted', 'changed'))))
