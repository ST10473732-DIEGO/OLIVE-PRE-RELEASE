# OLIVE Electron development application

This is the untagged 3.5.1 development application. M2 workspaces, M3 Personal Core
and M4 native Mail use the shared Python runtime. The root `run_olive.bat` launches
this Electron application. `python main.py` retains the historical Qt fallback.
The current implementation and classified evidence are in `docs/releases/3.5.1`.

Use Node 24.21.0 and the repository Python virtual environment. From `desktop`:

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
fail clearly. Legacy environment aliases remain documented in OLIVE_REBRAND.md.
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

Ctrl+Shift+P opens the command palette. Ctrl+Alt+Escape stops desktop input through Electron main and Python. Studio Ctrl+S uses the policy-bearing save path. Output is read-only, not an interactive shell. No language server or debugger is claimed.

Packaging uses electron-builder, but `package:dir` deliberately fails until a validated self-contained `backend-artifact/python.exe` and dependencies exist. The development virtual environment is not a distributable backend. No installer or shortcut has been rebuilt.

Mail is available from All Spaces or the command palette. It works locally before
server setup. See `MAIL_TRANSPORTS.md` and `ACCOUNT_SECURITY.md` for optional setup,
protected credentials, submission semantics, backup privacy and limits. Final
release/packaging acceptance remains separate from M4 internal acceptance.
