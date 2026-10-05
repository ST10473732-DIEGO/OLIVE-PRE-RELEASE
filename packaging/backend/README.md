# OLIVE backend artefact

`build_backend.py` produces `desktop/backend-artifact/`. It is a self-contained Python
backend that electron-builder ships as `resources/backend`. Users need no system Python,
virtual environment, Git checkout, Node or npm.

```bash
python packaging/backend/build_backend.py        # any Python >= 3.11, on the target OS
python packaging/backend/lock_dependencies.py    # after a pyproject dependency change (needs uv)
```

| File | Purpose |
| --- | --- |
| `python-runtime.json` | Pinned relocatable CPython: python-build-standalone release, asset, URL and SHA-256 per target. The checksums come from the release's `SHA256SUMS` and were cross-checked against GitHub's asset digests |
| `locks/<target>.txt` | Every distribution of pyproject `dependencies` (core only), binary wheels, PyPI SHA-256 hashes |
| `build_backend.py` | Download and verify → extract → `pip install --require-hashes --only-binary=:all: --no-deps` → copy `olive/` → `.pth` → prune → precompile (unchecked-hash) → manifest → smoke test → atomic replace |
| `smoke_backend.py` | Runs inside the built interpreter from an unrelated directory and a throwaway profile. It imports everything, checks that excluded parts are absent, starts `python -m olive.bridge`, reads `runtime.runtimes` (all Needs setup) and checks that nothing was written into the artefact |

Targets: `linux-x86_64`, `windows-x86_64`, `macos-arm64`. Intel macOS is not supported
because `cryptography>=50` publishes no x86_64 macOS wheel.

Not in the artefact:

- `olive/ui_qt`, `olive/__main__.py` (the Qt fallback);
- `dmdo/`;
- PySide6, Playwright and its browsers, and pip;
- the `studio` extra (pylsp, debugpy); `pywinpty` is a core Windows dependency since PASS 2C and is in the Windows lock;
- Tcl/Tk, IDLE, the CPython test suite and headers;
- on Linux, the unused `libpython` shared library (the interpreter is statically linked);
- console-script launchers;
- models and runtimes.

Every build writes `olive-backend.json`, which records the interpreter provenance, the lock
hash, the exact installed distributions, the source commit and whether `olive/` had
uncommitted changes, and every excluded or pruned path.
