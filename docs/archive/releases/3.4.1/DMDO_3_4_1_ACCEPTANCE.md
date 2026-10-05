# DMDO 3.4.1 acceptance report

Status: DMDO 3.4.1 acceptance complete on 2026-09-10. All required validation gates passed with the evidence and provider limits below. The annotated release pointer is v3.4.1. The user explicitly authorized one real "hello" message to Guaplings/#nepali-jerk-circle. One actual message is visually verified and independently confirmed by updated read-only UI Automation observation with an empty composer. No further external sends will be performed. DMDO 3.5 was not started and v3.4.0 was not changed.

## Validation ledger

The original 37 cases, original four compounds, expanded 145 samples, deterministic automated tests, and live provider checks are separate measurements. A semantic classification pass is not evidence that an application was operated successfully. Expected outputs in the original evaluations remain unchanged.

Completed checks (2026-09-10):

| Check | Result |
| --- | --- |
| Compile | PASS |
| Automated suite including security regressions | 514/514 |
| Qt smoke | 49/49 |
| Original semantic cases | 37/37 on the final code; unchanged expectations |
| Original compounds | 4/4 on the final code; unchanged expectations |
| Expanded multi-domain suite | 145/145; subsequent affected previous-app case recheck 1/1; playback/task disagreement resolved with bounded reasoning fallback |
| Destination naming/paraphrases | 8/8 |
| File/date/open-reference/summary | PASS; external PDF viewer launch intercepted |
| Draft correction/cancellation | PASS; same pending identity and recipient |
| Windows navigation | PASS; Explorer and natural Bluetooth page, no setting change |
| Adapter-free Qt application | PASS |
| Browser and multi-app live regression | PASS after generic app-switch, current-text provenance and DOM field-binding fixes; same file and tab preserved |
| Discord destination and preview | PASS for user-corrected Guaplings/#nepali-jerk-circle |
| User-authorized real Discord send | One hello verified visually and by read-only UIA; no further sends |
| Local Chromium editor | PASS; reviewed text replacement, one local submission, receipt beyond 300 controls |

Historical checkpoints in the architecture document are explicitly identified as historical.

## Requested completion details

