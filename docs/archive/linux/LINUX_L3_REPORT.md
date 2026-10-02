# OLIVE Linux L3 — native services and application parity

Date: 2026-09-19. Branch: `platform/linux-l3`. Starting checkpoint: `2d3eede`.
The checkout was clean and already on the requested branch before edits.

## Decision

**YES — OLIVE is a dependable native desktop application for the validated
CachyOS/KDE Wayland workflows on this host.** Native credentials, reminders,
local Chat/DEEP vision, SDXL generation/edit/cancel, GPU handoff, Python/C#,
Browser, Mail fixtures and owned lifecycle now have direct evidence. This is not
a claim of arbitrary Linux Desktop Control, physical X11 certification, personal
provider authentication or a clean-machine installer. The remaining manual and
unsupported capabilities are listed below.

Host: CachyOS, KDE Plasma 6.7.5/Wayland, Python 3.14.7, Node 24.21.0/Electron
44.3.0, NVIDIA RTX 3080 Ti Laptop GPU (16 GiB), driver 615.71.09. L1/L2's native
launch, portable workspace and owned-process foundations are preserved.

## Native services

Linux credentials use **SecretStorage 3.5.0 → D-Bus Secret Service → KDE
KWallet/ksecretd**. The actual session exposes `org.freedesktop.secrets` and an
unlocked default KWallet collection. OLIVE requires an encrypted Secret Service
session, refuses locked/missing stores and unsupported plaintext sessions, and
never creates a JSON fallback. Profile namespaces are hashed and case-sensitive
on Linux. Windows retains its original case-folded DMDO namespace and Credential
Manager read/write/delete implementation. No migration of existing secrets occurs.

The shared `CredentialVault` API remains authoritative. Mail's Google setup and
masked credential entry now use it on Linux, with safe visible failure messages
and transient secret clearing. Synthetic live tests verified put/read/remove,
profile-file absence, generic IMAP/SMTP credentials, iCloud app-password readiness,
and four Gmail OAuth fixture tests against the real wallet (PKCE, wrong state,
account identity, cancellation and refresh-token rotation). Google HTTP responses
were synthetic; no personal Google/iCloud account was contacted. All synthetic
wallet entries were removed. A desktop-user keyring does not isolate secrets from
every process running as that same user.

Linux notifications use Electron's native notification API through Plasma's
`org.freedesktop.Notifications` service (Plasma 6.7.5, notification specification
1.2). Titles identify OLIVE; bodies contain bounded generic completion guidance,
not mail subjects, document text, terminal output or credentials. Selected events
cover task/calendar reminders, Agent terminal states, Studio build results,
completed downloads and Mail attention. Progress events are excluded. A bounded
profile claim ledger is written atomically before delivery; duplicate event keys
are suppressed and delivery is capped at four popups per minute. Existing durable
reminder history remains authoritative. Failed notification delivery/storage is
shown in OLIVE. No Windows notification implementation was removed.

The live reminder test creates a task/reminder, closes before due, reopens,
observes Electron's native **show** acknowledgement, checks one durable delivery,
restarts again and confirms no additional claim. Africa/Johannesburg is retained
while due instants are UTC; existing DST/gap/overlap/snooze tests also pass.
At-most-once OS delivery intentionally permits a lost popup if the app crashes
between durable claim and native delivery. It is not an exactly-once transactional
protocol with Plasma. Missed reminders remain in OLIVE history. Reminders do not
fire while OLIVE is closed; overdue reminders are processed on reopening.

## Login startup

Explicit user commands:

```bash
./run_olive.sh --enable-startup
./run_olive.sh --disable-startup
```

