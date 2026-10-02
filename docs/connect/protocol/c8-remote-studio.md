# OLIVE Connect C8 — guarded Remote Studio

C8 lends an explicitly shared development workspace. It uses the existing C2
identity, C3 TLS channel, C4 trusted approval and target Studio services. Pairing,
Remote AI, record sync and file transfer enable no Studio permission. Networking
still starts Off. No new listener, shell server, network filesystem or cloud
service is introduced.

The work began on clean `feature/olive-connect-c8` at `ab7f60a`, with the completed
`feature/olive-connect-c7` verified as an ancestor. C1–C7 and the Linux/Windows
baseline reports informed the boundaries below. C9 Mobile and C10 Internet
direct/relay remain future work.

## Explicit shares and authority

The target opens Devices, selects a paired peer, and uses **Remote Studio →
Share workspace** to select an existing workspace from its approved local
repository. Only opaque workspace IDs and titles enter this selection UI. The
requester cannot create shares, select a target directory, register a workspace,
change trust, change permissions or unrevoke itself.

Each share has a random UUID reference scoped to the paired identity, a local
workspace UUID, a digest binding the original root, and a monotonically increasing
share revision. Paths are resolved only against the target's existing repository.
Repointing the same local workspace UUID to a different root invalidates the old
share. Removing and sharing again creates a new reference. Equal project/device
names have no identity significance. No workspace metadata enters mDNS.

| Capability | Operations | Default |
| --- | --- | --- |
| `studio.view` (existing ID) | Shared list, bounded tree/read | Off |
| `studio.edit` | Revision-checked save of an existing file | Off |
| `studio.build` | Structured Python compile or .NET build | Off |
| `studio.test` | Existing Python/.NET structured test controller | Off |
| `studio.run` (existing ID) | Existing validated Python/.NET console configuration | Off |
| `studio.debug` | Unavailable remotely in C8 | Off |

Off is the existing `deny` decision; Ask and Allow use the existing permission
engine. Every share starts with six exact-scope Off rules. Device-wide Studio
rules are deliberately excluded from evaluation: one workspace grant cannot
spill into another. Current pairing/public identity, policy locks, share binding,
share revision and capability are checked on each operation. The local filesystem
and execution policy's explicit Deny also remains authoritative.

The authenticated shared list contains only this peer's shares with View Ask or
Allow. Ask requires a target approval before listing. View Off shares and unshared
projects are invisible. Entries contain reference, title, share revision and the
six decisions; no root, credentials, environment or unshared inventory is sent.

## Protocol and trusted Ask

Protocol version: **`olive-studio/1`**, using C3 frame types **11/12**. Exact fields:

```
request_id, protocol_version, source_device_id, target_device_id,
workspace_id, share_revision, operation, arguments, timestamp, expires_at
```

UUIDs are canonical. The C3 TLS identity is authoritative, never a claimed source.
Duplicate JSON keys, unknown fields/operations, invalid types, booleans as integers,
nonfinite numbers, oversized messages, raw workspace paths and remote approval
flags fail closed. Responses have strict operation-specific validation too.

| Operation | Exact arguments |
| --- | --- |
| `workspaces` | `{}`; null workspace, revision zero |
| `tree` | `{}` |
| `read` | `path` (safe workspace-relative name) |
| `save` | `path`, `text`, `expected_hash` |
| `build`, `test`, `run` | `{}`; current target configuration only |
| `run_status`, `run_cancel` | `job_id`; also bound to exact workspace/channel/peer |

Status/cancel also address build/test jobs and check the original job capability.
No command, executable, argument list, interpreter, environment, launch profile,
PTY, Python object, raw LSP/DAP socket or generic RPC is accepted from the peer.
C1/C5/C6/C7 versions and dispatch remain independent.

Ask uses `ConnectApprovals → Host.confirm → approval.respond`, not a new approval
engine. The target sees peer, workspace, operation and safe relative filename.
Approval binds the immutable envelope fingerprint, TLS public fingerprint,
permission revision, workspace/share revision, request ID and expiry. File reads
and edits additionally bind the current content hash. Trees bind their bounded
result; workspace lists bind their current shared identities/revisions. Job
approval binds sanitized target configuration, workspace trust and bounded
project manifests. Changed content/configuration cannot reuse an approval.

Requester retries while awaiting Ask retain the exact envelope on the original
channel. Deny executes nothing. Allow once leaves Ask unchanged. Consequential
retries use durable receipts rather than executing again. There is no remote
approval route, Remember, automatic reconnect/resume or model-produced authority.

## Tree, reads, editor buffers and saves

