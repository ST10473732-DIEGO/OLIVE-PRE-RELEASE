# Project history: sources and evidence gaps

This is the evidence ledger for the first recovered project-history edition,
prepared on 26 September 2026. Read the [Journey](PROJECT_JOURNEY.md) for
chronology and [Decisions](PROJECT_DECISIONS.md) for recorded choices. The
2 October 2026 update at the end of this file records what changed afterwards. Repository reports were inspected; their application,
model, GUI and platform tests were **not re-executed** for this documentation task.

## Baseline and recovery boundary

`DOCUMENTED_BASELINE_HEAD`: `dd1a041dc0353710be83f2f02a1fad913265faf6`.
The desktop source branch is `feature/olive-unified-agent`; its remote-tracking
ref and `origin/feature/olive-mobile-c9` both pointed to this checkpoint after a
successful non-destructive fetch. The original worktree was clean on
`feature/olive-mobile-c9`. Documentation was isolated on
`docs/olive-project-journey` in the sibling `OLIVE-journey` linked worktree.
No mobile implementation was imported. Branch names describe the inspected
snapshot, not a promise about where those branches will point later.

The reachable root is
`95d3a3b` (`95d3a3bc4f0201e577842bc07978344e5c6bbd7d`),
dated 19 September 2026, whose subject identifies a Windows snapshot from
`c04337e`. It is a parentless snapshot, not the project's creation date. Earlier
eras survive principally in documents carried into that snapshot. The reports
describe missing Git objects and restored files; that historical damage should
not be confused with a fresh diagnosis of corruption in this clone.

`git cat-file` could not resolve the source-mentioned commits `c04337e`,
`637d947`, `ebe737e`, `0c4520d`, `96fb78b`, `15c89a2`, `8982efc` or `9cafe68`.
They are document references only, never presented here as recovered commits.
The available post-snapshot milestone hashes in the ledger below resolve locally.
No original Windows object store or private chat archive was recovered in this task.

Discovery covered the current tree, all local and remote-tracking branch tips
(20 distinct tip commits), reachable commit history, historical design trees,
and relevant source/contracts/tests. Exact-name searches included REX, Jev,
Laya, DMDO, OLIVE, Core, GO, Studio, Connect, REIMAGINE, Owner Mode and Grove.
The historical `origin/feature/olive-connect-c9` tree and its design specification
were read without switching the implementation checkout. No `CLAUDE.md`, root
`CHANGELOG.md`, root project licence, native mobile source tree or
`docs/OLIVE_MOBILE_C9_1_FOUNDATION.md` was found at the documented baseline.

Dates below follow explicit report dates or Git timestamps with their original
offsets. A report can be committed after the work it describes: the unified-agent
entry headed 23/24 September is one such boundary. Undated early stages use
version order rather than invented day-by-day dates.

## Evidence categories

| Category | What it establishes |
| --- | --- |
| VERIFIED IN CURRENT SOURCE | Implementation/configuration exists at the documented baseline; not proof of a fresh runtime pass. |
| RECORDED TEST RESULT | A named report, manifest or explicitly attributed commit body records a test. Its environment and scope remain attached. |
| OWNER-REPORTED STATUS | Narrative context supplied with this task, including the ongoing Mac session. |
| HISTORICAL IMPLEMENTATION | A retained report describes an earlier implemented stage, possibly without its original Git objects. |
| CONSIDERED / NOT IMPLEMENTED | A proposal or evaluation without evidence of integration. |
| SUPERSEDED BY A LATER CHANGE | A once-correct state displaced by a specified later source. |
| PLANNED FUTURE WORK | Intended capability, not a current product claim. |
| SOURCE NOT RECOVERED | Necessary evidence is absent; uncertainty remains visible. |

## Milestone ledger

Each row records the recovered goal/change, consequential problems or decisions,
source and evidence boundary. Detailed reasons are expanded in the decision log.

