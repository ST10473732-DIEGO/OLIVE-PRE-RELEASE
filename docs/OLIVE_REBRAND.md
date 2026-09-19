# OLIVE rebrand and compatibility map

OLIVE was formerly named DMDO. This is the same 3.5.1 application and schema 4;
M3 remains complete, M4 has not started. Source checkpoint: 0c4520d on
`development/3.5.1-electron-experience`. The initial worktree was clean.
Rebrand implementation and local acceptance are complete at source commit `ebe737e`.
The subsequent documentation commit records these results. No release tag or
default-launcher switch is part of this task.

| Old identity | Canonical identity | Compatibility decision / validation |
| --- | --- | --- |
| DMDO display name / prompts | OLIVE | Owned current screens, errors, templates and Qt labels renamed; historical user content untouched |
| dmdo Python package | olive | One backend; dmdo import finder aliases canonical modules/classes. Fresh-process class and entry tests |
| DMDOApplication | OliveApplication | Narrow legacy attribute alias, no second runtime |
| run_dmdo.bat | run_olive.bat; python -m olive | Old batch forwards; Qt remains default |
| DMDO_* environment | OLIVE_* | One startup normalizer; old-only accepted, equal values accepted, conflicting values fail clearly. Explicit profile wins over discovery |
| ~/.dmdo | ~/.olive for fresh profiles | Existing nonempty legacy profile reused in place. Two nonempty distinct locations require OLIVE_DATA_DIR. No real directories moved |
| electron-shell / Chromium state | unchanged under selected profile | Explicit userData/sessionData retained; panel/navigation storage keys untouched |
| dmdo://app origin | intentionally unchanged | Chromium origin state and exact sender validation remain; no additional trusted origins |
| dmdo:* IPC / window.dmdo | olive:* / window.olive | Main/preload/renderer/tests changed together; no raw bridge or legacy renderer alias |
| local.dmdo.desktop | intentionally stable app/packager ID | Upgrade/taskbar identity preserved; display/executable configuration uses OLIVE |
| DMDO credential target namespace | intentionally unchanged | Credential references must not rotate; no real secrets accessed |
| runtime-writer.lock / qt-runtime.lock | unchanged | Old/new imports and both frontends share the existing writer exclusion |
| dmdo_version backup field | olive_version plus product=OLIVE | Format 1 and schema validation retained; legacy DMDO manifests explicitly accepted |
| dmdo_csv_escape / X-DMDO-* | stable interchange extensions | Existing CSV/vCard/ICS relationships and escaping remain readable; new ICS producer is OLIVE; event UIDs unchanged |
| dmdo-default-calendar / dmdo-local-profile | stable bootstrap UIDs | Existing native IDs are not branding text and must not be regenerated |
| DMDO-CHAT and measured role display aliases | OLIVE-* display only | Runtime model tags and stored alias records untouched |
| DMDO Blue theme identifier | OLIVE Blue presentation | Legacy stored theme read in memory; no colour redesign |
| assets/branding/dmdo-* / dmdo.ico | olive-* / olive.ico | Same bytes; selected olive artwork and blue Core unchanged |
| release reports / evidence / Git tags | unchanged historical names | Never rewrite evidence to imply OLIVE was always the name |

Current shared identity is `olive/identity.json`, consumed by Python and Electron.
Branding regressions reject unintended former branding in active source/UI.
Profile resolution is mirrored and tested at the Python/Electron boundary; branding
is not an ownership/permission decision. Nonempty unknown profile data also causes
an explicit conflict instead of an overwrite. No automatic relocation is offered.

## Running

From the checkout root: `run_olive.bat` or `.venv\Scripts\python.exe -m olive`
launches the retained Qt default. `run_dmdo.bat` forwards to the same command.
Electron: from `desktop`, use the pinned project Node toolchain with `npm run build`
and `npm start`. Both use canonical `olive.bridge`. Set `OLIVE_DATA_DIR` for an
explicit profile. Do not run Qt and Electron as independent writers on one profile.

## Packaging and folder relocation

The package remains version 3.5.1.dev1 (Electron 3.5.1-dev.1). OLIVE executable/icon
configuration is updated; existing stable installer identity is retained. A portable
backend artifact is absent. The actual `npm run package:dir` attempt reached the
existing backend-artifact guard and stopped: a validated self-contained
`desktop/backend-artifact/python.exe` and dependencies are required. No packaged
executable or installed shortcut was produced. See `artifacts/rebrand/package-with-toolchain.log`.

