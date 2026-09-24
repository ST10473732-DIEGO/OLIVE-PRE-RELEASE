"""Validate this request's narrow UI/IPC changes without rewriting older ledgers."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs/evidence/chat-agent-repair-scope.json'


def changes(baseline):
    roots = json.loads((ROOT/'docs/evidence/backend-v3-frozen.json').read_text())['roots']
    changed = subprocess.check_output(['git','diff',baseline,'--name-only','-z'],cwd=ROOT).decode().split('\0')
    changed += subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    rows = []
    for name in sorted(set(changed)):
        if not name or not any(name == root or name.startswith(root+'/') for root in roots):
            continue
        old = subprocess.run(['git','show',baseline+':'+name],cwd=ROOT,capture_output=True)
        current = ROOT/name
        rows.append({'path':name,'baseline_sha256':hashlib.sha256(old.stdout).hexdigest() if old.returncode == 0 else None,
                     'current_sha256':hashlib.sha256(current.read_bytes()).hexdigest() if current.is_file() else None})
    return rows


def verify():
    ledger = json.loads(LEDGER.read_text())
    if changes(ledger['baseline_head']) != ledger['authorized_changes']:
        raise ValueError('Changes differ from the Chat repair scope ledger')
    for path, digest in ledger['historical_manifests'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:
            raise ValueError('Historical manifest changed: '+path)
    return {'baseline_head':ledger['baseline_head'],'authorized_changes':len(ledger['authorized_changes']),
            'historical_manifests_unchanged':True}


if __name__ == '__main__':
    print(json.dumps(verify(),indent=2))