These manage only `$XDG_CONFIG_HOME/autostart/olive.desktop`, normally
`~/.config/autostart/olive.desktop`. The entry points to this checkout's launcher
and resolved profile; paths are desktop-entry quoted. Unmanaged entries and
symlinks are refused. There is no root daemon, system service or model-facing
startup tool. Electron's existing profile-scoped single-instance lock handles
manual/login overlap. Moving the checkout requires disabling/re-enabling startup.
A temporary entry passed `desktop-file-validate`, enable/disable and collision
tests. The native journey verified that a second process exits without a second
application instance. Actual logout/login remains a manual check; acceptance did
not change the user's login preference.

## AI and media

DEEP retains native extraction/retrieval plus `gpt-oss:20b`, with relevant
`qwen3-vl:8b` image evidence. The newly installed vision model required
6,140,415,879 bytes, reported before download. A real mixed-PDF request read page 2,
answered the synthetic pears total **37**, and retained
`vision_interpretation:qwen3-vl:8b` provenance and page citations. The rendered
answer was inspected. This host also has native Tesseract: the scanned page can
have OCR text before vision. The test preserves this distinction instead of
assuming every scanned page must be unreadable. Shared tests cover no unnecessary
vision, absent models and evidence metadata. No model substitution was introduced.

The optional Linux ComfyUI runtime is separate from OLIVE's Python environment.
ComfyUI v0.35.0 resolves to `40c4fcdf513a4523e39d54a9d391908af8df8171`.
SDXL Base 1.0 is 6,938,078,334 bytes, verified against SHA-256
`31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b`.
The isolated resolved Python/CUDA dependencies total 3,748,233,894 download bytes.
These requirements were reported before installation. No existing usable Linux
checkpoint was found in the inspected project/cache locations; the downloaded
checkpoint is reused through a symlink, not downloaded a second time.

The checkout launcher discovers optional ignored `.toolchains/ComfyUI` and
`.toolchains/comfy-venv`; explicit `OLIVE_COMFY_ROOT`/`OLIVE_COMFY_PYTHON` paths
remain authoritative. ComfyUI is started on demand for explicit configuration,
rendering or a configured engine's GPU-release check, never for an unconfigured
idle launch. It binds only `127.0.0.1:8188`, disables automatic browser launch,
custom/API nodes, intermediate node caching, dynamic VRAM and cudaMallocAsync. It shares L2's supervised process
ownership/cleanup. Existing engines remain externally managed. Disconnect and
shutdown stop only an app-owned engine. This is local runtime provisioning, not
a Linux package/installer.

## Live REIMAGINE and GPU handoff

The actual `./run_olive.sh --ozone-platform=wayland` journey passed:
Chat → Browser → Studio → REIMAGINE generation → Chat → image-to-image edit →
cancel generation → Chat → disconnect engine → Chat, followed by two major-page
route cycles and normal shutdown. Both 1024×1024 PNGs were decoded, checked for
nonblank content and visually inspected; hashes differ and the original is
unchanged. Artifact previews worked. Cancellation produced no completed artifact.
SDXL follows prompts approximately: the inspected generation contains four olives
rather than the requested three, and the edit changes texture/color without fully
matching the requested purple olives/blue plate. Operational success is not a
claim of exact counting or perfect prompt adherence.

| Measurement | Observed |
| --- | ---: |
| Generation including artifact/release verification | 12.248 s |
| Image-to-image editing including artifact/release verification | 12.333 s |
| Cancellation | 1.345 s |
| Sampled generation Torch allocation peak | 7,761,559,552 bytes |
| Sampled editing Torch allocation peak | 7,864,320,000 bytes |
| ComfyUI allocator after release and after returning to Chat | 20 MiB |
| Captured owned process identities verified gone | 15 |
| Host NVIDIA use after final shutdown | 115 MiB; no remaining owned Ollama/ComfyUI runtime |

PyTorch 2.14.0+cu130 ran a real CUDA computation before acceptance. ComfyUI
inspection reported the actual NVIDIA CUDA device. Ollama had no resident model
during media, then completed real Chat inference after successful generation and
after cancellation. Browser WebContents remained bounded at two during route
churn. ComfyUI disconnect terminated the owned runtime; normal application exit
also reaped the backend, Electron children and owned inference processes.

