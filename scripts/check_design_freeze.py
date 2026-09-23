"""Compare all frozen files, including ignored/untracked additions, to V2."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/backend-v3-frozen.json"


def verify(root=ROOT, manifest=MANIFEST):
    baseline = json.loads(manifest.read_text())
    current = {}
    for name in baseline["roots"]:
        path = root / name
        for file in (path.rglob("*") if path.is_dir() and not path.is_symlink() else [path]):
            if file.is_symlink():
                current[file.relative_to(root).as_posix()] = "symlink:" + hashlib.sha256(os.readlink(file).encode()).hexdigest()
            elif file.is_file():
                current[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    expected = baseline["sha256"]
    result = {"design_base": baseline["design_base"], "files": len(current),
              "added": sorted(current.keys() - expected.keys()),
              "deleted": sorted(expected.keys() - current.keys()),
              "changed": sorted(p for p in current.keys() & expected.keys() if current[p] != expected[p])}
    exceptions_path = root / "docs/evidence/backend-v3-frozen-exception.json"
    approved = json.loads(exceptions_path.read_text())["sha256"] if exceptions_path.exists() else {}
    result["approved_changes"] = [p for p in result["changed"] if approved.get(p) == current[p]]
    result["changed"] = [p for p in result["changed"] if p not in result["approved_changes"]]
    # Also verify the stored baseline itself against immutable Git bytes.
    for name, digest in expected.items():
        original = subprocess.check_output(["git", "show", baseline["design_base"] + ":" + name], cwd=root)
        if hashlib.sha256(original).hexdigest() != digest:
            raise ValueError("Baseline digest mismatch: " + name)
    return result


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if any(result[k] for k in ("added", "deleted", "changed")) else 0)
