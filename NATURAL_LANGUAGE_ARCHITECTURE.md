# OLIVE 3.4.1 Natural Language Interaction Core

## Electron entry point (3.5.1 development)

Home and Chat submit trusted user text through the private Python bridge to the existing NaturalLanguageOrchestrator. React has no language parser and cannot grant permissions. Cross-route context remains in Python. Untrusted Markdown/editor/output content is presentation data, not intent. See `docs/releases/3.5.1/ARCHITECTURE.md`.

Status: 3.4.1 acceptance complete. OLIVE 3.5 has not started.
See [the current acceptance report](DMDO_3_4_1_ACCEPTANCE.md) for measured results and provider limitations.

## Entry points and execution

Home's composer and Chat call the shared `NaturalLanguageOrchestrator`. A user can
describe a task without opening Agent, Research or Desktop Control first. The
existing service container, Qt worker bridge and cached single-window workspaces
remain in place. Regenerate repeats an answer, never a previously executed action.

The sequence is user utterance → bounded interaction context → semantic
interpretation → deterministic entity resolution → capability router → existing
authorized controller/tool → observation and verification → conversational result.
Application launches use the installed application catalog after interpretation;
they do not invoke another planner simply to launch a known application.

Existing Agent keyword dispatch and the explicit desktop planning interfaces remain
advanced entry points. They are not the command language for Home or Chat. There is
no phrase lookup table or per-application regular expression in the language layer.
The small illustrative examples are schema documentation supplied to the model,
not synthetic conversation turns or reference-resolution candidates.

## Intent and model boundaries

Intents cover conversation, application launch/navigation/search/control,
communication compose/send, media, filesystem, coding, research, project selection,
Knowledge, Memory and task control. Calendar, email APIs, trading and other future
capabilities are not executable intents. Unknown fields, capabilities, actions,
duplicate JSON keys and malformed output are rejected.

The fast role, normally `qwen3:8b`, first distinguishes an action request from an
informational request and then produces a bounded structured interpretation. The
reasoning role is used for a bounded retry when interpretation fails validation.
Ordinary intent routing rejects coding, vision and embedding model assignments.
Code inspection uses the coding role only after routing to a bounded read-only
source inspection. Existing residency and context-budget policies still apply.

An informational interpretation cannot contain a mutating intent. Category hints
are not tool permissions. Low confidence or meaningful missing information leads
to a natural clarification. Model confidence never authorizes an action.

## Context, references and pending actions

Each conversation has an in-memory InteractionContext: recent user turns, selected
project/workspace/file, active browser tab, resolved entity slots, file candidates,
pending message, clarification and the last completed sequence. Context is bounded
to six recent turns and thirty file candidates; at most one hundred conversation
contexts are cached. It is not a copy of the full conversation or repository.

References resolve by named context slot. The other file resolves only when one
selected file and exactly one alternative exist. Ambiguous names remain unresolved.
Explicit Studio selection updates context once per changed selection; it does not
overwrite a later conversational file choice on every request.

A prepared communication can be corrected or cancelled. Correction does not submit
it, and an already sent message cannot be represented as an unsent corrected draft.
Repetition runs through fresh backend authorization. Cancellation stops future
operations; completed external changes are not undone. Pause currently applies
between semantic steps. Waiting during an outstanding send confirmation withdraws
that review and retains the unsent draft. Desktop's independent emergency stop remains immediate.

Chat messages persist through the existing repository. Interaction selections and
pending drafts are session-local and are not automatically replayed after restart.
No existing user data format is replaced.

Pending communications retain an action ID and originating conversation. Body
corrections preserve that identity and destination. Explicit browser attachments
use the selected path, the observed upload control and the existing read/upload
approvals. Merely selecting a file does not attach it to a later message. Native
and browser preparation refuse to overwrite unrelated existing draft text.

The generic taxonomy also includes application.activate, browser.navigate/search/
interact, communication.attach, media.next/previous, filesystem.copy and
project.add_file. Provider metadata maps supported browser identities to the
interactive engine after interpretation; application aliases and the remembered
media provider help choose a target. A browser tab remains separate from the
Research browser. Blank tabs do not grant arbitrary non-HTTP navigation.

Text entry first uses exact accessibility matches. Descriptive names can use a
bounded semantic selection among observed Edit/Document controls. Model-selected
controls still require ordinary keyboard/control authorization and exact read-back.
Field text is excluded from application-name extraction. Hierarchical destination
extraction separates application, community, channel and person without app rules.

