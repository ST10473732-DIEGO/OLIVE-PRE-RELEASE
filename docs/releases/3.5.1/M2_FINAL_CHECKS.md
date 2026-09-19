# M2 final functional checks — 11 September 2026

Baseline: clean `development/3.5.1-electron-experience` at `cab8b76cdbe5083a18d10513ae6791f9705b6d95`. The user accepted the close-out visual corrections, including pause presentation, Knowledge outcomes, direct Studio tools, settled Projects and retained output. This accepts their design, not full M2 functional sign-off or the release. No new Personal Core interfaces, tag, Qt removal or default-launcher change.

| Acceptance item | Current evidence and status |
|---|---|
| Visual corrections | Accepted by the user at the baseline above; unchanged in this task. |
| Agent live local | Actual temporary-workspace natural-language validation evidence supplied in the preceding package; not rerun as a new live pass here. |
| Research public integration | Previous Electron request actually read the public page and persisted evidence/citation/result. That integration evidence remains valid independently of answer quality. |
| Research answer quality | Original third finding overgeneralised helper behaviour. General extraction/selection/synthesis corrections and separate recorded-source model check below; no universal factual-accuracy claim. |
| Ordinary Electron suite | Fresh complete final-code run recorded in the review package, separately from opt-in checks. |
| Desktop live through Electron | Pending explicit user initiation. Target script compiles and isolated-profile launch configuration is verified; target not launched, UIA controls not inspected, no input performed. |

## Research defect and correction

The original request, plan, source metadata, four excerpts, findings and generated report are preserved in `tests/fixtures/research_scope_original.json`, with original-artifact SHA-256 and public-documentation attribution. The original ignored acceptance artifact is unchanged. New generations have separate artifacts; they do not overwrite the old recorded answer.

Old third finding: “The equality check is type-sensitive: type-specific methods can be registered to enforce that objects of exactly the same type compare equal, and mismatched types can trigger an error.” Typography here is normalised; the fixture retains the original bytes/text values.

The defect was not solely synthesis. HTML extraction omitted definition signatures (`dt`), leaving paragraphs without API ownership. Ranking four isolated paragraphs against planner subquestions omitted the main definition and its neighbouring conditional dispatch explanation. The old selected offsets were 38710, 38979, 39924 and 40602: generic dispatch, registration helper, string helper, and list/tuple helper respectively. The main operation definition at offset 27530 was absent. Helper-specific restrictions could consequently be attributed to the parent operation.

Changes:

- Extraction retains definition signatures and bounded section ownership with exact source offsets. Selection prioritises the requested definition and keeps neighbouring conditions together, without crossing into another API to fill an excerpt. New selected evidence contains the main definition, general dispatch, registration helper and string helper with explicit owners.
- Synthesis sees ownership and truncation, must retain each finding's conditions, and has no quota requiring tangential findings. No operation name or exact user phrase is hard-coded.
- A separate bounded review using the existing research-synthesis model checks proposed paraphrases against their cited excerpts. Wrong-subject, lost-condition and insufficient-support assessments withhold the conclusion and retain the proposal/reason in session context. Invalid/unavailable review also withholds paraphrases. Cancellation propagates. Full untruncated quotations remain quotations, not independent verification.
- Source-ID/quote identity checks establish provenance only. Token overlap ranks relevance or rejects unrelated material; it is not positive evidence of factual support.

`tests/test_research_scope.py` covers two structural cases: a decoder's ASCII-only helper versus the general decoder, and a list-comparison helper versus general value comparison. Extraction/offset tests are deterministic; scope-assessment responses in these tests are explicitly mocked. The test showing a false claim can pass provenance validation is intentional.

The separate model-backed check (`scripts/check_m2_research_scope.py`) read one bounded public [Python documentation page](https://docs.python.org/3/library/unittest.html), then reused its recorded HTML for small follow-up checks. No crawl, new model or role change. Existing `gpt-oss:20b` generated and reviewed a new persisted session in an isolated profile. The final synthesis/review took 15.44 seconds, not a frontend first-output measurement. The final old-claim review returned **insufficient**, specifically noting that the cited excerpts do not establish an error for mismatched types.

The new answer states that the arguments compare equal or the test fails, then explicitly limits specialised dispatch to arguments of the exact same type and the listed/registered types. Its string-diff finding refers to the string helper. The exact generated Markdown, selected evidence, proposals and review assessments are included in the package. An earlier review failed closed as unavailable/invalid; an intermediate answer still overbroadened helper dispatch. Those intermediate records are retained in the ignored artifact directory. They prompted the standalone-condition/no-quota instructions; they are not relabelled as successes.

Remaining uncertainty: section detection and selection are heuristic, bounded excerpts may omit later conditions, and old cached text without section metadata falls back to paragraph selection. The same-model review can miss or overreject a claim; its supported verdict is not factual certification. The extra bounded model call adds latency (maximum 45 seconds before withholding). This does not eliminate hallucinations. No stored old report is silently rewritten; metadata additions use existing version-compatible dictionaries, with no destructive data migration.

## Validation and remaining gate

See the package's `REVIEW.md` and logs for final fresh counts. Python scope tests include mocked inference; ordinary Electron tests use isolated profiles and retain real file-content, backend-validation, selected-output, visible-output and editor-retention assertions. Security regressions are part of these suites, not an independent full security audit.

The two ordinary Electron opt-in skips are live Chat inference (`DMDO_LIVE_AI=1`) and live Agent/public Research (`DMDO_M2_LIVE=1`). These would deliberately invoke models/network; their previous evidence and this separate Research model check must not be counted as fresh passes of skipped tests.

Desktop approval was requested specifically for launching one new acceptance target and inspecting only its process/title/accessible controls through Electron, with Stop available. No reply means no launch or interaction. Tkinter import/compilation does not establish UIA compatibility. `DESKTOP-MANUAL-CHECK.md` in the package gives the isolated launch, identity/permissions/Stop checks, and separately approved optional input steps. If controls cannot be resolved, stop and report that limitation; no coordinates or alternate application fallback.

All 125 original M2 action mappings remain intact. Read-only Output is not a PTY; no connected LSP/debugger is claimed. Qt fallback style warnings, clean-machine packaging, unmeasured GPU/combined-model performance and broader provider compatibility remain release limitations. Dependencies/model assignments are unchanged. Native Identity, Contacts, Calendar, Personal Tasks and in-app Reminders follow only after M2 acceptance; Mail/optional SMTP/IMAP follow later, without a Google dependency.
