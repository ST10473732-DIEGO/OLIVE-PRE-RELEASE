# OLIVE roadmap

## Active: 3.5.1 Electron Experience and Native Personal Core

The latest Electron master brief supersedes Qt/QML as the final presentation. The existing 3.5 Qt work is a fallback checkpoint, not a completed release. M0/M1 builds a working Electron prototype; M2 migrates remaining actions, M3 completes native Personal Core, and M4 validates parity/security/packaging. Stop at the M1 and final user visual gates. [Tracked requirements](../releases/3.5.1/REQUIREMENTS.md).

## v3.5.0 Experience 2.0 + Native Personal Core — development

The fresh release brief is authoritative. M0 verification and a working M1
Welcome/Core/Home/Chat/Studio prototype are implemented on
`development/3.5-personal-core` as `3.5.0.dev1`. M1 visual approval is pending;
all later workspace redesign and Personal Core interfaces wait for that gate.
The [individual requirement ledger](../releases/3.5/REQUIREMENTS.md) tracks
mandatory scope and evidence separately. See the [visual review](../releases/3.5/M1_REVIEW.md).
No new account integrations, mail transport or native personal records are claimed.

## v3.4.1 Natural Language Interaction Core — complete

Shared Home/Chat semantic routing, bounded context, strict interpretations,
conversational drafts and existing capability integration are implemented.
Original and expanded paraphrases, compound tasks and required live application acceptance pass.
Final-pass fixes cover file-date constraints, selected-document grounding, draft
corrections, previous-application references and exact browser text preservation.
The user corrected the live Guaplings destination to #nepali-jerk-circle because
#general does not exist there. Navigation and the semantic preview are verified
for that destination. The user separately authorized one real "hello" send test;
one delivered message is verified visually and with read-only UIA; no further send is planned. This is test data, not an app alias.
Final results and provider limitations are tracked in
[the acceptance report](releases/3.4.1/DMDO_3_4_1_ACCEPTANCE.md).
Research follow-ups now carry bounded prior-report planning context, preserve the
original investigation and require fresh evidence for citations.
The completion pass adds generic attachment/tab routes, browser draft preparation,
project document linking, indexed topic lookup, media skip controls and an optional
interaction inspector. The broader evaluation contains 145 multi-domain samples.
That acceptance belongs to the preserved v3.4.1 tag; 3.5 development is tracked separately above.

## v3.4 release acceptance

The Qt desktop now uses one main shell with lazy cached workspaces, navigation history,
a collapsible rail and explicit pop-outs. Studio/editor state and shared services survive
page navigation. See [workspace shell](qt/QT_WORKSPACE_SHELL.md).

Intelligent model roles and universal Windows control are the current release scope.
Live UIA, a Qt inspector, bounded semantic planning, window capture, strict vision observations,
and a separate interactive browser are integrated. Browser/file handoffs and consequence
execution previews pass controlled local fixtures. Final acceptance adds real media playback,
Store search/install preview, LOGIN_REQUIRED handling and visual-label verification.
Localization remains limited. Clean-machine packaging and broader authenticated-app
reliability are post-release hardening. See [acceptance](releases/3.4/DMDO_3_4_ACCEPTANCE.md).
No 3.5 implementation has started.

## v3.3 Research, Browser and Web Knowledge

- Dedicated Qt Research workspace, history, bounded local-model planning and source/evidence reports
- Free replaceable search, public-only static HTTP and isolated rendered browser providers
- Deterministic tool permissions, citation validation and untrusted-content boundaries
- Approved website collections, incremental Knowledge indexing and manual refresh
- Project reports, bounded Studio handoff and controlled Agent research subtasks
- Disabled subscription and Tor/authenticated-provider foundations; no Tor connectivity

## Historical preparation notes following v3.3

Prioritize clean-machine Windows packaging, browser lifecycle/resource testing, wider research quality evaluation and a smaller installed-model performance matrix. Add opt-in scheduled source refresh only after explicit subscription controls and recovery tests. Monaco remains separate follow-up work. Email, calendar, voice, trading and universal desktop control require separate scoped releases.

## v3.2.5 PySide6 / Qt migration

- Native Qt Widgets Home and dedicated feature windows sharing one backend runtime
- Qt Studio docks, offline native editor adapter, controlled terminal and localhost preview
- Queued GUI updates, safe window state, global themes, tray and command palette
- Existing 3.2 services and v2/v3 data compatibility preserved
- Monaco remains a follow-up requiring offline assets and a minimal reviewed bridge
- See QT_RELEASE_REPORT.md for tested scope and remaining packaging acceptance work

The 3.2.5 baseline contains no Research implementation; public-web Research arrives in 3.3 above. Tor, email, calendar, voice, trading and universal desktop control remain outside both releases.

## v2 foundation — implemented in this rebuild
- OLIVE branding and local data directory
- Modular application architecture
- Legacy chat/settings import without deleting legacy data
- Ollama model service with streamed generation
- Model capability detection with vision fallback hints
- Chat history and settings persistence
- Correct regeneration branch bookkeeping
- Summarisation that does not pollute the visible conversation
- PDF, DOCX, text/code and native image attachments
- Page-aware document chunking
- Local SQLite hybrid RAG store
- Semantic retrieval through an Ollama embedding model when installed
- Lexical fallback when embeddings are unavailable
- Per-chat document knowledge bar and source reporting