| Era / supported date | Goal, features, decisions and setbacks | Primary source and version reference | Classification / uncertainty |
| --- | --- | --- | --- |
| Early origins, date unknown | Personal assistant project; owner recalls REX → DMDO → OLIVE, but later calls the beginning Jev. | Task-supplied context; pre-existing Journey introduction, preserved below in the Journey history. | OWNER-REPORTED STATUS / SOURCE NOT RECOVERED. No REX implementation, acronym or naming rationale recovered. Jev is not established as a former name. |
| v2–2.4, before the recovered snapshot | Modular services, real regeneration branches, hidden-summary repair, document chunking/SQLite/embeddings with lexical fallback, Memory, OCR, persistent indexing and staged backup/restore. | Baseline README (`git show dd1a041:README.md`), “What changed in v2”, “2.3 reliability”, “2.4 operations”. | HISTORICAL IMPLEMENTATION. This retrospectively branded README says v2 renamed OLIVE; later DMDO release records prevent treating that as a securely dated rename. |
| 3.0–3.2 | Bounded agent loop and deterministic tool authority; approved workspace roots, Git, checkpoints, code retrieval, native versus isolated execution. | [Architecture](../architecture/overview.md), “Agent lifecycle”, “3.1 workspace boundary”, “3.2 coding intelligence”; [deployment](../archive/3.4/DEPLOYMENT_DESIGN.md). | HISTORICAL IMPLEMENTATION; original commits unavailable. Model suggestions and workspace text do not grant authority. |
| 3.2.5, migration audit 5 September | Flet → Qt; preserve services/data, separate application coordination, one async owner, offline native editor; Monaco deferred then. | [Qt migration](../archive/qt/QT_MIGRATION.md), “Pre-migration audit”; [release report](../archive/qt/QT_RELEASE_REPORT.md), “Requested completion report”. | HISTORICAL IMPLEMENTATION / RECORDED TEST RESULT: 184 tests after cutover, 27 visible checks. No clean-machine installer claim. |
| 3.3 | Public-web Research, evidence IDs, approved website Knowledge, isolated reading and quarantine. | [Research report](../archive/releases/3.3/RESEARCH_RELEASE_REPORT.md), “Desktop and live checklist”, “Validation limits”. | HISTORICAL IMPLEMENTATION / RECORDED TEST RESULT: 258 automated tests, 30 visible checks; citation validity is not semantic truth. |
| 3.4 / 3.4.1 | Single-window cached workspaces, Windows UIA and browser control, Home/Chat natural requests and contextual files/drafts. | [3.4 acceptance](../archive/releases/3.4/DMDO_3_4_ACCEPTANCE.md), “Results”; [3.4.1 acceptance](../archive/releases/3.4.1/DMDO_3_4_1_ACCEPTANCE.md); [interaction architecture](../architecture/natural-language.md). | HISTORICAL IMPLEMENTATION / RECORDED TEST RESULT. Preserve provider-specific limits; later Linux acceptance is separate. |
| 3.5 / 3.5.1, recovered 10 September | QML experience work, then Electron/React with one Python owner; damaged source/history recovery. | [3.5 M1 review](../releases/3.5/M1_REVIEW.md); [recovery](../releases/3.5.1/RECOVERY_REPORT.md), “Baseline and recovery”; [bridge architecture](../releases/3.5.1/ARCHITECTURE.md). | HISTORICAL IMPLEMENTATION. Fresh replacement evidence was explicitly distinguished from lost historical screenshots. |
| 3.5.1 M2–M4 / rebrand, September | Workspace parity, native Personal Core, Mail, data-preserving OLIVE identity. | [M2 closeout](../releases/3.5.1/M2_CLOSEOUT.md), [M3](../releases/3.5.1/M3_COMPLETION.md), [rebrand](../architecture/legacy-dmdo-compatibility.md), [M4](../releases/3.5.1/M4_COMPLETION.md). | HISTORICAL IMPLEMENTATION / RECORDED TEST RESULT. Rebrand's fresh run is dated 12 September; exact original rename motivation absent. |
| Workbench → clarity → GO / workspaces | Real LSP/DAP/PTY/.NET Studio, then labelled navigation and multi-project creation; native browser views and shared page composition. | [Workbench](../releases/3.5.1/WORKBENCH_REPORT.md), [clarity](../releases/3.5.1/CLARITY_REPORT.md), [GO report](../design/OLIVE_GO_REPORT.md), [GO parity](../design/OLIVE_GO_PARITY.md), [workspaces](../design/OLIVE_WORKSPACES.md). | HISTORICAL IMPLEMENTATION; original branch names survive in reports, not local refs. GO prototype is separate from production. |
| Functional work / Windows snapshot, 13–19 September | Chat code versus effects, presets, native media, Mail providers, WinForms subset, terminal input and launcher cleanup. | [Functional ledger](../archive/3.5/FUNCTIONAL_RELIABILITY.md), [Windows baseline](../archive/3.5/WINDOWS_STABLE_BASELINE.md), [media](../archive/3.5/BROWSER_AND_MEDIA.md); `95d3a3b`. | HISTORICAL IMPLEMENTATION / RECORDED TEST RESULT. Public results blocked by CAPTCHA, provider logins and installer acceptance remain separately classified. |
| Linux L1/L2/L3, 19 September | Native launch first; local GPU inference/PTY/tooling next; Secret Service, notifications, media and shutdown next. | [L1](../archive/linux/LINUX_L1_REPORT.md), [L2](../archive/linux/LINUX_L2_REPORT.md), [L3](../archive/linux/LINUX_L3_REPORT.md), [CI repair](../archive/linux/LINUX_CI_REPAIR.md); `da5abda`, `2d3eede`, `7ada881`. | VERIFIED IN CURRENT SOURCE / RECORDED TEST RESULT. “Linux control unavailable” was true here, superseded by unified-agent work. |
| C1/C2/C3, 19 September | Metadata and strict fixtures → vault-backed keys and TLS comparison → opt-in authenticated local networking. | [C1](../archive/connect/OLIVE_CONNECT_C1.md), [C2](../connect/protocol/c2-identity-pairing.md), [C3](../connect/protocol/c3-transport.md); `a37a6d7`, `e48577e`, `6f2823e`. | VERIFIED IN CURRENT SOURCE / RECORDED TEST RESULT. C2 had no sockets; C3's real acceptance used loopback/mDNS, not two physical laptops. |
| C4/C4.1, 19 September | Devices UI, actual state and exact Ask; temporary real pairing carrier and signed completion reconciliation. | [C4](../connect/devices.md), [C4.1](../connect/pairing.md); `2984d65`, `6f28642`. | VERIFIED IN CURRENT SOURCE / RECORDED TEST RESULT. Pairing grants no capability; manual recovery can be needed. |
| C5/C6, 20 September | Native signed record exchange/conflicts/selected Chat; inert hashed files and explicit Save. | [C5](../connect/protocol/c5-sync.md), [C6](../connect/protocol/c6-files.md); `5434675`, `a9cd078`. | VERIFIED IN CURRENT SOURCE / RECORDED TEST RESULT. Sync is manual; file resume and automatic imports remain excluded. |
| C7/C8 and repairs, 20 September onward | Text inference with explicit attribution; revision-bound shared Studio; cancellation, EOF, exact-byte and SQLite repairs. | [C7](../connect/protocol/c7-remote-ai.md), [C8](../connect/protocol/c8-remote-studio.md), repair sources below; `ab7f60a`, `9806e17`. | VERIFIED IN CURRENT SOURCE / RECORDED TEST RESULT. Local real-model/process tests do not certify every hosted Windows run. |
| C9 design, before V2 | Touch companion; five-tab artifact, truthful unavailable states and bounded remote capabilities. | [C9 specification](../design/OLIVE_MOBILE_C9_DESIGN.md), [HTML prototype](../design/olive-mobile-c9-artifact.html); `418cbf9`. | CONSIDERED / NOT IMPLEMENTED for native client at this checkpoint. Visual codes/word comparison are not new pairing wire formats. |
| V2 / Studio V2, 23 September | Semantic navy/blue/cyan system, denser desktop, IDE structure, capability-classified design. | [V2 design](../design/OLIVE_DESIGN_SYSTEM_V2.md), [Studio design](../design/OLIVE_STUDIO_V2.md), [implementation](../archive/design/OLIVE_DESIGN_V2_IMPLEMENTATION.md); `5000379`. | HISTORICAL IMPLEMENTATION / RECORDED TEST RESULT. Palette superseded by Grove; many structures retained. |
| Backend V3, 23 September | Preserve design while repairing toolchain discovery, completion/context/lifecycle and measuring candidates. | [V3](../archive/agent/OLIVE_BACKEND_V3_IMPLEMENTATION.md), [model selection](../architecture/model-selection.md), [toolchains](../archive/repairs/OLIVE_TOOLCHAIN_REPAIR.md), [image gate](../features/reimagine-qwen-image-2.1-gate.md); `2df73b3`. | RECORDED TEST RESULT; no candidate promoted at this stage. Qwen Image remained preparation, not integration. |
| Guarded Linux control, 23 September | Portal/helper foundation, consent/Stop route; later capture, PTY ownership and handshake fixes. | [backend closeout](../archive/linux/OLIVE_DESKTOP_BACKEND_CLOSEOUT.md), [unattended continuation](../archive/linux/OLIVE_DESKTOP_UNATTENDED_RUN.md); `a84b035`, `7b19f1d`. | HISTORICAL IMPLEMENTATION; blocked native acceptance then, superseded later. Vision gate failed. |
| Unified Chat / Owner / freeform, 24 September | Owner-authorised named KDE grant, actual input, one Chat; Copy and code-routing repairs; finite authority and derived page-to-note results. | [unified implementation](../archive/agent/OLIVE_UNIFIED_AGENT_IMPLEMENTATION.md), [Chat repair](../archive/agent/OLIVE_CHAT_AGENT_REPAIR.md), [Owner](../security/owner-mode.md), [freeform](../archive/agent/OLIVE_AGENT_FREEFORM_CLOSEOUT.md); `f7efb50`, `9e4d915`, `340c755`. | VERIFIED IN CURRENT SOURCE / RECORDED TEST RESULT. Owned messenger ≠ Discord. Kate crash cause not established. |
| Final unified / native Discord, 25–26 September | Goals/conditions/completeness, controller inventory, OS controls, B promoted to MAX; later actual Discord sends, DMs and model-swap repairs. | [final closeout and addenda](../archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md); `20a97db`, `b87cf83`, `c2d2290`; baseline commit `dd1a041`. | RECORDED TEST RESULT and current code. Baseline commit body records 8/8 channel and 7/7 DM live runs; no new full-suite result follows from those figures. |
| Grove, 26 September | Olive neutrals/pimento, bundled fonts, seven spaces, shared mark and darker frame. | [Grove](../design/OLIVE_GROVE.md), `4728711`, `3f3fbf8`, `dd1a041`; current navigation, tokens, logo and package files. | VERIFIED IN CURRENT SOURCE; owner-approved direction recorded by the design note. No complete post-Grove platform acceptance inferred. |
| Mobile / OS, task date | Native C9.1 being built separately on Apple Silicon for iPhone 15 Pro Max; separate apps around Core and eventual OS. | Owner-supplied task context; [Core boundaries](../architecture/core-app-boundaries.md); accessible mobile ref still equals desktop baseline. | OWNER-REPORTED STATUS / PLANNED FUTURE WORK. No accessible Swift build or phone-acceptance report. |

