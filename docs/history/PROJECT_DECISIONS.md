# OLIVE project decisions

This selective log records choices supported by the recovered repository and the
owner's supplied context. It is not a reconstruction of private thoughts. The
[Journey](PROJECT_JOURNEY.md) gives chronology and [Sources](PROJECT_HISTORY_SOURCES.md)
fixes the first edition's evidence boundary at
`dd1a041dc0353710be83f2f02a1fad913265faf6`. Notes headed *Later outcome* and
decision 17 were added on 2 October 2026 (OLIVE 1.0 PASS 2A) from the commits and
reports named in the Journey, up to `b026b60`. Tests cited in those documents were
inspected, not repeated for this edition.

## 1. Keep local data and model services central

**Problem.** Chat, documents and later personal records needed continuity across
UI changes and imperfect local model availability.

**Options and choice.** The recovered architecture uses local repositories and
Ollama-backed services, with parsed documents indexed and retrieved in chunks.
Semantic retrieval is preferred when its configured model exists; lexical
retrieval remains usable without it. No source establishes a formal early vote
between local-first and a particular commercial cloud architecture.

**Recorded reason.** Local-first is an explicit product constraint. The original
personal motivation for choosing it is not recorded in the recovered sources.

**Trade-off and outcome.** The user retains local state and can work without a
paid inference dependency, but installed models, GPU capacity and OS integration
become real operational responsibilities. Public-web research and optional mail
connections do not make the whole product offline-only.

**Evidence.** [Architecture](../architecture/overview.md), [Core](../architecture/core.md),
[model presets](../features/chat-modes.md), baseline README (`git show dd1a041:README.md`).

## 2. Change interfaces while preserving the application core

**Problem.** The Flet interface mixed UI coordination with application behaviour;
the product later needed a richer desktop surface.

**Options and choice.** Move first to Qt with UI-neutral coordination, explore
QML, then implement Electron/React around the supervised Python backend. Qt
remained a fallback rather than a hidden dependency of normal Electron launch.
The Qt-era offline editor adapter was used before later richer Studio tooling.

**Recorded reason.** The migration audit calls for preserving service/data
behaviour and defining asynchronous ownership while replacing the UI. The
Electron architecture records the trusted process boundary. It does not supply
a complete original comparison of every alternative desktop framework.

**Trade-off and outcome.** A reusable backend avoided wholesale logic duplication;
bridge contracts and child-process ownership introduced their own testing needs.
Current `main.py` remains small while logic lives under `olive/`.

**Evidence.** [Qt migration](../archive/qt/QT_MIGRATION.md), [Qt release](../archive/qt/QT_RELEASE_REPORT.md),
[3.5 review](../releases/3.5/M1_REVIEW.md), [Electron architecture](../releases/3.5.1/ARCHITECTURE.md).

## 3. Rebrand without abandoning existing profiles

**Problem.** OLIVE needed a shared product identity while existing installations
still used DMDO names and paths.

**Options and choice.** Change product-facing identity centrally; preserve legacy
application identifiers and reuse existing profiles in place. Explicit configured
paths remain authoritative. Do not erase the source profile during migration.

**Recorded reason.** The rebrand report explicitly treats compatibility and data
preservation as requirements. Why the owner originally chose the name OLIVE is
not recorded. Neither an official acronym nor Jev as a former identity is proven.

**Trade-off and outcome.** Historical strings survive intentionally inside the
product. Current Linux resolution also recognises XDG data placement, so a generic
older default-path statement is insufficient to describe every current platform.