Chat's optional Developer interaction details view shows the last interpretation,
resolved steps and selected providers. Normal responses and draft cards use natural
descriptions; developer state is copied and never used as permission or user input.

## Capability connections

| Request class | Existing execution boundary |
| --- | --- |
| Ordinary answers and selected-document questions | Chat, temporary document retrieval, filesystem read permission |
| Launch and native controls | DesktopController, catalog identity, DesktopGateway, UI Automation |
| Named hierarchical destinations | Fresh selectable controls and verified selection state |
| Browser navigation and one-step interaction | Separate interactive browser, fresh DOM targets, guarded controller |
| Code inspection | `code.read_file`, bounded excerpt, coding-role explanation |
| Code changes, run and tests | Agent and Studio controllers |
| Research | Research controller and persistent research repository |
| File search/open/move | Existing registered filesystem/system tools |
| Media | Existing media-session controller and bounded accessible search |
| Native communication | Visible destination/body bindings and existing consequence service |

Adapters remain optional. A live local-model request successfully entered and
verified `Hello from OLIVE` in the generic Qt acceptance application, which has no
dedicated adapter or language rule.

## Security and fidelity

Only UI-submitted user utterances enter the command channel. Retrieved documents,
webpages and accessibility observations remain labelled evidence. They cannot
grant permissions or answer confirmations. Typed text and message bodies must be
faithful to user input or the corresponding existing draft/context slot. A channel
cannot silently become a recipient address through cross-slot copying.

Native communication requires visible evidence for the requested destination,
exact body read-back and the existing one-time `communication.send` confirmation.
Browser interactions call existing guarded operations; consequential clicks are
not a fallback for sending, installation or purchase. Password/login controls
require user takeover. Acceptance scripts deny external sending by default. The
Discord harness has a separate explicit opt-in for one reviewed test message;
the current user authorized that test. A timeout never triggers a send retry.

## Evaluation and current limitations

Normal unit tests use deterministic fake model responses and provider fixtures to
test schema, routing, ordering, cancellation, reference resolution, fidelity,
permission preservation and Qt transport. They never operate the user's desktop.
`scripts/natural_language_evaluation.py` is an explicit local-model evaluation of
37 ordinary requests plus four compound requests. It checks meaningful entities as
well as intent labels. Live desktop scripts are separate and opt-in.

Acceptance is still being completed. Do not infer general application reliability
from a successful classification. In particular:

Historical checkpoint (2026-09-08): 458 automated tests and 48 visible Qt
smoke checks pass. The extended 30-case local-model evaluation passes 30/30;
it covers applications without language rules, files, browser navigation,
media, Windows Settings, coding, research, drafts, cancellation and references.
The original 37-case evaluation and four compound cases are tracked separately.
Evaluation samples live under scripts/ and are not imported by product code.

Historical live evidence from that checkpoint:

| Capability | Observed result |
| --- | --- |
| Adapter-free application | Natural-language field entry, exact UIA read-back and owned-window cleanup pass. |
| Interactive Chrome | Natural-language exact field fill, click, local-only send preview, upload, quarantine/file handoff, tabs and modal checks pass. Research browser is not used. |
| File search | Temporary PDFs with controlled dates: correct file selected, reference retained and actual document summary verified. The harness does not open an external PDF viewer. |
| Windows navigation | Explorer location and natural-language Bluetooth page navigation verified; no setting changed. |
| Discord | Requested server and channel navigation verified through selected state and the active window title. A message field exists; no invokable Send control was exposed in the tested tree. Native send confirmation was not reached. No message was sent. |
| Qt | One main window, retained workspaces, shared services, consequence previews, unsent draft card and deterministic Stop pass. |

Discord names are data, not rules. The live requested destination was guaplings /
#nepali-jerk-circle. The user subsequently confirmed this is the correct live
destination and that #general does not exist in this server. Original #general
semantic fixtures remain unchanged; no product alias was added. Matching accepts an optional
leading #, rejects similar names, and requires a fresh verified destination.
Generic window-title evidence is permitted only on the authorized Window control;
a similarly named sidebar link cannot itself prove navigation completed.