## Repair sources and current-state checks

The [portable lock repair](../archive/repairs/OLIVE_CONNECT_PORTABLE_LOCK_REPAIR.md),
[Windows lifecycle repair](../archive/repairs/OLIVE_CONNECT_WINDOWS_LIFECYCLE_REPAIR.md),
[C6 repair](../archive/repairs/OLIVE_CONNECT_C6_PORTABLE_REPAIR.md),
[C8 portable repair](../archive/repairs/OLIVE_CONNECT_C8_PORTABLE_REPAIR.md) and
[C8 storage repair](../archive/repairs/OLIVE_CONNECT_C8_STORAGE_REPAIR.md) distinguish deterministic
reproductions from original hosted failures whose lock owner or exception was
not captured. Their local passing repetitions are not fresh hosted passes.

Current source checks include [identity](../../olive/identity.json),
[profile resolution](../../olive/identity.py), [preset catalogue](../../olive/services/presets.py),
[navigation registry](../../desktop/src/navigation/features.ts),
[Grove CSS](../../desktop/src/design/grove.css), [theme tokens](../../desktop/src/design/tokens.css),
[message evidence](../../olive/desktop/messaging_context.py),
[visual messaging](../../olive/desktop/linux/visual_messaging.py),
[Python metadata](../../pyproject.toml) and [desktop metadata](../../desktop/package.json).
Setup was checked against [Windows setup](../../setup_windows.bat),
[Windows launch](../../run_olive.bat), [Linux launch](../../run_olive.sh), requirements
and the existing workflow definitions. These checks executed no application code.