The top-level checkout has not moved. Close OLIVE, terminals, editors and Codex
before any optional manual folder rename. Do not move an active virtual environment
and assume it is portable. This setup uses requirements files, not an editable
install; recreate .venv after relocation, install the same pinned requirements,
and rebuild Electron assets. No remotes, repositories or Windows registrations
are renamed by this work.

## Validation checkpoint

Fresh clean run: `artifacts/rebrand/final-clean-2/` (12 September 2026).

| Check | Fresh result |
| --- | --- |
| Python unittest discovery | 697 passed, exit 0; includes language, security, backup and seven rebrand tests |
| Compilation | `python -m compileall -q .`, exit 0 |
| Frontend | 18 tests passed; TypeScript, lint and production build all exit 0 |
| Approval/diagnostic harness | 7 passed, exit 0 |
| Complete ordinary Electron | 28 passed, 3 intentional opt-in skips, exit 0 |
| Qt fallback | 49/49 checks, no errors; `artifacts/rebrand/qt/results.json` |
| Live local identity | Existing `gpt-oss:20b` through Home/Electron/Python answered `OLIVE.`; 10,053 ms total request-to-completed-answer, not rendering latency |

Ordinary opt-ins intentionally skipped: `live-chat.spec.ts` (real local generation),
`m2-closeout-live.spec.ts` (live Agent/public Research), and
`m3-language-live.spec.ts` (longer installed-model composition evaluation). They
are not ordinary mock passes. The separate bounded identity check used the real
installed model and unchanged role assignment; its result is in
`artifacts/rebrand/local-identity/result.json`. No model was downloaded or renamed.

Earlier errors remain recorded: protected DPAPI failed under restricted execution
context; the normal-user complete run passed without a security bypass. The first
new Electron test used an incorrect generic page selector, then the first full run
caught the old avatar initial in the already-built bundle. The final rebuild and
complete ordinary suite passed, including its explicit `O` avatar assertion.
Separate targeted reruns are not substituted for that final full result.

The current maintained runner is `scripts/run_rebrand_checks.py`; it uses the
tracked `scripts/check_frontend.py`, not an ignored recovery helper. Example:
`python scripts/run_rebrand_checks.py compile python frontend harness electron --label my-check`.
Set `OLIVE_DATA_DIR` to an isolated test profile for direct Python test invocation.
Windows GUI/DPAPI checks use the normal user context, never administrator access.

Local evidence is ignored under `artifacts/rebrand/`; no review ZIP is required.

## Narrow former-name source allowlist

The final source scan is retained in `artifacts/rebrand/remaining-source-identifiers.json`.
These are the only maintained production/source paths with former-name text:

| Path | Intentional former-name material |
| --- | --- |
| `olive/identity.json` | Former name/slug, legacy directory, stable application ID and Chromium origin |
| `olive/identity.py` | Environment compatibility, explicit two-profile conflict, known old display aliases |
| `desktop/electron/identity.ts` | Matching environment/profile compatibility and conflict errors |
| `desktop/electron/main/index.ts` | Exact existing `dmdo://app/index.html` origin; preserving state without widening trust |
| `desktop/package.json` | Stable `local.dmdo.desktop` packaging/upgrade identity |
| `dmdo/__init__.py` | Legacy import namespace aliases the same canonical modules |
| `pyproject.toml` | Includes the minimal legacy compatibility package |
| `run_dmdo.bat` | Documented legacy forwarding command |
| `olive/ui_qt/application.py` | Old class-name lookup returns `OliveApplication` |
| `olive/personal/interchange.py` | Previously shipped CSV escaping and vCard/ICS relationship extension names |
| `olive/personal/service.py` | Stable profile/default-calendar bootstrap UIDs |
| `olive/services/backup_service.py` | Explicit legacy manifest acceptance; validation is not weakened |
| `olive/services/credential_vault.py` | Stable credential namespace; no credential retrieval or rotation |
| `olive/services/prompt_service.py` | Current OLIVE identity instruction explains the historical alias |
| `olive/storage/settings_repository.py` | Legacy theme presentation mapping |
| `scripts/capture_desktop_attach.cjs` | Exact retained trusted origin check; no new desktop acceptance performed |

Tests mentioning the old name are explicit synthetic compatibility cases in
`tests/test_olive_rebrand.py`, `desktop/tests/identity.test.ts`, and
`desktop/tests/e2e/rebrand.spec.ts`. The UI/QML branding guard rejects the old
name in current presentation; prompt construction separately checks current
identity while retaining historical content. No active source directory is
excluded to conceal branding matches.

Current documentation keeps the former-name compatibility note and links to
`DMDO_3_4_ACCEPTANCE.md` / `DMDO_3_4_1_ACCEPTANCE.md`. Completed release reports,
original milestone requirements/evidence, screenshots, logs, and Git tags are
historical records, not current branding. Their names/content are not purged.