| # | Item | Implementation or evidence |
| --- | --- | --- |
| 1 | Previous keyword dependencies | The initial intent schema omitted browser, attachment, copy and media transport distinctions. File queries mixed filename globs with semantic date/type meaning. Short follow-ups could be classified as conversation or application launch. Browser return could invent about:blank navigation, and an attachment request could replay prior field text. Strict web-URL validation and current-request text provenance now trigger semantic retry before execution. Draft disposition and literal content extraction were conflated. Generic semantic stages now address these cases; evaluation sentences are not command mappings. |
| 2 | NaturalLanguageOrchestrator | Home and Chat enter the same user-authored front door: bounded context, speech-act classification, validated semantic intents, reference resolution, CapabilityRouter, existing permission/confirmation controllers, execution and observation. |
| 3 | Intent taxonomy | Generic conversation, application, browser, media, communication, filesystem, code, research, project, knowledge, memory and task intents. No application-specific top-level taxonomy. See `dmdo/interaction/intent.py`. |
| 4 | CapabilityRouter | Connects structured intents to existing guarded services and tools. Compound steps execute sequentially, resolving references immediately before execution. A failed or ambiguous step stops the sequence. |
| 5 | Provider/application resolution | Installed application discovery and saved aliases are separate from intent interpretation. Browser preferences choose compatible Chrome/Edge providers; media uses identified sessions and preferences. OS navigation, controlled browser interaction and generic UIA remain available without language adapters. |
| 6 | InteractionContext | Conversation-scoped state retains current/previous application, six recent application scopes, selected file and bounded candidates, browser tab, media session, project/workspace, research session, pending action and recent user turns. |
| 7 | Pronouns/references | Validated references identify existing context slots; an earlier compound file search may supply a later path. “Other file” requires exactly one alternative to an existing selection. Fabricated paths are rejected. |
| 8 | File-search root cause | Initial interpretation did not reliably separate filename, type, topic and relative time. Filtering after a result cap could miss valid dated files. Selected-document answers could skip the selected file or retrieve no text for a short pronoun query. |
| 9 | File-search fix | A shared semantic constraint schema produces filename/type, folder, topic, timestamp basis and ordering. Deterministic search applies timestamp limits before the result cap. Scoped indexed-content lookup assists filename misses. |
| 10 | Relative time | Local calendar dates become deterministic timestamp intervals. Morning ends at local noon, this week begins Monday, recent means the last seven calendar dates. Latest is ordering, not an implicit date cutoff. Download-event history is unavailable: last-modified time is a disclosed proxy when downloaded is interpreted. |
| 11 | File follow-ups | Selected file identity survives app switches and supports guarded open, selected-document retrieval, project Knowledge links, move/copy and controlled browser attachment. The live file harness intercepts external viewer launch and verifies routing; it does not claim that a PDF viewer opened. |
| 12 | Draft-correction root cause | Broad intent classification could miss short replacement fragments, confuse content with recipients, or treat a pending draft as delivery intent. A combined operation/content extraction could mistake withdrawal wording for message text. |
| 13 | PendingAction correction | Operation classification precedes literal field extraction. Corrections preserve the pending ID, provider/destination, source chat and unchanged fields; state remains unsent. Prepared native body identity is retained; replacement binds the reviewed old text and stops on an intervening user edit. Interpretation cannot emit an approval field. |
| 14 | Cancellation | Cancellation clears the unsent request. Holding retains it. Waiting while a send review is outstanding withdraws that review and retains the draft. Emergency Stop remains independent. |
| 15 | Cross-app context | Application-scoped navigation is saved/restored separately from the selected file. Explicit browser selection cannot silently reuse a tab from another provider. |
| 16 | Compounds | Ordered capability steps preserve intermediate references. Document answers inside compound plans use the existing selected-document retrieval/generation pipeline. Repeating a completed task uses its resolved entities and fresh permission checks. |
| 17 | Discord semantics | Discord is an acceptance input for generic application, hierarchy and communication intents. Destination extraction preserves app/server/channel/body separately; no Guaplings-specific rule or Discord language parser exists. |
| 18 | Discord server resolution | Fresh Guaplings selected-server evidence was observed during the corrected live test. |
| 19 | Discord channel resolution | The user corrected the live destination to #nepali-jerk-circle: #general does not exist in Guaplings. Fresh selected-server and window-title evidence verifies the corrected destination. Original #general semantic fixtures remain unchanged; there is no product-specific alias. |
| 20 | Discord live navigation | PASS for the user-corrected live channel, verified by the authorized active window title and selected server. Focus changes, missing controls or inaccessible destinations stop execution. |
| 21 | Send preview | PASS for Guaplings / #nepali-jerk-circle / hello. Qt renders destination/body and Review Send, Edit and Cancel. The generic editor transaction supports a separately reviewed Enter submission without an invokable Send button. One actual Discord hello is verified visually and by read-only UIA. The updated automatic send transaction passes the local Chromium fixture; it was not rerun against Discord after the verification fix. |
| 22 | Confirmation protection | The natural layer cannot mint permission or consequence permits. Editor submission binds the exact body/destination and requires keyboard and communication review. Optional caret placement requires mouse review and a fresh UIA hit inside the editor; overlaid buttons are rejected. A failure after submission dispatch marks the pending action uncertain and blocks another send or replacement until it is checked and cancelled. |
| 23 | Browser | The local interactive Chrome acceptance checks natural text entry, draft preparation, file lookup/attachment, reviewed fixture-only submission, download quarantine/handoff, tabs and modal handling. It never sends an external message. |
| 24 | Windows navigation | Explorer location is checked through the deterministic OS provider; Bluetooth navigation uses the natural-language front door and existing UIA verification. Navigation does not change a setting. |
| 25 | Media | Shared semantics cover search/play/pause/next/previous. Execution chooses an identified session; ambiguous providers require clarification. Named-song playback still depends on accessible search/results and observable media state. |
| 26 | Coding/research | Coding intents use selected workspace context; running existing tests differs from writing tests. Research can consume bounded selected-document evidence or start a follow-up with explicitly untrusted prior-report context. Prior report text is not new citable evidence. |
| 27 | Adapter-free application | Live acceptance uses a fixture application without a dedicated adapter, natural field entry, generic UIA selection and exact read-back, followed by owned-window cleanup. |
| 28 | Multi-app acceptance | The live local workflow finds a file, enters text in an owned adapter-free Qt app, returns to the same Chrome tab, and attaches the same file. Expanded semantic samples cover file/browser/media compounds and returning to recent applications. This does not assert universal end-to-end support for every third-party mail interface. |
| 29 | Original paraphrases | Final unchanged 37-case result is recorded in the ledger. |
| 30 | Expanded evaluation | 145 multi-domain samples are defined separately from product code. Full-run scores and remaining failures are reported without changing expectations to inflate results. |
| 31 | Compound score | The original four cases are rerun independently. |
| 32 | Latency | Every semantic evaluation records wall time and measured model calls. Representative recorded timings: launch Discord 1.473 s, play Starboy 0.998 s, find report.pdf in Downloads 5.635 s, Bluetooth settings 1.350 s. Original-suite median 1.102 s / p95 8.385 s; expanded median 1.466 s / p95 10.068 s. These are interpretation timings, not full application launch/playback latency; overlapping validation workloads can increase them. Fast requests use qwen3:8b; file constraints and draft content may require deliberate extraction. Complex hierarchy/delivery ambiguity uses gpt-oss:20b. Exclusive activation of a known recent app is classified separately from navigation/typing; a compound request stays with the general planner. Disagreement between playback and task-control interpretation also gets a bounded reasoning retry (11.5 seconds in the isolated failing-case recheck). Coding/vision models are rejected for ordinary routing. |
| 33 | Security | Regressions cover informational/untrusted content, unknown schemas, literal fidelity, denied reads/uploads, ambiguous files/destinations, cross-provider mismatch, correction confirmation and existing raw-input/consequence guards. Source-read/destination-write permission targeting for copy/move was corrected. |
| 34 | Automated total | Final full-suite total is recorded in the ledger. |
| 35 | Qt total | Final smoke total is recorded in the ledger; QtWebEngine requires normal Windows child-process access in this test environment. |
| 36 | Files added | Focused semantic helpers, provider resolution, indexed search, browser draft preparation, UIA verification, pending-draft UI, acceptance scripts, evaluation samples and regression tests. The Git change manifest below records exact paths. |
| 37 | Files modified | Orchestrator/router/context/schema, guarded provider integration, selected-document retrieval/provenance, project links, research follow-up, local Python selection, Chat developer inspector and the four requested documentation files. See the Git manifest. |
| 38 | Tests added | Deterministic tests exercise semantic constraints, timestamp ordering, selected-document isolation, scoped retrieval, project links, pending identity/hold/cancellation, browser preparation, provider mismatch, fabricated paths and compound document answering. The full suite increased from the supplied 444-test checkpoint to 514; Qt smoke increased from 46 to 49. Live/model evaluations remain opt-in. |
| 39 | Git commits | The release commit, titled DMDO 3.4.1 - Complete natural language interaction acceptance, is identified by v3.4.1; its parent checkpoint is c82195b3f3dc41166f5f5934cdb92422df1e0a56. The completion response records the resulting commit hash. |
| 40 | Remaining limitations | Precise download history and unindexed full-content discovery are unavailable. Native send requires accessible controls and fresh completion evidence. Named-contact resolution, automatic verified browser-mail submission, full prior-research evidence continuity and generated-summary transfer remain limited. Natural pause acts between steps. No required semantic fixture remains failing. Ambiguous shorthand and unsupported provider operations can still require clarification. |
| 41 | Tag | Annotated v3.4.1: DMDO 3.4.1 - Natural language interaction core. Created only after passing validation and a clean committed worktree. v3.4.0 remains unchanged at tag object 172b17beeb65743d124d29a4959b617ace1194bc. |

