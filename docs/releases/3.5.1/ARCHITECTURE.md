# OLIVE 3.5.1 - current identity

OLIVE was formerly named DMDO. M3 remains complete; M4 native Mail is implemented.
See [the rebrand map](../../architecture/legacy-dmdo-compatibility.md). Historical checkpoint text below
retains its original scope. New code uses `olive`, `OLIVE_*` and `window.olive`.

## M4 native Mail boundary

`olive/mail/controller.py` registers strict shared capabilities in the existing
ToolRegistry/PermissionService/ConfirmationService path. `olive/mail/contracts.py`
generates matching strict Electron Zod contracts. Main owns native file dialogs
and validated file selections. React uses narrow `window.olive` methods, never
database/vault/socket access. No second runtime or profile writer is introduced.

MailStore is a separate additive SQLite schema 1, holding relational record IDs,
source keys, revisions and immutable hash-addressed blobs. Personal schema 4 is
unchanged. Submissions persist exact MIME/envelope/connection/draft fingerprints
before approval and use guarded single-flight transitions. Recovery never sends.
SMTP acceptance, recipient rejection, uncertain outcomes and remote Sent copies
are separate facts. IMAP uses connection/mailbox/UIDVALIDITY/UID identity, bounded
PEEK fetches, explicit remote mutation intent/outcomes and no broad EXPUNGE.

Current-user Credential Manager is accessed only by trusted provider code with
opaque profile-scoped references. A dedicated transient secret-entry route is
excluded from tool/model/audit content. No plaintext fallback exists. Mail HTML
uses DOMPurify and an opaque sandboxed frame with no bridge or remote resources.
Safe raster CID data is bounded and re-encoded. Original MIME remains evidence.

The existing interpreter/router handles Mail meanings and native Contact
resolution. Source-linked Calendar/Task proposals reuse Personal Core validation
and revisioned approval. Selected Mail Knowledge material uses existing indexing,
with explicit backed-up source snapshots. One optional runtime read-sync loop
respects configured connection preferences and existing Allow/Ask/Deny decisions;
it never drains an outbox. Existing Core aggregation reflects real Mail activity.

Backup uses SQLite snapshots, staged validation and cross-store relationship
checks. Restore disconnects transports, strips credential references, retains
uncertainty/dismissed reminders, and rebinds selected Mail Knowledge sources to
the target profile. See MAIL_TRANSPORTS.md, ACCOUNT_SECURITY.md and
[M4 evidence](M4_COMPLETION.md) for tested guarantees and limits.

# Electron / Python boundary

One sandboxed BrowserWindow loads bundled React through a restricted `dmdo://app` protocol. Context isolation and web security stay enabled; Node integration is disabled. Radix owns dialog focus, Motion owns short presentation animation, Lucide supplies the navigation icons, Monaco supplies the actual editor and diff view, and xterm supplies read-only output. Heavy editor/output bundles load on demand.

The preload exposes an allowlisted typed request API, a native workspace picker, an external-link action with scheme validation and native confirmation, and an event subscription with cleanup. It exposes neither raw IPC nor filesystem/process/secret primitives. Main verifies webContents identity, top-level sender frame, exact application URL, request ID, method and strict Zod arguments. Python independently validates the protocol and invokes explicit service callables. `ServiceContainer.dispatch` is not exposed as a general gateway.

Python runs one asyncio-owned ServiceContainer without Qt initialization. The existing NaturalLanguageOrchestrator, CapabilityRouter, InteractionContext, tool registry, permission service and confirmation service remain authoritative. Renderer text enters the same user-request path; Markdown, source code and output remain content. No React intent parser exists.

## Private protocol and ownership

Version 1 uses newline-delimited JSON over inherited private pipes. Frames are limited to 1 MiB; method fields have smaller bounds. Requests carry identities; events carry ordered sequence numbers. A request ID cannot change arguments or execute twice in the runtime. Renderer refresh obtains a snapshot and does not resubmit actions. No listening HTTP server is created.

Input/output queues and concurrent requests are bounded. Saturation stops control and disconnects rather than silently losing approval. The M1 implementation does not yet coalesce stream events or provide replay-by-sequence; snapshots recover current Chat, approvals, buffers and run state. The 2,048-request lifetime cap fails closed rather than forgetting deduplication identities. This requires improvement before final release.

The writer lock is shared with current Qt and also detects a live legacy Qt lock. Different frontends must not write the same profile concurrently. Older releases without this lock must never be launched simultaneously with a new writer. No data migration is introduced by M1.

Pipe EOF sets the existing desktop emergency-stop event from the reader thread. Renderer loss/unresponsiveness and Ctrl+Alt+Escape call the same stop path from main. Graceful shutdown cancels work, denies pending approvals, saves existing data and stops owned runs. Hard-crash/process-tree coverage remains a final-release acceptance item; this is not protection against every malicious same-user process.

## Editor and execution

Native folder selection establishes a workspace through existing repositories. Relative file reads/saves use Studio tools and workspace guards. Saves retain expected hashes and checkpoints. Compare reads the current bounded disk version without replacing the editor; rebasing requires the exact compared hash and existing approval, and does not itself save. A later Save authorizes the exact write.

Monaco models and view states survive route changes; dirty buffers are also retained in Python for renderer-refresh recovery. Model count is bounded at 32. Native close warns about retained unsaved buffers. Interactive PTY, LSP, full Git controls and all old Studio actions remain later parity work.

Validation now uses existing RunService instead of an unmanaged blocking subprocess. Native structured runs receive DEVNULL stdin so they cannot inherit the protocol input. Existing environment filtering and approved/untrusted execution-provider selection apply. Working directory is not advertised as an isolation boundary.

## Dependencies and primary references

Node 24.21.0 meets [Vite's supported Node requirements](https://vite.dev/guide/). TypeScript 6.0.3 was selected within typescript-eslint's peer range; 7.0.2 was rejected rather than forcing incompatible peers. Security settings follow [Electron security guidance](https://www.electronjs.org/docs/latest/tutorial/security) and the [custom protocol API](https://www.electronjs.org/docs/latest/api/protocol). Monaco workers follow the installed package exports and [official ESM integration guidance](https://github.com/microsoft/monaco-editor/blob/main/docs/integrate-esm.md).

Production packaging requires a separate Python artifact outside ASAR; the guard refuses an incomplete package. No default switch, installer publication, auto-update or release tag occurs at M1.

## M3 native personal boundary

`PersonalController` is owned by the existing ServiceContainer and registers
explicit tools with the existing registry/executor. The main/preload contract is
extended by `desktop/electron/m3-contracts.ts`; Python independently validates
`olive/personal/contracts.py`. Native file choosers resolve import/export/avatar
paths in Electron main, not through a renderer filesystem primitive.

`PersonalService` and `PersonalStore` own one profile-local SQLite database, schema
4, with transactional revisions, relationship validation and bounded records.
The runtime owns one persistent ReminderScheduler; route navigation never creates
another scheduler or backend. Its delivery history survives reload/restart and
is included in consistent SQLite backups. Restore stages and validates native
records plus cross-store Project/Agent references, quiesces work and restarts.

Home, Chat and Agent use the existing interpreter/orchestrator/router. Native
mutations prepare independently identified, revisioned proposals before the
existing approval path. Imported notes and source fields remain untrusted data;
no external account, mail transport or model-side interval arithmetic is added.
See PERSONAL_CORE.md and M3_COMPLETION.md for supported operations and recovery
limits. Historical M1 statements above remain scoped to M1, not a claim that M3
introduced no new storage.