File-search constraints are extracted into a strict schema: filename/type,
folder, relative date, timestamp basis and recency. Ordinary code converts dates
and applies timestamp filters before the result limit. A unique result is selected
only when enumeration is complete. Multiple/truncated results remain ambiguous.
Downloaded dates are not proven by ordinary filesystem metadata: modified time is
an explicitly disclosed proxy. Creation time is used only when the platform
exposes it. Topic lookup falls back to indexed content in the current conversation,
filtered to the authorized folder and file type before ranking. It excludes denied
paths and discloses that it covers indexed documents only. Unindexed full-content
discovery and precise download-event history remain limitations; latest sorting does not justify choosing from a
truncated search.

Two selected-document defects were fixed: an informational follow-up could skip
reading the selected file, and lexical retrieval of a short pronoun query could
return no text. A semantic evidence-source check now selects authorized temporary
reading. Chat passes the selected document ID to conversation-scoped retrieval;
when no ranked match exists, a bounded opening excerpt is used with real source
labels and an explicit partial-document limitation. Re-indexing retains the
original source path instead of replacing provenance with the cache path.

Pending corrections use literal user-authored replacement fields, preserving
application/destination and unsent state. Holding a draft does not delete it.
The Qt draft card shows its destination and content, supports body editing and
cancellation, and offers Review Send. That button requests the existing flow;
it neither grants approval nor bypasses the consequence service. A missing native
submission capability remains a useful error with the draft retained.

Application references retain a bounded prior-app context while selected files
survive app switches. Schema-validated reference resolution distinguishes a
selected file from an explicitly named app. Focused semantic checks preserve
explicit application names and distinguish writing tests from running existing
ones. They are model interpretation, not phrase-specific command parsers.

Research follow-ups now retain the last investigation ID per conversation and
start a new investigation with the previous question and up to 6000 characters
of its report as explicitly untrusted planning background. Missing, unfinished,
or cross-project investigations require clarification. The original session is
preserved. Prior report text is not promoted to citable evidence; follow-ups must
retrieve evidence again. This uses the existing session context format.

Provider limitations:

- Native verified sending needs observable completion evidence. A generic reviewed
  editor-submit transaction now supports editors without an invokable Send control.
  It binds the exact body and destination, reviews keyboard input and communication
  separately, submits once, and requires a newly observed message outside the
  composer plus an empty composer. Chromium caret placement additionally requires
  mouse review. The corrected live Discord preview passes; one user-authorized hello
  is verified visually and by expanded read-only UIA. The updated submission verifier
  passes a local Chromium fixture with message evidence beyond the ordinary snapshot.
  No further external send was used to test that fix. A failure after dispatch leaves
  an uncertain action that cannot be replayed.
- Browser email-field preparation and reviewed attachment upload are connected;
  automatic verified browser submission and contact-name resolution remain limited.
  Native email subjects are not silently dropped.
- Named-song playback still depends on an accessible search/result and observable
  media session; semantic classification is not a claim of playback in every app.
- Research follow-up includes bounded prior-report planning context; full prior-evidence continuity,
  and generated-summary transfer remain incomplete. An optional developer inspector
  now exposes the latest interpretation and resolved steps.
- Natural pause is between steps and does not pause every backend sub-operation.
- Local-model latency varies, especially deliberate constraint extraction and
  reasoning fallback. Classification success does not guarantee provider support.

The required 3.4.1 acceptance matrix passes; the report distinguishes live execution,
semantic coverage and the provider limitations above. The annotated release is
v3.4.1. No v3.4.0 tag is moved.

No model downloads, new cloud dependency, new UI framework or 3.5 work is included.

### Final-pass interpretation and provider checks

URL entities are validated as credential-free HTTP(S) destinations before routing.
Returning to a running application must resolve to activation; an invented internal
browser URL is rejected and reinterpreted. Text-entry payloads must be literal
current-request wording or explicit validated references, so prior field content
cannot silently become a new input operation. Email form binding uses explicit
canonical field labels when available, with schema-constrained model selection
for remaining observed controls. Existing different drafts are retained.

When semantic domain classification identifies playback but the proposed control
is task pause/resume, a separate object classification resolves the scope. A
remaining disagreement receives a bounded reasoning-model retry. Literal outgoing
message content is masked in that classification. Neither model can grant a
permission or emit an executable free-form command.

Known recent-application activation is an exclusive semantic operation: a separate
operation decision precedes selection of a bounded known app name. Navigation,
typing, attachments and compound requests continue through the general planner.
This prevents an app return from inventing a URL or repeating earlier actions.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
