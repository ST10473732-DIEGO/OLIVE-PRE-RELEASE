# Release engineering

| Tool | What it does |
| --- | --- |
| `.github/workflows/release-build.yml` | Private, build-only CI: desktop (Linux AppImage, Windows NSIS, macOS DMG, all unsigned), relay bundle and OCI image (never pushed), Creator runtimes (manual input), one SHA256SUMS. `contents: read` only; every action pinned to a commit; artefacts kept 7–14 days |
| `build_info.py` | Writes `BUILD-INFO.json` (source commit, CI run, file digests; `signed: false`, `published: false`) and `SHA256SUMS` for a folder |
| `release_gate.py` | Lists every runtime-manifest entry's gate state; `--record ID --by NAME` prints (never writes) an owner approval bound to the entry's fingerprint; `--check` fails on stale approvals |
| `check_ollama_pins.py` | Re-reads every pinned Ollama registry manifest and reports drift for human review. It never rewrites a pin |

## Gated stages

- **macOS signing and notarization** (`macos-signing` job): runs only on manual dispatch with
  `macos_signing`, in the owner-protected `release-signing` environment. Without a Developer ID
  certificate and notary key it fails closed; the signing steps themselves are not written yet.
- **Windows signing:** none configured; `CSC_IDENTITY_AUTO_DISCOVERY=false` keeps test builds
  unsigned.
- **Publication** of anything (GitHub Release, public repository, container registry): not part
  of this workflow at all.

The workflow has not run on GitHub yet. Nothing in it is a platform validation: Windows and
macOS builds still need their own acceptance passes on real machines.