The first two live attempts exposed a repeatable allocator-release failure after
editing under ComfyUI's default intermediate cache. Generation and the first Chat
handoff worked, but edit completion was rejected after 30 seconds. Disabling the
compiler alone did not resolve it. Using the supported **`--cache-none`** mode
passed generation, edit, cancellation and both Chat handoffs; compiler disabling
is not retained. The 256 MiB release threshold and bounded queue checks were not
weakened. This is observed behavior of the tested stack, not a promise of perfect
VRAM eviction for every external engine or future PyTorch version. Externally
managed engines remain fail-closed when release cannot be verified. Concurrent
profiles needing independent lifetimes should use a separately managed dedicated
loopback engine rather than sharing an app-owned process.

## Desktop Control foundations and safety

| Capability | KDE Wayland on this host | X11 |
| --- | --- | --- |
| Session detection | Verified Wayland despite Xwayland DISPLAY | Detected from session/display; no physical X11 acceptance |
| Application/window enumeration | Not integrated; no global enumeration claim | No Linux enumeration adapter integrated |
| Screenshot/screen capture | Screenshot v2 portal exposed; user-consent integration not implemented | No Linux Desktop Control capture adapter integrated |
| Remote input | RemoteDesktop v2, keyboard/pointer/touch device mask 7, ConnectToEIS exposed; no input requested | No Linux input adapter integrated |
| Accessibility | AT-SPI user bus present; OLIVE adapter not integrated | AT-SPI not integrated |
| Clipboard | Explicit Electron copy/paste only; no Agent clipboard control | Same application integration; not live-certified on X11 |
| File open/folder/reveal | Electron shell / argument-array xdg-open | Portable APIs; physical session not tested |
| File save/import dialogs | Electron native dialogs; automated journeys control chooser responses | Physical X11 dialogs not tested |
| Application control/launch | Unavailable until a Linux focus/observe/verify adapter exists | Unavailable in this build |

The existing Desktop Control design remains. Its unavailable notice now identifies
the session and accurately explains the missing consent-aware integration.
No unrestricted X11 automation is claimed or selected automatically. Portal
introspection is read-only and grants no authority. The session also exposes
`org.a11y.Bus` and KWin window-info methods; none were used to enumerate or control
personal windows. Their presence is not an integrated OLIVE capability. Windows UIA, ConPTY,
notifications, credential storage and `run_olive.bat` remain intact. Native Windows
navigation/launch/clipboard entry points explicitly reject Linux even if reached
below the bridge. Agent cannot obtain a gateway capability from model arguments.
Existing ACT → OBSERVE → VERIFY, focus guard, takeover, stop, confirmation and
permission tests remain in the suite. No untrusted page/mail/document can grant
terminal, filesystem, communication or desktop authority.

## Reproduction and data

```bash
./run_olive.sh
# Native Wayland selection:
./run_olive.sh --ozone-platform=wayland
# Synthetic live wallet checks; creates and removes only fixture entries:
.venv/bin/python scripts/check_linux_vault.py
```

Fresh Linux data remains `$XDG_DATA_HOME/olive`, normally
`~/.local/share/olive`; explicit paths and existing legacy profiles retain L1/L2
precedence and conflict rules. User data was not migrated or overwritten. Model
files, local environments, logs and synthetic acceptance profiles are untracked.
No merge, push, tag, release, history rewrite, OS, Connect, Mobile, pairing,
relay/sync, ISO or custom shell work is included.

## Sources