Several older guides retain superseded assertions: Qt as default launcher,
read-only terminal output, absent LSP/debugging, no Linux desktop control,
MAX on the old coder model, and no Discord send. The new narrative names their
later sources rather than editing those historical reports. The pre-existing
README's v2 rename statement and the later dated rebrand report conflict; the
timeline deliberately does not turn that contradiction into a fabricated date.

## Specific missing evidence

1. **Original REX material:** source/archive, dated screenshots and the conversation
   identifying its purpose, name expansion if any, and transition to DMDO.
2. **Jev clarification:** the original naming/model discussion. The supplied context
   describes a model proposal; recovered code/docs do not establish a shipped Jev
   integration or a product rename. Laya has similarly sparse negative references.
3. **DMDO origin and rename reasons:** earliest code and naming conversations. No
   acronym expansion is established. “Operating Layer for Intelligence, Vision &
   Execution” was not found in the inspected identity or repository text; it is
   not asserted as the current official OLIVE expansion.
4. **Pre-snapshot Git objects:** original Windows history/backup if available,
   especially the commits named above. The snapshot and surviving reports support
   a feature chronology, not reconstruction of every earlier diff or tag.
5. **Decision conversations:** original reasons for the first local-first choice,
   first OS postponement and some visual pivots. Where absent, the decisions log
   says the reason was not recorded; owner-supplied future vision is labelled.