Remote access reuses `Workspace.resolve`, `StudioService`, `EditingService` and
checkpoints. The remote policy is narrower than the local editor: UTF-8 text only,
64,000 bytes rather than the local 2 MiB maximum. Binary/NUL content, oversize
files, traversal, absolute/drive/UNC paths, backslashes, symlinks and Windows
junctions are refused. Existing ignored directories include Git internals,
virtual environments, node_modules, bin/obj and build/dist. Remote discovery
additionally excludes hidden components and named credentials/secrets directories.
The tree has explicit entry/depth/encoded-byte bounds.

Read returns exact text and SHA-256 of its original UTF-8 bytes. Save must name
that hash; the target rechecks current authority and source before writing.
Remote buffers never replace the target's local editor buffer. A dirty local
buffer refuses the remote save. Local/remote Studio saves share a workspace
writer reservation, checkpoints remain local, and staging rechecks the disk hash
and resolved path before atomic replacement. A target edit from X to Y produces
`revision_conflict`; it never silently overwrites Y or auto-merges source.

External editors do not participate in OLIVE's writer reservation. Hash checks
catch intervening changes through staging; this is not an OS-wide transactional
filesystem CAS guarantee against a hostile same-user process racing the final
rename. Local OS/profile compromise is outside the endpoint trust model.

The requesting Monaco editor retains separate buffers keyed by peer UUID,
workspace reference and relative file. The Remote view mounts on first explicit
selection, then remains mounted alongside Local within Studio. Offline drafts
remain visible as **Unsaved local draft**, are not
saved on the target, and require a fresh permission/hash check on Save. Reload
requires explicit discard confirmation when dirty. A window-close guard protects
unsaved drafts. Draft persistence across an application crash/restart is deferred;
C8 does not write target files automatically or synchronize drafts through C5.

## Structured build, test and run

The target adapter calls the existing Studio project/build/test controller and
RunService. Python build uses the existing standard compile operation; tests use
the existing structured unittest runner/report. .NET uses the target's existing
project scanner, build/test builders and configured startup selection. Project
references and solution members must remain inside the workspace. The peer cannot
substitute an executable, target path, configuration or arguments.

.NET build uses `--no-restore`; test and Run use `--no-restore --no-build`.
Dependencies/assets must already have been prepared locally. Missing dependencies
produce failure; C8 never runs pip/npm/package-manager installation or restores
packages in response. A separate local user may prepare dependencies using
existing local permissions, then retry explicitly.

Run is non-interactive with stdin closed. It uses the target's current validated
Python/.NET console configuration, filtered environment and bounded RunService
lifecycle. Stored interpreter choices must identify Python; executable/browser
launch profiles are refused remotely. Custom configured environment overrides
are not forwarded by the remote adapter. No terminal is created even when the
local Run UI ordinarily uses a PTY. Python GUI and web launch parity are deferred.

Remote execution of **untrusted** workspaces is refused, including Run: C8 does
not yet provide full remote lifecycle parity for an isolated container. It never
changes trust or falls back from required isolation to native execution. For
approved/trusted workspaces, execution retains Studio's existing native trust
boundary. Approved code/build logic can itself perform OS actions; native
execution is not a new syscall/network sandbox. Review workspace code before
granting Edit together with execution. C8 restricts protocol authority and entry
points; it cannot make arbitrary approved source code harmless.

Linux uses the existing owned supervisor and descendant reaper. Windows remote
pipe runs use a kill-on-close Job Object: create suspended, attach to the job,
resume, and close ownership on cancellation/root exit. Assignment/start failures
fail closed. This Windows adapter is included in portable CI, but has not been
executed on a Windows host during this Linux implementation session.

Status contains bounded recent output, exit code, state, test totals/duration,
and bounded structured diagnostics. Truncation is explicit. stderr alone never
means failure: warnings with exit zero remain successful. Absolute workspace
prefixes and path-shaped diagnostic tokens are removed from remote output.
Missing/unreadable test reports do not fabricate passed tests. Build artifacts
are not transferred; downloading an artifact remains an explicit independent C6
operation.

## Lifecycle, replay and limits

A remote job belongs to the exact authenticated channel, peer, share reference,
share revision and original request ID. Its transient record is an ownership
record, not cached permission. Execution rechecks authority/configuration and
serializes the launch boundary with authority writes. No remote job waits while
holding the Studio editor for its lifetime. A busy workspace is rejected.

Permission writes/removal, unsharing, revocation, observed channel loss and Connect
disable cancel affected owned jobs. Current authority is checked before status
output. Cancel returns `cancelling` until actual owner cleanup completes; subsequent
status reports `cancelled`. Target Stop requests the same lifecycle. Shutdown
awaits owner release and retires owned sessions/tasks/output; it does not merely
mark jobs terminal. Revocation also closes C3 and prevents fresh authentication.
Previously accepted edits remain ordinary target data and projects are not deleted.

