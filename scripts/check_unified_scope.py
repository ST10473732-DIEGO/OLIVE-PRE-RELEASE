"""Verify the owner's scoped V2 changes against the recorded desktop baseline.

Historical manifests and their original verifier remain untouched.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    ledger = json.loads((root/'docs/evidence/unified-agent-scope.json').read_text())
    baseline = ledger['baseline_head']
    original = json.loads((root/'docs/evidence/backend-v3-frozen.json').read_text())
    actual = []
    for name in original['sha256']:
        before = subprocess.check_output(['git','show',baseline+':'+name],cwd=root)
        path = root/name
        after = path.read_bytes() if path.exists() else None
        if before != after:
            actual.append({'path':name,'baseline_sha256':hashlib.sha256(before).hexdigest(),
                           'current_sha256':hashlib.sha256(after).hexdigest() if after is not None else None})
    expected = [{k:row[k] for k in ('path','baseline_sha256','current_sha256')} for row in ledger['former_frozen_changes']]
    if actual != expected:
        raise ValueError('Former-frozen changes differ from the owner-scoped ledger')
    for name, digest in ledger['historical_manifests_unchanged'].items():
        if hashlib.sha256((root/'docs/evidence'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('A historical freeze manifest changed')
    known = set(original['sha256'])
    for name in original['roots']:
        path = root/name
        for file in path.rglob('*') if path.is_dir() else [path]:
            if file.is_file() and file.relative_to(root).as_posix() not in known:
                raise ValueError('Unrecorded addition under a formerly frozen root')
    return {'baseline_head':baseline,'scoped_changes':len(actual),'historical_manifests_unchanged':True}


if __name__ == '__main__':
    print(json.dumps(verify(),indent=2))