- [Secret Service specification](https://specifications.freedesktop.org/secret-service/latest-single/)
- [SecretStorage documentation](https://secretstorage.readthedocs.io/en/latest/)
- [XDG autostart specification](https://specifications.freedesktop.org/autostart/latest/)
- [Desktop-entry argument escaping](https://xdg.pages.freedesktop.org/xdg-specs/desktop-entry/latest-single/)
- [Ollama qwen3-vl inventory](https://ollama.com/library/qwen3-vl/tags)
- [SDXL Base model and hash](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors)

## Provisioning the optional local media runtime

This host uses the existing ignored checkout toolchain convention. An external
installation can instead be selected with absolute `OLIVE_COMFY_ROOT` and
`OLIVE_COMFY_PYTHON` environment variables; neither is a model-provided setting.
The equivalent explicit setup, after reviewing storage/download requirements, is:

```bash
git clone --depth 1 --branch v0.35.0 https://github.com/Comfy-Org/ComfyUI.git .toolchains/ComfyUI
python3 -m venv .toolchains/comfy-venv
.toolchains/comfy-venv/bin/python -m pip install -r .toolchains/ComfyUI/requirements.txt
```

Place or symlink the verified existing `sd_xl_base_1.0.safetensors` into
`ComfyUI/models/checkpoints`, then use **REIMAGINE → Local generation setup →
Check dedicated local engine**. The endpoint is `http://127.0.0.1:8188`.
No runtime, checkpoint or vision model is downloaded by normal application launch.
The managed command also disables API nodes; fixed local workflows do not require
hosted image APIs. A manually managed engine must retain the measured allocator
flags (`--disable-cuda-malloc --disable-dynamic-vram --cache-none`) and loopback binding.

## Regression evidence

Implementation commits: `b5480e5` (native services, platform safeguards, managed
media runtime and acceptance fixtures), then **`bf1d159`** (live-verified cache
release fix and normal-launcher media coverage). Final report commits are listed
by `git log --oneline -- docs/LINUX_L3_REPORT.md`; no self-referential hash is
embedded.

| Check | Result |
| --- | --- |
| Full Python discovery | 853 total: **845 passed, 8 Windows-only skips**, zero failures/errors |
| Frontend unit tests | **33 passed**, 12 files |
| TypeScript, ESLint, production renderer/main/preload build | Passed |
| Source compilation, excluding ignored environments/toolchains | Passed |
| Exact `python -m compileall -q .` | Failed on the same ignored PySide6 Android Jinja `__init__.tmpl.py` as L1/L2; not marked passed |
| `pip check`, `bash -n run_olive.sh`, `git diff --check` | Passed for OLIVE |
| Synthetic real KWallet/Gmail fixture suite | Four OAuth tests passed; generic IMAP/SMTP/iCloud storage readiness also passed |
| Native reminder/restart/second-instance journey | Passed, three launches, one native show acknowledgement, one durable delivery, no replay |
| Short idle sanity sample | One Electron WebContents; reported Electron CPU 0% in the five-second sample, 603,224 KiB combined Electron working set; excludes Python and is not a long-duration benchmark |
| Owned shutdown in reminder journey | All seven captured process identities gone |
| FAST/NORMAL/MAX after native changes | Live L2 journey passed, including GPU residency, cancellation and cleanup; backend interruption/restart passed separately |
| DEEP | Real mixed native/scanned PDF vision and answer evidence passed |
| REIMAGINE | Real SDXL generation/edit/cancel, both Chat handoffs, artifacts and 15-process cleanup passed |
| Desktop journeys | **26 distinct tests passed** across final focused runs; zero unresolved failures |
| ComfyUI dependency consistency and CUDA | `pip check` passed; actual NVIDIA CUDA computation passed |

The eight Python skips remain: two Windows Credential Manager checks, three
Windows UI ownership checks, one DPAPI diagnostic check, one ConPTY shell check,
and one WinForms build. They are not Linux passes. The baseline shutdown warning
about 26 uncollectable objects remains; it is distinct from process leak checks.

Completed native UI coverage includes Chat/presets, OLIVE GO fixture navigation,
sandbox isolation, downloads/private storage/restart, Python/C# real xterm input,
Monaco save/conflict/dirty-close, Git permission binding, Projects, Knowledge,
Memory, personal forms, Calendar/Tasks recurrence and linked reminders, local
Mail drafts/restart, EML isolation, loopback IMAP and TLS SMTP
accepted/partial/uncertain outcomes, separate-account reply identity, Agent
fixture history, Settings and Activity. Desktop Control is verified unavailable
on Linux and protected by deterministic denial tests, not marked as functional
Linux automation.

Native reminder popup acknowledgement is directly observed. Other notification
origins have event-selection/deduplication tests and corresponding workflow
coverage, not individual manual visual confirmations. File import/save tests
control native picker responses; actual portal/picker interaction, logout/login,
DND, multi-monitor and physical X11 acceptance remain **manual/unverified**.
No personal provider login or real external mail send was performed.

Earlier unsuccessful attempts are not counted as passes: one transient Ollama download HTTP 500 (one retry succeeded); an SDXL HTTP/2
stream reset (resumed existing bytes, full hash then passed); DEEP test launched
from the wrong directory; a Windows-era unreadable-page assertion incompatible
with available native Tesseract; and a fixture variable named `process` shadowing
Node's platform object. Corrected DEEP and two-account Mail journeys passed.
A redundant sandbox-only threaded fixture stalled under the previously documented
sandbox restriction and was stopped by exact process identity; the complete
host-access Python runs passed. No broad process kills were used.

The 26 distinct Electron cases comprise the 16-case broad native suite (the
single Mail fixture failure passed after correction), five additional
Studio/Git/Settings/data cases, one Agent case, two L2 live/restart cases, one
DEEP vision case and one live media case. Repeated L3 reminder/idle and diagnostic
reruns are not added to that distinct count. There is no claim that these were a
single monolithic 26-case invocation.

Logs live under `/tmp/olive-l3-*.log`; screenshots/results are in ignored
`desktop/test-results`, `/tmp/olive-l3-*-results` and `artifacts/core/functionality`.
They contain synthetic fixture data and are not committed application profiles.

Repeat portable checks with the locally provisioned toolchains:

```bash
export PATH="$PWD/.toolchains/dotnet:$PWD/.toolchains/node/bin:$PATH"
export DOTNET_ROOT="$PWD/.toolchains/dotnet"
.venv/bin/python -m compileall -q -x '(^|/)(\.venv|node_modules|\.toolchains|\.git)/' .
.venv/bin/python -m unittest discover -s tests -v
(cd desktop && npm run typecheck && npm run lint && npm test && npm run build)
```


Repeat the selected native journeys from the desktop directory after building;
these flags opt into local model/media work with synthetic profiles:

```bash
export PATH="$PWD/.toolchains/ollama/bin:$PWD/.toolchains/dotnet:$PWD/.toolchains/node/bin:$PATH"
export DOTNET_ROOT="$PWD/.toolchains/dotnet"
cd desktop
OLIVE_LIVE_AI=1 OLIVE_LIVE_MEDIA=1 OLIVE_START_OLLAMA=1 npx playwright test \
  browser.spec.ts interactive-run.spec.ts linux-l1.spec.ts linux-l2.spec.ts linux-l3.spec.ts \
  deep-pdf.spec.ts media.spec.ts media-generation.spec.ts \
  m3-personal.spec.ts m3-workflows.spec.ts m4-mail-local.spec.ts m4-mail-content.spec.ts \
  m4-mail-imap.spec.ts m4-mail-smtp.spec.ts mail-accounts.spec.ts \
  m2-data.spec.ts m2-settings.spec.ts m2-studio.spec.ts m2-studio-git.spec.ts studio.spec.ts m2-agent.spec.ts
```

Native tests require the actual user session and local GPU/process access. They
are not headless CI claims. The optional media runtime is first configured per
profile in REIMAGINE's existing setup controls; personal profile settings were not
silently changed during acceptance.