## Generality acceptance

| Domain | Evidence |
| --- | --- |
| A: Communication / Discord | Generic semantics, live destination and preview, one separately authorized hello verified |
| B: Browser | Live natural interaction and local-only reviewed form submission |
| C: Files | Dated temporary PDF search, selected reference, open routing and grounded summary |
| D: Windows navigation | Live Bluetooth page and Explorer location verification |
| E: Media | Expanded search/play/transport semantics and guarded session routing; no claim of live named-song playback |
| F: Coding/project | Semantic project/inspect/modify/run/test coverage and deterministic route regressions |
| G: Research | Semantic start/follow-up and selected-document route regressions |
| H: No dedicated adapter | Owned Qt fixture, natural entry, generic UIA, readback and cleanup |
| I: Compound | Original four cases and additional multi-domain ordered plans |
| J: Cross-app context | Live file / Qt app / Chrome return / attachment with same file identity |
| K: Correction | Same pending UUID and recipient, replacement body, confirmation retained |
| L: Cancellation | Pending cancellation and reviewed-send withdrawal regressions; no implicit delivery |

All domains enter the shared orchestrator and capability router. Provider execution remains independently guarded. The 145-case full run preceded the final browser-specific validation fixes; the one expanded case affected by the new multi-app activation resolver passed its independent recheck, as did the original suites and live browser flow.

## Git change manifest

Added (27):

- `DMDO_3_4_1_ACCEPTANCE.md`
- `dmdo/desktop/message_submission.py`
- `dmdo/desktop/verification.py`
- `dmdo/interaction/application_intent.py`
- `dmdo/interaction/browser_communication.py`
- `dmdo/interaction/coding_intent.py`
- `dmdo/interaction/control_intent.py`
- `dmdo/interaction/controls.py`
- `dmdo/interaction/destination_intent.py`
- `dmdo/interaction/document_intent.py`
- `dmdo/interaction/file_intent.py`
- `dmdo/interaction/indexed_files.py`
- `dmdo/interaction/native_editor.py`
- `dmdo/interaction/pending_intent.py`
- `dmdo/interaction/providers.py`
- `dmdo/interaction/reference_intent.py`
- `dmdo/ui_qt/components/pending_draft.py`
- `scripts/cross_application_acceptance.py`
- `scripts/native_editor_acceptance.py`
- `scripts/natural_language_broad_cases.py`
- `scripts/natural_language_context_acceptance.py`
- `scripts/natural_language_extended_cases.py`
- `scripts/natural_language_file_acceptance.py`
- `tests/test_interaction_completion.py`
- `tests/test_interaction_constraints.py`
- `tests/test_message_submission.py`
- `tests/test_natural_language_evaluation.py`

