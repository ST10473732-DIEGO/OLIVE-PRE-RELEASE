# OLIVE NOW and Chat-native Research

OLIVE NOW is the seventh public Chat preset. Existing preset mappings, including UNCENSORED, remain intact. NOW uses public retrieval and local Ollama synthesis. It is unavailable through C7 Remote AI. No automatic model acquisition or hosted inference fallback is implemented.

## Local routing

The primary model is `qwen3.5:9b`; it must be installed and the Ollama endpoint must be loopback. `qwen3.8:27b` is selected before synthesis when there are at least five sources, over 10,000 evidence characters, an explicit comparison/analysis request, or potentially conflicting numerical estimates. Numerical disagreement detection is a routing hint, not fact verification. If escalation is absent, the primary receives the same bounded evidence, with the fallback reason in internal provider metadata. Only one synthesis model is used for a request. OllamaService uses the existing ModelResidencyService lease; NOW does not preload either candidate before evidence-based selection.

Normal Chat research uses its selected local preset model. UNCENSORED continues to select its model through its existing router. Remote endpoints are refused for source-based research. Ordinary questions continue through existing Chat orchestration.

## Retrieval and freshness

NowService calls the existing broker for `web.search` and `web.open`. Research's DDGS and optional SearXNG adapters support news categories and day filtering in addition to their existing interfaces. DDGS text retains its existing Bing backend; news uses DDGS's supported automatic selection. Explicit URLs are read directly. Static extraction and configured rendered-page fallback remain in BrowserService; NOW requests fresh opens rather than cached browser reads.

At most six sources per search pass are inspected. A current search without usable evidence may make one additional pass in the other category (news or general). Known publisher/official domains influence preference only; search ranking is not proof. News/event requests require publication/update dates: today and yesterday use the local machine's calendar day; other dated current requests use a seven-day ceiling. Retrieval time never establishes event time. Unknown publication dates remain null; updates are recorded separately. Search snippets can be used when dated and clearly labelled as snippets. No qualifying evidence means a safe error, with no answer from model memory.

Current-state questions (leadership, net worth, version, listed value or status) can additionally use an undated `current_snapshot` from a page freshly opened in that request. These searches omit the search engine date filter so current leadership/profile pages can be found, while eligibility remains enforced locally. The bounded excerpt must contain explicit current/live wording or a present-tense office-holder statement. A known stale publication/update date cannot be bypassed. A search snippet cannot qualify as a snapshot. Explicit news/events or today/yesterday/this-week constraints always retain dated eligibility, even if a state term also appears.

Snapshots preserve the actual page retrieval timestamp, URL and null publication date. The inspector labels them **Current page snapshot**, **Retrieved …**, and **Publication date unavailable**. Synthesis explains that this is what the page showed when retrieved, not when it was published or independently verified. Multiple volatile estimates remain separate; synthesis is instructed to attribute each, state disagreement, and neither average estimates nor select a winner without evidence. Qualification is a conservative textual heuristic, not source authentication or a guarantee of factual support.

Evidence excerpts reuse Research's 2,400-character passage ceiling. Synthesis shares a 12,000-character excerpt budget across sources and marks shortened evidence. Input framing is checked against the existing model context policy before inference. Exact citations must reference supplied source IDs; square-bracket, grouped, bold, Unicode-bracket and table-column references are recognized. Valid table/bold references are not rejected merely for lacking square brackets. Invalid references cause the answer to be withheld; this validator checks provenance identity, not factual entailment.

The combined synthesis prompt requests three concise evidence/comparison paragraphs with `[D1]`/`[S1]` citations and lists the actual allowed IDs; ordinary document-only, web-only and NOW prompts retain their existing instructions. Compatibility parsing also recognizes bold table labels such as `**D1 – Report.pdf, page 2**`, parentheses containing only source IDs/separators such as `(D1, S1)`, explicit ID-only bullets labelled `PDF excerpts:` or `Online source:`, and labelled `- *Source:* D1 – …` bullets observed in live synthesis. Publisher names, ordinary prose such as “Amazon S3”, and timestamps do not become citations. Unknown IDs are detected before membership validation and remain rejected even alongside valid citations.

Combined document/web synthesis requires at least one valid D citation and one valid S citation when both evidence groups are supplied. Naming both publishers or citing only one side cannot pass. An answer may explicitly state that the reviewed excerpts are insufficient or irrelevant, citing both groups to identify what was reviewed without claiming corroboration. Missing retrieval evidence still follows the existing truthful missing-evidence/error paths. Group coverage is a conservative syntax check, not proof that a comparison is factually supported. Validation errors carry a safe internal reason; raw answer/evidence logging is not enabled in production.

Combined synthesis can use spare context for output up to the existing 4,096-token ceiling: live comparisons on the installed model sometimes exhausted the former 2,048-token allowance before emitting visible text. Original input-fit checks and evidence bounds still apply. This does not change ordinary document/web/NOW budgets, models, or the one-inference-per-request behavior.

## Weather

`web.weather` is a narrow registered tool requiring `network.read`. It calls Open-Meteo geocoding and forecast APIs over Research's DNS-pinned public HTTP transport. No API key, Google scraping, model download or LLM-generated weather measurement is involved.