6. **Visual archive:** source-identified early Flet/REX/DMDO images and approved,
   privacy-reviewed Grove desktop/phone prototype exports. Existing V2 captures
   are historical, not current Grove or physical-iPhone screenshots. No raw
   desktop/test recording was republished for this edition.
7. **Latest verification:** a consolidated regression record at/after Grove and
   the final DM fixes; fresh native Windows certification and exact hosted matrix
   outcomes where the individual reports leave them pending. Older green totals
   remain tied to their tested commits.
8. **Mobile acceptance:** the Mac's committed C9.1 report, native project, signing
   status, simulator/generic-device/physical-iPhone results and a safe screenshot.
   Unpushed Mac work is inaccessible here. C9.2 pairing/inference and C10 remain
   future milestones until their own evidence exists.
9. **Project licence:** no root licence declaration was found. Component notices
   do not establish a licence for OLIVE as a whole; the owner must supply that
   decision before documentation can state one.

The relevant project sources were inspected, not private browser profiles,
account storage or unrelated conversation logs. External model/licence claims
are reported as what the historical review recorded, not a fresh upstream audit
or present commercial-use assurance. No web research was used to add new claims.

## Maintaining this edition

Add new evidence with its tested commit and platform, then update current claims
in the README. Retain prior failures and distinguish new complete runs from
focused reruns. Do not add Connect counts to full Python counts when they overlap.
Integrate the documentation only after the mobile work is safely checkpointed:
review a merge of this documentation branch and reconcile both versions of
`PROJECT_JOURNEY.md` manually. Do not resolve that shared history file by taking
one side wholesale.

## Checks on this documentation edition

A lightweight local check resolved the four documents' relative file links and
heading anchors, verified pinned GitHub source objects against local Git, checked
code-fence balance and table column counts, and confirmed that the previous
Journey's milestone body remains verbatim. All referenced accessible milestone
commits resolved; the eight explicitly listed unavailable early hashes remain
evidence gaps. Targeted scans found no personal absolute paths or secret-shaped
values in the four documents. `git diff --check` passed. These are document
checks, not a browser-rendering review or an exhaustive secret audit.

Only the four requested Markdown files changed. Application tests, model tests,
GUI acceptance and platform builds were not rerun, in accordance with this task's
documentation-only scope. The existing implementation checkout was left unchanged.

## Update, 2 October 2026 (OLIVE 1.0 PASS 2A)

This edition was brought into `release/olive-1.0` selectively; the branch was not
merged and its README rewrite was not taken. `PROJECT_JOURNEY.md` was reconciled
by hand, as the section above asks: the branch's recovered chronology comes first,
every entry `main` had appended since `dd1a041` follows unchanged, and new entries
from 27 September to 2 October cite commits and the current reports. Links now
point to the restructured `docs/` tree; historical reports moved to `docs/archive/`
with their content unchanged. Links to the hosted repository were replaced by
commit references, which resolve in any clone.

Gaps above that later evidence closes:

- **Mobile acceptance (item 8).** The native project is in `mobile/ios/`. C9.1–C9.3
  physical-iPhone results are in the archived C9 reports, and later Notes, Draw and
  Connect World acceptance is recorded in the current feature documents.
- **Project licence (item 9).** A proprietary source licence (`LICENSE`) was added
  on the owner's decision of 2 October 2026.

Still open: the original REX/Jev/DMDO naming sources, pre-snapshot Git objects, a
consolidated full regression at a single post-Grove commit on every platform, and
fresh Windows certification of the current tree.