The Python distribution/console metadata is canonical OLIVE. No public package
name availability, trademark clearance, or installed console command is claimed.
No installed `olive` module conflicted at the initial audit. This checkout uses
requirements-based setup; the actual tested commands use its Python executable.
No dependency versions changed; npm updated only lockfile package-name metadata.

## Data, execution and visual acceptance

- Python and TypeScript profile tests cover fresh defaults, in-place legacy reuse,
  custom paths, old/new aliases, and explicit conflicts. No real profile relocation.
- Fresh-process canonical/compatibility imports share class identities. Both
  `python -m olive.bridge` and `python -m dmdo.bridge` start and shut down on EOF.
  Module and batch entry points retain the Qt default; no duplicated backend copy.
- Actual Electron uses `window.olive` and canonical Python. The old environment
  spelling selects a synthetic `.dmdo` profile; contact/profile IDs and Chromium
  state persist after restart. `userData` and `sessionData` both remain under that
  profile's `electron-shell`. Evidence: `screens/continuity.json`.
- A synthetic old DMDO manifest is validated and restored by the actual backup
  service into another isolated profile. Chat, Project, Contact, Calendar, Task,
  Reminder IDs/UIDs, historical text, Deny rules and dismissed delivery state
  survive. The ordinary Electron suite also exercises the real native Restore
  confirmation, using the existing narrow delegated fixture helper. Mocked
  controller/provider cases remain mocked; no external desktop input was tested.
- New backups identify OLIVE. Actual ICS export/import preserves the event UID
  and a historical DMDO mention while using the OLIVE producer label:
  `export-continuity.json`. CSV/vCard relationship extensions stay compatible.
- Separate legacy-alias/current Python processes reject the second writer through
  the existing OS profile lock; owned child shutdown verified in
  `cross-process-lock.json`. No reminder replay or external action was introduced.
- Nine icon/source artifacts were compared byte for byte with the old checkpoint;
  all are identical (`icon-integrity.json`). Renaming did not redraw the olive.
- Opened and visually inspected actual rendered Welcome, Home, Chat, Studio,
  Agent, Research, Settings, Profile, Contacts, Calendar, Tasks and Reminders in
  `screens/`. Profile's missed fallback initial was repaired and re-inspected.
  Also inspected the live identity conversation and Qt Home capture.
- Inspected representative 1366x768 dark Contacts, light Calendar and scrolled
  Home/Today captures in `final-clean-2/screens/`. Main rebrand captures use a
  1440x920 window (1424x881 client area). Normal scrolling remains available;
  the Today capture is deliberately scrolled and is not an initial-viewport claim.
  No new branding clipping or palette/Core regressions were found. This is internal
  visual review, not independent approval, accessibility certification, or FPS data.

Remaining limits: self-contained/clean-machine packaging is not verified; no
installer/shortcut was installed. Physical DPI/multiple monitors and combined GPU
performance were not newly measured. Existing Qt style warnings remain. Stored
user-authored content may legitimately mention DMDO, and one identity answer is
not proof a model can never repeat a historical name. No real personal records,
external accounts, credentials or Windows registrations were modified. M4 has not
started; no release tag, Qt removal or default launcher switch.

## Optional manual checkout relocation (not performed)

The detected checkout remains `D:\DMDO`. After closing OLIVE, Codex, editors and
all shells using that checkout, and only if `D:\OLIVE` does not already exist,
rename the checkout to `D:\OLIVE` and reopen Codex there. Do not run a relocated
old virtual environment: its recorded creation path is not portable. This machine
has the Windows `py` launcher and the tested interpreter is Python 3.14.5.
In a new PowerShell at `D:\OLIVE`:

```powershell
Rename-Item -LiteralPath .venv -NewName .venv-before-relocation
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PATH = (Join-Path (Get-Location) '.toolchains/node-v24.21.0-win-x64') + ';' + $env:PATH
.\.toolchains\node-v24.21.0-win-x64\node.exe .\.toolchains\node-v24.21.0-win-x64\node_modules\npm\bin\npm-cli.js --prefix desktop run build
```

Use a different archive suffix if `.venv-before-relocation` exists; do not overwrite
it. The existing project Node toolchain and dependencies use relative launch paths;
rebuild their assets after relocation. If dependency reinstallation is needed,
follow the pinned project-local setup rather than changing versions.
No editable install was present to repair. Review explicit custom paths before
relocation; do not rewrite real profile/workspace paths as a text replacement.
The original checkout and environment have not been moved by this rebrand.