Weather supports current conditions, today, tomorrow and yesterday. Yesterday uses archived forecast data, not a station-observation claim. Results include requested/resolved place, coordinates, timezone, units, conditions, forecast timestamps, retrieval timestamp and provider URLs. The first geocoding match is explicitly disclosed. Current measurements more than two hours from retrieval and mismatched requested forecast days are rejected. Ambiguous locations and broader forecast periods remain limitations.

Provider documentation: [forecast API](https://open-meteo.com/en/docs), [geocoding API](https://open-meteo.com/en/docs/geocoding-api).

## Chat-native Research

The Research feature is removed from the navigation/launcher/palette registry. Its legacy navigation target resolves to Chat. The redundant Research mode selector is removed: natural-language intent and the public preset are the normal entry points. Explicit legacy depth arguments remain supported by backend contracts. The existing Research component remains available in Chat's **Saved research & evidence** sheet. Existing sessions, reports, evidence, sources and project associations are preserved with no migration or deletion.

The app initializes its active route as Home; it does not restore an active route or handle URL routes. Remembered space views are the existing persisted navigation setting: a legacy Research value opens Chat through the space navigation path. Route values are also normalized before rendering, protecting direct state initialization without introducing a migration. An Electron regression test seeds the old remembered value, reloads the app and checks that the Chat composer appears.

Cheap explicit-intent recognition handles research, investigation, verification, multiple-source comparison and attached-document questions. The existing semantic interpreter remains a fallback for other research phrasings. Explicit full-report requests retain the existing report workflow. Routine Chat research creates assistant messages and broker audit records, without creating permanent Research sessions/reports.

Attachment intent requires an explicit document reference (PDF, document, report, attachment, chapter, file or findings), or reference-like follow-up wording backed by an earlier assistant message marked `research_kind=documents/combined`. Generic pronouns, cost, evidence and recommendation alone do not activate document research. Ordinary intervening turns preserve that context, while unrelated questions such as “What is this error?” and “What does it cost to run an RTX 4090?” remain ordinary Chat.

Document-only requests use existing extraction/indexing/RAG. Relevant chunks and bounded opening excerpts for overview/comparison questions are synthesized locally. At most four document excerpts are used; combined requests add at most four public sources. Document coverage and missing text pages are supplied to synthesis. Missing document evidence produces an explicit limitation rather than a model-memory replacement. Reviewed document attachments stay available for follow-ups, including after ordinary intervening turns. Changing presets does not remove attachments.

NOW itself remains public-question-only in this milestone and refuses image/document attachments. Use NORMAL, DEEP or another local text preset for document and combined research. DEEP's existing independent image/OCR path remains available; the new document research path requires indexed text and does not claim full-PDF or exhaustive chapter coverage.

## Privacy and trust

No memories, notes, custom system prompt, clipboard, selected workspace, local files or model-generated assistant history are appended to public queries. NOW follow-ups can reuse only a prior NOW public question. Document follow-ups use bounded prior user-question context locally.

A document-only request never searches the web. Explicit current/online comparison permits external research, but only short user-supplied public topic wording or up to three recognized public concepts are sent. Derived terms come from a fixed public-topic vocabulary, not arbitrary private identifiers. Unknown topics prompt for public search terms. Raw chunks, filenames and the file itself are never submitted to search providers by this path. This conservative vocabulary limits automatic comparisons for specialized/private topics.

Source data has no action authority. Synthesis has no tools and is not returned to a planner. All public reads remain broker-mediated, with persistent Deny authoritative. The weather tool is classified in the authority inventory without a generic Owner grant. No shell, messaging, settings or filesystem capability is added to research output.

## Provenance and errors

Assistant `sources` retain `id`, `label`, `source`, `title`, `url` where applicable, `published_at`, `updated_at` where known, `retrieved_at`, `provider`, `evidence`, `kind` and trust labels. Document sources retain document ID/name, page, chunk, extraction origin and RAG metadata. Weather adds its structured provider payload. Public and document evidence are grouped separately in source chips; inspection shows evidence, timestamps and an original-source link. Exact model/provider/tier/reason remain diagnostic message metadata, not normal Chat labels.

Errors distinguish missing primary model, nonlocal inference endpoint, remote NOW, search/weather unavailability, missing fresh evidence, failed page retrieval, unsupported weather location/period, private NOW attachments and invalid synthesis citations. No raw provider exception or stack trace is surfaced in normal UI.

## Validation and live limitations

Deterministic tests mock network/inference by default and exercise real broker, Chat persistence, model adapter, residency and local indexing. `scripts/now_live_smoke.py --live [--synthesize]` and Electron tests gated by `OLIVE_LIVE_AI=1` are opt-in and use isolated profiles. `scripts/create_chat_research_fixture.py` creates a synthetic PDF for acceptance.

Free search availability, timestamp coverage and publisher blocking vary. A dated current source can still quote older numbers; synthesis is instructed to preserve dates/disagreement and state insufficiency, but provenance validation cannot guarantee factual correctness. Long research remains bounded, and an explicit report request uses the fuller existing Research workflow. Answers are buffered until source-ID validation passes, so progress is visible but unvalidated tokens are not streamed into Chat.