The durable `(authenticated peer, request ID)` receipt is committed before a save
or launch. It stores an envelope digest and metadata-only result, never source or
logs. Identical replay returns the existing receipt after current authority;
changed duplicate rejects. A crash between claim and result yields indeterminate
outcome and never repeats the effect. Startup reconciles unfinished job receipts
as connection-lost/indeterminate. Lost acknowledgement cannot cause a second Run.
There is no distributed process resume or automatic consequential retry on a new
channel. These are at-most-once effects, not distributed exactly-once delivery.

| Resource | Bound |
| --- | --- |
| Shared workspaces | 8 per peer |
| Workspace ownership sessions | Existing C3 maximum 8 channels; no detached editor locks |
| Concurrent target file operations/saves | 1 under the Studio admission lock |
| Pending trusted Studio requests | 16, within C4's global 32 approval registry |
| Tree | 512 entries, depth 8, approximately 48,000 encoded entry bytes |
| Relative filename | 500 UTF-8 bytes |
| File read/save | 64,000 UTF-8 bytes |
| Frame | 400,000 bytes, including worst-case JSON escaping |
| Job configuration manifests | 64, each within the file bound |
| Build/test/run ownership | 2 globally, 1 per peer; no waiting job queue |
| Job lifetime | 120 seconds, plus bounded provider start/cleanup |
| Unpolled job | Cancel after 15 seconds without a requester status poll |
| C8 frames | 300 per peer/minute across reconnects; 256 rate buckets |
| C3 pending requests/write queue | Existing 8 each per channel |
| Visible recent output | 12,000 UTF-8 bytes per status |
| Diagnostics | 32 entries, 8,000 encoded bytes |
| Local provider output | Existing RunService 1,000,000 characters per stream; tooling 400,000-character tail |
| Structured report parsing | 1,000,000 bytes |
| Retained remote jobs | 32; completed tails eligible for retirement after 30 seconds |
| Requester editor buffers | 32 for the Studio session |
| Request / approval lifetime | 120 seconds; five-second future-clock tolerance |
| Durable receipts / dedicated Activity | 10,000 non-evicted receipts / latest 1,000 events |
| Protocol exchange / write | Existing C3 five-second request / two-second framed write |
| Studio shutdown owner wait | 8 seconds; failure is explicit |

Old completed sessions and tooling job output are retired along with their remote
job owners; this avoids accumulating process-output history outside the bounded
remote registry. OS buffers, native compiler memory and filesystem performance
are not hard real-time application quotas.

## UI, privacy and excluded authority

Devices retains its existing layout, adding shared workspace permission controls
and active remote job Stop. Studio adds Local/Remote selection, explicit peer and
workspace pickers, Online/Offline state, remote file editor and remote action
buttons. Remote files never masquerade as local project files. Failures do not
switch to a same-named local project or another device.

Remote operations are explicit Studio controls in C8. Natural-language remote
Studio/AI-edit composition is deferred: the remote view has no action-bearing AI
assistant. Existing Chat answer/action routing stays local to its own explicit
context. Selecting Remote AI never authorizes workspace edits, builds or Run.
C7 works with Studio Off and Studio works with `models.remote` Off.

Remote interactive stdin, terminal/PTY, debugger/evaluate, LSP, workspace search,
project creation, package installation, Git writes and read-only remote Git
metadata are deferred. Local features remain available through their existing
controllers. No SSH, SMB/NFS/WebDAV, filesystem.full, process.exec, desktop control,
Mail, browser, credential helper or generic Connect filesystem method is added.
C5 continues syncing only its established records; C6 stays separate.

Audit events use known `remote_studio_view/edit/build/test/run/cancel/denied`
labels, peer/request/workspace IDs, operation, result and timestamp. A dedicated
bounded metadata table retains workspace attribution; generic Activity has no
source code, filenames, output, environment or absolute roots. Successful status
polls do not flood Activity. Error responses are fixed categories, including
permission_denied, confirmation_required, workspace_unavailable/not_shared,
revision_conflict, unsupported_file, toolchain_unavailable, busy, cancelled,
connection_lost, configuration_changed and changed_duplicate. No traceback or
provider exception is used as the wire error.

Source code deliberately shared under View may itself contain secrets. Program
output can repeat secrets deliberately embedded in approved code. C8 is not an
automatic source/semantic-output secret-redaction product. It excludes hidden
credential paths, filters execution environment, omits configuration/credentials
from protocol, and never adds target-private context to Remote AI.