**Evidence.** [Rebrand](../architecture/legacy-dmdo-compatibility.md), [identity](../../olive/identity.json),
[profile resolver](../../olive/identity.py), [naming gaps](PROJECT_HISTORY_SOURCES.md#specific-missing-evidence).

## 4. Separate model suggestions, evidence and execution authority

**Problem.** Retrieved web pages, model plans and workspace text can contain
untrusted instructions or incorrect claims.

**Options and choice.** Use typed, bounded tools and deterministic policy checks;
keep source evidence identifiable and gate durable Knowledge ingestion. A planner
can suggest an effect but cannot approve itself by writing persuasive text.

**Recorded reason.** The architecture makes authority separate from model output.
Research's quarantine and approval paths prevent scraped text from silently
becoming trusted instructions or permanent knowledge.

**Trade-off and outcome.** The system needs explicit adapters and policy plumbing.
Citations prove a relation to retrieved chunks, not semantic correctness. This
boundary persists even when the visible experience becomes one ordinary Chat.

**Evidence.** [3.x architecture](../architecture/overview.md),
[Research report](../archive/releases/3.3/RESEARCH_RELEASE_REPORT.md), [Owner Mode](../security/owner-mode.md).

## 5. Keep normal code answers separate from project effects

**Problem.** A user asking for code could be routed into Studio inspection instead
of receiving an answer; selected-workspace context could also be lost.

**Options and choice.** Keep ordinary explanation/code generation in Chat. Use
explicit workspace context and typed action routing when the request actually
calls for inspecting or changing a project. Studio's answer-only assistant does
not acquire automatic write/run permission by displaying generated text.

**Recorded reason.** The repair records identify the routing defect and the
owner's expectation that normal Chat should answer normal requests.

**Trade-off and outcome.** Intent and workspace association must be handled
carefully. Later repairs improve local action routing without making every code
snippet an instruction to create a project or start a build.

**Evidence.** [Functional ledger](../archive/3.5/FUNCTIONAL_RELIABILITY.md),
[Chat repair](../archive/agent/OLIVE_CHAT_AGENT_REPAIR.md), [final closeout](../archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md).

## 6. Prove Connect in stages, with pairing separate from permissions

**Problem.** A companion must know which peer it is talking to and what that peer
may do; discovery alone establishes neither.

**Options and choice.** Establish bounded protocol/storage fixtures, then
cryptographic pairing, then authenticated LAN transport and UI. C2 selects pinned
TLS 1.3 with exporter-bound human confirmation rather than designing an ad hoc
cryptographic channel or adopting the discussed Noise route. Pairing does not
implicitly grant sync, inference, file or Studio permissions.

**Recorded reason.** The C2 design records the TLS choice and its binding to the
existing identity/confirmation requirements. C3 explicitly treats discovery as
untrusted. Each later capability keeps its own Off/Ask/Allow authority.

**Trade-off and outcome.** Both peers must confirm, interruption needs recovery,
and capability approvals remain visible. C4.1 adds the temporary real carrier and
signed completion receipts without reducing pairing to a decorative six-digit
mockup. Real LAN/mobile deployment still needs its own acceptance evidence.

**Evidence.** [C1](../archive/connect/OLIVE_CONNECT_C1.md), [C2](../connect/protocol/c2-identity-pairing.md),
[C3](../connect/protocol/c3-transport.md), [C4 pairing](../connect/pairing.md).

## 7. Sync native records rather than copying a live database

**Problem.** Independent computers can edit records concurrently, and timestamps
alone cannot safely resolve every conflict.

**Options and choice.** C5 exchanges selected signed native records with stable
identifiers, version vectors and explicit conflict handling. It does not copy a
live database or use unconditional last-writer-wins. Attachment bytes and local
notification delivery are separate concerns.

**Recorded reason.** The protocol preserves record meaning, selection and conflict
visibility without synchronising machine-local storage internals.

**Trade-off and outcome.** Sync is manual and users may need to resolve conflicts.
The initial contract covers specific native types and selected Chat, not a promise
that every future feature or local setting already synchronises.

**Evidence.** [C5](../connect/protocol/c5-sync.md), [portable lock repair](../archive/repairs/OLIVE_CONNECT_PORTABLE_LOCK_REPAIR.md).

## 8. Receiving a file must not imply running or importing it

**Problem.** Transport success could otherwise become an unexpected overwrite,
execution or application import.

**Options and choice.** C6 verifies bounded file bytes into an inert inbox, then
requires explicit handling/Save. Exclusive finalisation protects existing paths.
Automatic execution and resumed transfers are outside the implemented contract.

**Recorded reason.** The report separates transfer authority from authority to
apply content. Portable repair preserves that contract across Windows handles
and file-system finalisation behaviour.

**Trade-off and outcome.** An interrupted transfer restarts rather than pretending
to resume. Transfer-instance ownership and writable-handle fsync avoid silent
corruption or a stale cleanup removing a replacement transfer.

**Evidence.** [C6](../connect/protocol/c6-files.md), [C6 portable repair](../archive/repairs/OLIVE_CONNECT_C6_PORTABLE_REPAIR.md).

## 9. Remote execution should be bounded and visibly attributed

**Problem.** A remote answer or process could be mistaken for local execution,
and an overly broad Studio surface would expose more authority than intended.

**Options and choice.** C7 shows explicit remote inference attribution and returns
failure rather than invisibly changing computers. C8 grants named operations on
specific shared workspaces with revision-bound writes. Interactive shells,
debuggers, LSP, Git and package installation are not included in its first scope.

**Recorded reason.** The contracts keep execution location, selected workspace
and permitted effects explicit. Model availability is not permission to execute.

**Trade-off and outcome.** Remote Studio has fewer capabilities than local Studio.
Cancellation must retire actual resource owners, and revision conflicts need
user handling. Those restrictions are product boundaries, not missing buttons
that can be enabled safely by changing a view.

**Evidence.** [C7](../connect/protocol/c7-remote-ai.md), [C8](../connect/protocol/c8-remote-studio.md),
[Windows lifecycle repair](../archive/repairs/OLIVE_CONNECT_WINDOWS_LIFECYCLE_REPAIR.md).

## 10. Repair ownership and transaction boundaries, not test timing

**Problem.** EOF/reconnect races, cancelled inference, writer contention and audit
failures produced unstable cleanup or misleading completion.

**Options and choice.** Tie cleanup to the exact channel/process/transfer owner,
use explicit synchronisation signals, avoid writer reservations for ordinary
reads, and commit authority changes before acknowledging success. Tests preserve
byte and lifecycle assertions rather than papering over failures with sleeps.

**Recorded reason.** The repair reports connect failures to concrete ownership
and transaction defects. They distinguish reproduced causes from original hosted
incidents whose lock owner or precise exception was not captured.

**Trade-off and outcome.** More explicit state is needed, but failures become
bounded and inspectable. Repeated local passes validate the reproduction; they
are not a fabricated fresh hosted Windows matrix.

**Evidence.** [C8 portable repair](../archive/repairs/OLIVE_CONNECT_C8_PORTABLE_REPAIR.md),
[C8 storage repair](../archive/repairs/OLIVE_CONNECT_C8_STORAGE_REPAIR.md),
[Windows lifecycle repair](../archive/repairs/OLIVE_CONNECT_WINDOWS_LIFECYCLE_REPAIR.md).

## 11. Promote models from measured role gates, not recommendations

**Problem.** A newer or advertised stronger model may fail OLIVE's actual output,
latency, memory or tool-selection requirements.

**Options and choice.** Backend V3 evaluated candidates against existing baselines
and retained the current mappings when candidates did not satisfy the role gate.
Later less-refusal Candidate B first passed finite local checks, then separately
passed the promotion gate and became MAX. The earlier local pass alone was not
a promotion decision.

**Recorded reason.** The reports use observed role behaviour and bounded tests,
not publisher labels or generic benchmark claims. FAST and NORMAL remained
unchanged; DEEP is a workflow, not an extra model proven by renaming it.

**Trade-off and outcome.** MAX now pins the accepted Qwen-based Candidate B;
the prior coder model remains a historical/rollback reference. Finite successes
do not establish unrestricted competence or universal compliance.

**Evidence.** [V3 model selection](../architecture/model-selection.md),
[repository/model review](../archive/models/OLIVE_REPOSITORY_MODEL_REVIEW.md),
[freeform closeout](../archive/agent/OLIVE_AGENT_FREEFORM_CLOSEOUT.md),
[final closeout](../archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md), [current presets](../../olive/services/presets.py).

## 12. Keep image research distinct from a working runtime

**Problem.** REIMAGINE needed improved image capability, but a candidate's name or
model card did not establish local availability, licensing or runtime support.

**Options and choice.** Retain SDXL while preparing Qwen-Image-2.1 evaluation gates.
The latter remained preparation rather than a shipped replacement. Jev and Laya
likewise have no recovered evidence of an integrated production role.

**Recorded reason.** Download, licence, runtime and hardware gates were unresolved.
The SDXL tests themselves distinguished generated files from prompt-quality
success: producing an image did not mean count/colour requirements passed.

**Trade-off and outcome.** An existing path stays available, with known quality
limits. Historic licence review is not a current legal clearance, and proposals
must not appear in the README as already promoted models.

**Evidence.** [REIMAGINE gate](../features/reimagine-qwen-image-2.1-gate.md),
[V3](../archive/agent/OLIVE_BACKEND_V3_IMPLEMENTATION.md), [backend closeout](../archive/linux/OLIVE_DESKTOP_BACKEND_CLOSEOUT.md).

**Later outcome (to 2 October 2026).** FLUX.2 Klein 9B became the preferred
REIMAGINE engine for generation and edits. Qwen-Image 2.1 stayed blocked: the
installed ComfyUI 0.35.0 cannot load its layout. SDXL remains a compatibility
fallback that never edits and never outranks a validated newer engine
(`olive/services/media_workflows.py`, `ROUTES`). Licence review of the FLUX.2 and
video model files is still open release work, so neither is yet distributable.

## 13. One Chat, with task authority instead of repeated control rituals

**Problem.** A separate control page and repeated consent/shortcut steps obstructed
the owner's goal of asking OLIVE naturally to perform supported desktop tasks.

**Options and choice.** Move the user entry into ordinary Chat and provision the
supported named KDE authorisation route for the OLIVE helper. Add scoped Owner
Mode task grants, while retaining cancellation, explicit Deny and separate remote
capability authority. Fresh installations do not silently enable Owner Mode.

**Recorded reason.** The owner explicitly requested one assistant and less
redundant approval friction. The implementation records authenticated helper
identity, portal/PipeWire/EIS and accessibility integration; it is not a security
exploit, a root language model or permission to bypass arbitrary authentication.

**Trade-off and outcome.** Task grants still need scope, expiry and effect checks.
Native app acceptance replaced earlier blocked portal evidence. Actual Discord
sends arrived in later addenda after owned-messenger tests; those are distinct
proof points. Uncertain delivery should be checked rather than blindly retried.

**Evidence.** [Unified implementation](../archive/agent/OLIVE_UNIFIED_AGENT_IMPLEMENTATION.md),
[Owner Mode](../security/owner-mode.md), [final closeout and addenda](../archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md).

## 14. Use specialist grounding without making it the permission authority

**Problem.** A screen model could locate present targets yet invent locations for
absent ones; an independent verifier could also reject valid targets too often.

**Options and choice.** Evaluate GUI-Owl through an isolated local runtime and add
independent region verification. Repair false rejection using explicit present
and absent cases. Keep model proposals separate from typed actions and policy.
Earlier Qwen-VL/UI-TARS discussions are not evidence of a shipped replacement.

**Recorded reason.** The measured failure modes required checking both target
presence and absence. Successful coordinate benchmarks were deliberately kept
separate from live input acceptance.

**Trade-off and outcome.** Verification improves bounded grounding but adds latency
and its own failure modes. Later deterministic messaging paths did not require
the vision model for every action. No finite region benchmark proves arbitrary
application control.

**Evidence.** [Linux control](../features/desktop-control-linux.md),
[unified implementation](../archive/agent/OLIVE_UNIFIED_AGENT_IMPLEMENTATION.md),
[final closeout](../archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md).

## 15. Evolve the visual system without deleting capabilities

**Problem.** Workspaces and IDE features increased navigation density, while the
product needed a coherent identity across desktop and future mobile use.

**Options and choice.** Workbench's global tabs gave way to labelled clarity
navigation, V2/Studio V2 semantic structure, then Grove's seven spaces, olive
neutrals, pimento and shared mark. Existing feature routes remain reachable.

**Recorded reason.** The design records specify hierarchy, clearer navigation and
approved direction. They do not provide measured productivity gains, usability
study participants or an original personal rationale for every colour change.

**Trade-off and outcome.** An old screenshot may accurately show an implemented
era while no longer representing current OLIVE. Grove is the latest authority;
V2's navy palette and historical C9 mockup must not override it. No new logo was
created for this documentation task.

**Evidence.** [Clarity](../releases/3.5.1/CLARITY_REPORT.md),
[V2](../design/OLIVE_DESIGN_SYSTEM_V2.md), [Grove](../design/OLIVE_GROVE.md),
[current navigation](../../desktop/src/navigation/features.ts).

## 16. Build a mobile companion and keep the OS vision separate

**Problem.** OLIVE needs a usable phone interface without copying its desktop
backend, databases or unrestricted owner authority onto the phone.

**Options and choice.** The C9 design proposes a native companion using Connect;
the owner reports SwiftUI foundation work now underway on the Mac. Separate apps
around shared Core are the longer-term direction, with OLIVE OS beyond the
current desktop and mobile milestones.

**Recorded reason.** The supplied owner context prioritises a real native phone
foundation before pairing and remote Chat. Core boundary documentation explains
shared capabilities and future app separation. The original conversation deciding
when to postpone an OS was not recovered; no additional motivation is invented.

**Trade-off and outcome.** Desktop completion does not prove mobile acceptance.
C9.1 needs its own build/signing/device report, C9.2 needs real pairing/inference
proof, and C10/OS remain future work. Existing workspaces are not automatically
independently shipped applications.

**Evidence.** [C9 design](../design/OLIVE_MOBILE_C9_DESIGN.md),
[Core/app boundaries](../architecture/core-app-boundaries.md), owner-supplied task context,
[mobile evidence gap](PROJECT_HISTORY_SOURCES.md#specific-missing-evidence).

**Later outcome (to 2 October 2026).** The native companion was delivered:
C9.1–C9.3 on physical-iPhone evidence (C9.3 complete under an owner-revised,
platform-limited gate), then full Chat-mode parity, Notes, Draw and Connect World,
all with the paired computer doing the work. The phone still holds no desktop
backend or database. For OLIVE 1.0 the owner set the targets as Linux, Windows
and macOS desktops plus the iPhone companion; macOS desktop support is not yet
implemented. OLIVE OS remains future work.

## 17. Reach the phone away from home without new cryptography

**Problem.** Direct Connect works only on a shared local network. Away from home a
phone and computer usually cannot reach each other, and neither should need a VPN
or an open router port.

**Options and choice.** Connect World adds a relay that both sides dial out to over
WSS. The relay forwards the existing Connect TLS 1.3 session byte for byte; it
does not terminate it. Pairing, pinned identities, permissions and every Connect
frame are unchanged. Direct is preferred whenever it is healthy.

**Recorded reason.** Swapping only the byte stream under the existing TLS session
adds no application cryptography: end-to-end protection, forward secrecy and
replay protection are the ones Direct already has. Route credentials are derived
separately (HKDF with a distinct context) and never become TLS keys.

**Trade-off and outcome.** The relay operator cannot read content but does see
transport metadata: addresses, timing and byte counts. Operators run their own
relay from `world-relay/`; nothing in OLIVE requires a particular host. Production
acceptance passed on 1 October 2026; a stale-Direct failover defect found
afterwards was fixed on 2 October.

**Evidence.** [Connect World protocol](../connect-world/protocol.md) §1, §2, §4 and §14;
[Journey](PROJECT_JOURNEY.md#2026-10-01--connect-world).