Modified (51):

- `ARCHITECTURE_3.md`
- `NATURAL_LANGUAGE_ARCHITECTURE.md`
- `README.md`
- `ROADMAP.md`
- `dmdo/agent/executor.py`
- `dmdo/application/chat_controller.py`
- `dmdo/application/data_controller.py`
- `dmdo/application/desktop_controller.py`
- `dmdo/application/interactive_controller.py`
- `dmdo/application/knowledge_controller.py`
- `dmdo/application/research_controller.py`
- `dmdo/application/service_container.py`
- `dmdo/desktop/gateway.py`
- `dmdo/desktop/interactive_browser.py`
- `dmdo/desktop/privacy.py`
- `dmdo/desktop/uia_provider.py`
- `dmdo/desktop/uia_worker.py`
- `dmdo/desktop/windows_input.py`
- `dmdo/desktop/workflow.py`
- `dmdo/interaction/browser.py`
- `dmdo/interaction/communication.py`
- `dmdo/interaction/communication_intent.py`
- `dmdo/interaction/context.py`
- `dmdo/interaction/documents.py`
- `dmdo/interaction/examples.py`
- `dmdo/interaction/intent.py`
- `dmdo/interaction/interpreter.py`
- `dmdo/interaction/navigation.py`
- `dmdo/interaction/orchestrator.py`
- `dmdo/interaction/router.py`
- `dmdo/services/build_test_service.py`
- `dmdo/services/chat_service.py`
- `dmdo/services/generation_pipeline.py`
- `dmdo/services/prompt_service.py`
- `dmdo/services/rag_service.py`
- `dmdo/services/run_service.py`
- `dmdo/storage/rag_store.py`
- `dmdo/tools/filesystem.py`
- `dmdo/ui_qt/windows/chat.py`
- `scripts/desktop_live_acceptance.py`
- `scripts/desktop_test_app.py`
- `scripts/interactive_browser_acceptance.py`
- `scripts/natural_language_desktop_acceptance.py`
- `scripts/natural_language_evaluation.py`
- `scripts/navigation_acceptance.py`
- `scripts/qt_desktop_smoke.py`
- `tests/test_application_controllers.py`
- `tests/test_desktop_live_boundary.py`
- `tests/test_interaction_safety.py`
- `tests/test_rag_service.py`
- `tests/test_research_integration.py`

## Authorized real-send evidence

The first two individually reviewed Enter attempts left a stale editor value and produced no observed message. Navigation away and back restored the rich editor state. The third reviewed attempt delivered one `hello`; the composer cleared. The original automatic check timed out because it inspected only 300 controls. A screenshot showed the message, and expanded read-only UIA located the receipt beyond control 580. The final read-only acceptance observed exactly one visible `hello` outside the composer and an empty composer in the corrected destination.

Verification now uses complete bounded snapshots of up to 1200 controls / depth 24 before and after approval and submission. The collector no longer silently drops siblings after 100 children. A local Chromium fixture places its new message beyond control 300 and verifies actual input events, reviewed old-draft replacement, one local submission, new message evidence and empty editor. No further Discord submission was used to validate this change. A visible UI receipt is not an official service/API delivery receipt.

The eight destination paraphrase fixtures permit an optional leading activation of the same already-known provider before navigation. This valid execution precondition previously failed an overly strict intent-list comparison. Wrong-provider activation and additional send operations are still rejected by regression tests. Original 37-case and four-compound expectations were not changed.

## Safety and reproducibility

Live scripts use isolated temporary DMDO data and local fixtures where possible. Discord acceptance denies final communication approval by default. Its explicit send opt-in is restricted to one exact hello preview in the selected Guaplings channel, following the user's separate authorization. It never retries submission on timeout. No user data migration is overwritten. No model download or paid cloud dependency was introduced. PySide6 and the single-main-window architecture are retained.

Run deterministic checks with the repository's virtual-environment Python: `-m compileall -q .`, `-m unittest discover -s tests -v`, and `scripts/qt_desktop_smoke.py`. Semantic evaluation uses `scripts/natural_language_evaluation.py --limit 37`, `--compound --limit 4`, and `--broad --limit 145`. These are developer validation commands, not syntax users must learn.