## Threat model and acceptance

A paired peer is untrusted input: strict C3 identity, exact share scope, current
permissions, revision checks, bounded schemas and durable claims constrain it.
Other peers cannot discover/use an unshared reference or hijack a job/channel.
Local source/configuration changes invalidate pending authority. Native execution
of approved source remains the target's existing code-trust boundary. Compromised
OS/profile, hostile same-user filesystem races, rollback of the entire profile,
physical LAN/firewall behavior and older-peer negotiation are not newly solved.

Portable tests retain real TLS, synthetic C2 vaults, C4 Host approvals, native
stores, real file bytes/checkpoints and real Studio process controllers. No GPU,
Ollama, KDE/KWallet, external network or .NET SDK is needed for the portable Python
fixture. Two spawned backends prove Off/Ask/Deny/Allow once, revisions, exact saves,
concurrent edits, build/test/run, replay, revocation and actual ownership release.
Additional tests cover source spoofing, third peers, traversal/symlinks/binary/size,
policy changes between claim/effect, dirty target buffers, staging races, changed
configuration, disconnect/no-resume, quotas, environment filtering, stderr success,
output bounds, restart receipts and owned descendants.

Native Electron acceptance uses the real Devices approval flow and Monaco remote
buffer, with a separate target process over C3. It covers sharing, defaults,
Allow once remaining Ask, editing, tests, Run/Stop, offline draft retention and
reconnect conflict. The full-container Linux harness uses two complete ordinary
ServiceContainers and already installed Python/.NET. It exercises Python
read/edit/build/test/run and .NET read/build/run. The owned .NET fixture has no test
package; no .NET test-package installation or passing .NET test claim is made.
Its local restore prepares only the fixture's existing SDK assets before remote
build; no remote operation performs restore.

Reproduce with the project venv and existing Node toolchain:

```
.venv/bin/python -m unittest discover -s tests -v
# Exact portable command: .github/workflows/connect-portable.yml
.venv/bin/python scripts/check_connect_studio.py
npm --prefix desktop test
npm --prefix desktop run typecheck
npm --prefix desktop run lint
npm --prefix desktop run build
# From desktop:
npx playwright test connect-studio.spec.ts studio.spec.ts connect.spec.ts
```

Set PATH/DOTNET_ROOT to an already-installed .NET SDK for full local integration;
missing tooling is not installed automatically. `connect-portable.yml` retains
`ubuntu-latest`, `windows-latest` and `fail-fast: false`, adding both C8 suites.
Hosted success requires a later push; this task does not push, merge, tag or
release, and no hosted Windows/Ubuntu result is inferred from local Linux runs.
Native Windows GUI/PTY/.NET parity remains unverified.

The subsequent hosted reconnect/newline failures and their local repair evidence
are recorded in [C8 portable repair](../../archive/repairs/OLIVE_CONNECT_C8_PORTABLE_REPAIR.md).

### Measured local results — 2026-09-20

All Python checks used the project venv. No missing toolchain was installed.

| Check | Result |
| --- | --- |
| Full Python discovery | 1,073 tests: 1,065 passed, 8 platform skips |
| Exact portable Connect workflow command, C1–C8 | 219 passed on Linux |
| C8 within that portable command | 21 passed |
| Frontend unit tests | 50 passed in 14 files |
| Typecheck / lint / production build | All passed |
| Focused native Electron acceptance | 11 passed: C8, C7, Devices, local Studio, Linux launcher/Wayland/reminders, browser and media |
| Two full isolated backend instances with installed Python/.NET | Passed; Python read/edit/build/test/run, .NET read/build/run |
| Repository Python compilation | All 653 Python sources passed |
| Literal `.venv/bin/python -m compileall -q .` | Existing ignored PySide6 Android Jinja template fails parsing; repository sources pass |
| Diff whitespace, branding, secrets and user-data review | Passed |
| Hosted Ubuntu / Windows matrix | Pending; no push performed |

The full Python run emitted an existing shutdown warning about 26 uncollectable
objects. The full-container acceptance logged unavailable Ollama connections and
passed without Ollama, confirming that Remote Studio does not depend on Remote AI.
Owned process release, cancellation and shutdown are asserted by the C8 tests.
The literal whole-tree compilation failure is inside the installed dependency's
`PySide6/scripts/deploy_lib/android/recipes/PySide6/__init__.tmpl.py`, whose Jinja
syntax is not Python source; the vendor template was left intact.

C8 implementation and local acceptance are complete with the documented scope
limits. Full cross-platform sign-off remains pending hosted Ubuntu/Windows runs;
Linux evidence does not certify the Windows Job Object path or native Windows UI.
