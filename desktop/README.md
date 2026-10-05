# OLIVE desktop (Electron)

This is the OLIVE desktop application: an Electron/React shell around the shared
Python runtime, which it starts as `python -m olive.bridge`. It is the product
shell for OLIVE 1.0 (version metadata 1.0.0 on `release/olive-1.0`; installers are
still being prepared). The root `run_olive.sh` (Linux) and `run_olive.bat`
(Windows) launch it from a source checkout. `python main.py` starts the legacy Qt
fallback, which is development only. Historical 3.5.1 implementation evidence is
in `docs/releases/3.5.1`; current documentation starts at `docs/README.md`.

Use Node 22.12 or newer (the launcher's minimum; CI and the 3.5.1 toolchain used
Node 24) and the repository Python virtual environment. From `desktop`:

```text
npm ci
npm run build
npm start
npm run typecheck
npm run lint
npm test
npm run test:e2e
```

The build serves local assets through the intentionally stable `dmdo://app`
security origin; the canonical renderer API is `window.olive`. No Vite server or
CDN runs at application startup. Monaco and xterm load when Studio opens. Initial
development setup provisions Electron; packaged startup must not download it.

For an isolated populated preview, run `scripts/launch_electron_preview.ps1` from
the repository. `OLIVE_DATA_DIR` explicitly selects a profile; new defaults use
`~/.olive`, with safe in-place legacy `~/.dmdo` recognition. Conflicting profiles
fail clearly. Legacy environment aliases remain documented in docs/architecture/legacy-dmdo-compatibility.md.
Qt and Electron share an exclusive writer lock: close the writer before switching.

Visual evidence for the redesign is captured with an isolated synthetic profile
and realistic edge-case data: `npx playwright test --config playwright.visual.config.ts`
writes screenshots at 1920×1080, 1440×900, 1366×768, 1000×700 and 760×560,
an interaction recording, an overflow check and timings to
`artifacts/ui-review/redesign/<label>/` (ignored). `tests/visual/measure.spec.ts`
records startup, navigation, Monaco typing and idle metrics for before/after
comparison. Studio keeps its own compact-spine preference; Ctrl+S saves and
Ctrl+Shift+S saves all open files.

`OLIVE_LIVE_AI=1 npm run test:e2e -- tests/e2e/live-chat.spec.ts` opts into the
local-model Chat test. `OLIVE_M4_LIVE_LANGUAGE=1` opts into `m4-language-live.spec.ts`.
Ordinary M4 tests use synthetic profiles, dummy credentials and loopback-only
no-relay TLS mail sinks. They never access real mailboxes or deliver Internet
email. Matching synthetic approvals are exercised only under explicit delegation.
Install `requirements-mail-test.txt` in the project virtual environment for those
tests. IMAP uses a labelled scripted TLS fixture, not independent server proof.

Ctrl+Shift+P opens the command palette. Ctrl+Alt+Escape stops desktop input through Electron main and Python. Studio Ctrl+S uses the policy-bearing save path. Studio's language servers, debug adapters and interactive terminals are optional tooling provisioned by `scripts/provision_studio_tooling.py` (see `THIRD_PARTY.md`).

Packaging uses electron-builder: `npm run package:linux` (AppImage), `package:win` (per-user NSIS) and `package:mac` (unsigned DMG). Each one first needs the self-contained backend for that OS, built with `python ../packaging/backend/build_backend.py`. `scripts/require-backend.cjs` refuses a missing, mismatched or development backend, and the repository `.venv` is never packaged. Only the Linux AppImage has been built and launched so far; nothing is published (`docs/architecture/packaging.md`, `docs/install/README.md`).

Mail is available from All Spaces or the command palette. It works locally before
server setup. See `docs/features/mail.md` and `docs/security/credentials.md` for optional setup,
protected credentials, submission semantics, backup privacy and limits. Final
release/packaging acceptance remains separate from M4 internal acceptance.