## v2.1 intelligence foundation — implemented
- Context-budget planning with protected recent turns and automatic older-history summaries
- Ollama-backed model capability registry and context-window discovery
- Hybrid document retrieval with source metadata, relevance scores and deduplication
- Temporary attachments and persistent per-chat document knowledge
- Local searchable memory repository with edit, delete and deduplication services
- Testable generation pipeline separating memory, RAG, context and prompt construction
- Privacy-conscious rotating local application logs

## v2.2 retrieval and memory controls — implemented
- Automatic installed embedding-model selection and background upgrades of lexical-only indexes
- Tunable deterministic hybrid retrieval with diagnostics and duplicate suppression
- Per-response document sources and memory provenance stored outside answer text
- Memory review UI plus approval-required conservative suggestions
- Per-chat document status, chunk counts, re-indexing controls and background processing
- Safe local diagnostics view and idempotent RAG schema versioning

## v2.3 reliability and document intelligence — implemented
- Persistent recoverable indexing jobs with retry, pause, resume and cancellation states
- Page-level scanned PDF detection and optional local Tesseract OCR with provenance
- Content hashes and non-destructive stale/moved/changed source detection
- Retrieval evaluation metrics, score inspector and bounded embedding reads
- Post-generation grounding estimates kept separate from answer text
- Strict optional local-model memory proposals with deterministic safety gates
- Expanded data integrity checks and local diagnostics

## v2.4 user control and polished operations — implemented
- Validated ZIP backup/export and staged restore with automatic rollback backup
- Bounded persistent indexing scheduler with configurable local concurrency
- Source-file health badges and non-destructive document relinking
- Memory suggestion, local-model assistance, and approval controls
- Extensible local OCR provider API, Windows Tesseract discovery, and TSV confidence
- Versioned retrieval and grounding benchmarks with a standalone command
- Validated/resettable advanced RAG controls and compact response provenance
- Read-only data maintenance scans and Windows packaging readiness guidance

## v3.0 universal agent core — implemented
- Bounded PLAN/ACT/OBSERVE orchestration with cancellation and persistent task state
- Deterministic fast path plus generic local model routing roles
- Discoverable typed tool registry and normalized results
- Scoped ALLOW/ASK/DENY permission engine and reusable confirmations
- Safe foundational filesystem, terminal, and Windows application tools
- First-class projects, action audit history, and restart-safe task recovery
- Generalized knowledge provenance, research-provider, learning, and opt-in training interfaces
- Native Windows Tool Host boundary and optional future service/container design
- Minimal Chat/Agent mode, projects, tasks, permissions, and action-history UI

## v3.1 local workspace and coding agent — implemented
- First-class approved workspaces with bounded project discovery and recent-use metadata
- Git repository inspection plus permission-controlled safe write operations
- Incremental code indexing, lightweight symbol extraction, bounded code reading and deterministic search
- Atomic hash-checked targeted edits with task checkpoints and selective rollback
- Standard Python and .NET validation detection plus small offline project templates
- Visual Studio/VS Code launch services and task-scoped terminal-session metadata
- Project-aware memory ranking, path-scoped permission editing, and coding-loop failure guards
- Home feature registry, shared-service navigation shell, and dedicated feature workspaces
- OLIVE Studio real-file editor foundation with explorer, tabs, safe saves, Git/build status, Problems and Output
- Bounded RunService sessions with filtered environments, cancellation, URL detection and artifacts
- Future application-adapter and ACT/OBSERVE/VERIFY desktop-control contracts without input automation

## v3.2 intelligent coding and isolated execution — implemented
- Strict-schema Ollama coding plans validated against ToolRegistry definitions
- Bounded failure-driven replanning, duplicate-call protection, and explicit completion criteria
- Incremental repository maps plus hybrid exact, symbol, and semantic code retrieval
- Context-budgeted coding context with untrusted repository/tool-output separation
- Optional Docker execution provider for untrusted projects with network disabled by default
- Execution trust metadata, dependency-manifest inspection, and privacy-safe model timing
- Studio find/replace, go-to-line, symbol/language state, syntax preview, structured tests and deduplicated diagnostics
- RunSession-scoped application observations and strict optional vision-result validation

## Next upgrades
- Strict-schema Ollama coding planner with richer multi-step observation and action previews
- Code-index semantic embeddings and cross-language reference resolution
- Rich Show Changes, checkpoint rollback, and validation progress panels in Agent mode
- Better PDF layout/image understanding for scanned and diagram-heavy documents
- Local-model planner with strict structured tool-call validation
- User-friendly permission scope editor and richer task progress controls
- Optional benchmark history and retrieval-quality dashboard
- Packaging into a signed Windows installer
- Optional fine-tuned OLIVE model / LoRA once enough high-quality examples exist


OLIVE was formerly named DMDO. See [the rebrand compatibility map](../architecture/legacy-dmdo-compatibility.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.

## OLIVE Connect

- C1–C3: device identity, explicit pairing, permissions and opt-in authenticated local transport.
- C4/C4.1: [Devices workspace and trusted local Ask approvals](../connect/devices.md), with [ordinary desktop pairing and completion recovery](../connect/pairing.md).
- C5: [Structured record sync](../connect/protocol/c5-sync.md): Tasks, Calendar, Reminders and selected Chat continuity; shared data, never shared authority.
- C6: [Secure inert file transfer](../connect/protocol/c6-files.md): bounded authenticated bytes, OLIVE Inbox and explicit local Save.
- C7: remote AI.
- C8: remote Studio.
- C9: OLIVE Mobile.
- C10: Internet direct / relay.

C7–C10 remain future work. C5 structured records and C6 inert files do not grant remote execution or filesystem access.
