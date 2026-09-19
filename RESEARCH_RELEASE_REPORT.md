# DMDO 3.3.0 release validation

DMDO 3.3 adds a dedicated Research workflow to the existing Qt desktop. It preserves the 3.2.5 service architecture and existing data. This report records tested behavior and limits; it does not certify every website, model or clean Windows installation.

## Requested completion report

| Item | Result |
|---|---|
| 1. Pre-3.3 audit | Clean baseline at annotated v3.2.5 / 364cf8f; full compilation, 184 tests and 27 visible desktop checks passed before changes. No separate baseline defect fix was needed. |
| 2. Architecture | Added UI-neutral ResearchController, bounded ResearchOrchestrator and normalized providers to the single shared container. Qt remains the desktop framework. |
| 3. Lifecycle | Persistent created/planning/searching/reading/evaluating/synthesizing/paused/completed/failed/cancelled states. Interrupted active sessions recover paused; no automatic network restart. |
| 4. Qt workspace | Home card, singleton Research window, history, question/project/depth, plan, findings, sources/evidence, pause/resume/cancel, save actions and downloads. |
| 5. Search | DDGS with free Bing backend; optional public SearXNG JSON endpoint. Normalized, bounded results; visible failures and no challenge bypass. |
| 6. Browser | Static public HTTP first; Playwright-rendered DOM fallback through the provider abstraction. No arbitrary JavaScript tool. |
| 7. Isolation | Fresh nonpersistent contexts, no normal browser cookies/profile, filtered browser environment, sandbox enabled, public-only egress proxy, private/file/onion destinations rejected. |
| 8. Planner | Installed Ollama model, strict JSON schema, bounded retry, explicit user site constraints and URL seeds preserved deterministically. |
| 9. Routing | Research planning/synthesis map to reasoning, selection to fast, extraction to general. Parsing/hashing/ranking use deterministic code. No models downloaded. |
| 10. Sources | URL, canonical metadata, domain, dates, author, retrieval time, content hash, project/session/collection and trust provenance. |
| 11. Evidence | Bounded quote and source offsets, subquestion, score, timestamp and source-version hash; no repeated whole page per evidence item. |
| 12. Citations | Read-source/evidence validation, short prompt labels mapped to real IDs, no invented replacement targets, bounded correction. Exact quotations are classified deterministically. |
| 13. Conflict/freshness | Possible disagreement retained, current requests bypass stale web cache, future dates get no recency bonus, duplicate hashes do not add independent evidence. Semantic truth is not guaranteed by lexical validation. |
| 14. Website ingestion | Explicitly reviewed single/selected/subsection/sitemap scope, maximum 30 URLs. Existing chunking and embedding architecture reused. |
| 15. Persistent Knowledge | Approved web bodies and provenance plus existing RAG SQLite namespaces, global/project collections, restart retrieval verified. |
| 16. Change detection | Unchanged hashes skip embeddings; changed metadata history retained; interrupted indexing requires re-index; manual refresh/remove supported. |
| 17. Projects | Research project association, saved full reports or selected findings, project report and Web Knowledge tabs. |
| 18. Studio | Research toolbar handoff of bounded question/file/selection/error and project. Research requires an explicit start and returns no host authority. |
| 19. Agent | Registered research.run subtask returns summary/sources/evidence as untrusted data; network permissions remain authoritative. |
| 20. Performance | Hard page/search/depth/concurrency/runtime bounds, elapsed budget survives retries, bounded cache/output and lazy browser/window creation. Visible smoke startup approximately 474 ms. |
| 21. Injection defenses | Hostile-page fixtures cannot change policies or register tools. No webpage can approve confirmations, run terminal commands or gain trust. Markdown/source viewers block active content. |
| 22. Downloads | Bounded quarantine with URL/type/size/hash/time/state; explicit read, exclusive file save and approved Knowledge import. No execution action. |
| 23–24. Files | Full added/modified file manifest below. No source deletion or legacy-data removal. |
| 25. Dependencies | BeautifulSoup 4.15.0, DDGS 9.16.0 and Playwright 1.62.0 tested, bounded dependency ranges declared. pip check passes. No browser or model binary downloaded. |
| 26. Storage | Additive schema-1 Research session/report/web-body/subscription JSON, optional KnowledgeSource web fields and existing RAG DB. Backups include approved Research data; transient cache/quarantine bytes excluded. |
| 27. Tests | 74 additional tests beyond the 184 baseline, plus extended Qt thread/topic coverage and desktop smoke assertions. Ordinary runs are offline. |
| 28. Automated result | Full compileall and 258 unittest tests passed, including offscreen Qt tests. Expected negative-fixture logs are not runtime failures. |
| 29. Qt smoke | 30 distinct visible desktop checks passed, including Research construction, evidence inspection, singleton state, existing editing/Run/Stop/Restart/tests/preview, tray and shutdown. |
| 30. Live Research | Final Bing/DDGS query returned five normalized results; two official-page observations, four evidence items, validated cited Ollama report completed. Earlier DuckDuckGo empty results and invalid model labels were exposed and addressed, not hidden. |
| 31. Website learning | Official Ollama embeddings page fetched, chunked, embedded with installed qwen3-embedding:0.6b, saved/retrieved and reinitialized successfully. Hash 8c5a9763859430057eaeee7f8938dd677fca581d05961099538de31474ebd117. All integration data was temporary and removed afterward. |
| 32. Packaging | Windows source environment verified; Qt/WebEngine and Playwright driver/browser collection documented. Clean-machine executable/installer certification remains future work. |
| 33. Git | Logical commits on development/3.3-research; v3.2.5 preserved, no history rewrite. Commit list below. |
| 34. Manual checklist | Covered by visible deterministic smoke and bounded live probes below. Broader subjective evidence-quality review and clean-machine acceptance remain outstanding. |
| 35. Limits | Consumer search can fail or rate-limit; complex interactive sites may not render fully. One active Research session per runtime. Browser screenshots, authenticated browsing and active subscriptions are deferred. Citation validity does not prove every paraphrase true. |
| 36. 3.4 recommendation | Prioritize packaging, research-quality/model-performance evaluation and browser isolation/resource testing, then explicitly opt-in scheduled source refresh. Keep unrelated communications/control capabilities in separately scoped releases. |

## Desktop and live checklist

- Home and all ten feature windows open and share the bridge.
- Existing Chat streaming/stop, Agent persistence, Studio edit/save, Run/Stop/Restart, Problems, Tests, Git and local WebEngine preview pass.
- Research sources display inert evidence; closing/reopening retains state.
- Queued Research updates reach the GUI thread; backend tests remain headless.
- Actual HTTP and isolated Edge DOM reads returned the official embeddings page with matching hashes.
- Final live search, official-page reading, evidence extraction, local synthesis and citation mapping completed.
- Approved website learning, embeddings, retrieval and repository restart preserved source provenance.
- Temporary smoke Knowledge/workspaces were removed; personal DMDO data was not used for integration writes.
- No Tor, email, calendar, trading, voice, unrestricted desktop control, Flet or automatic permanent learning was added.

## Validation limits

The visible suite uses deterministic Chat output; separate Research validation uses the installed local model. It is automated desktop smoke, not a claim of exhaustive human usability testing. Semantic support and disagreement detection are conservative heuristics, not a formal entailment engine. Local model output can overgeneralize source material despite valid citations. The final live report is evidence of functional integration, not a general research-quality benchmark.

The default browser profile is isolated but the Python backend is not itself a separate OS sandbox. Public website availability, consumer search changes and the installed model's speed remain external dependencies. Automatic subscriptions, authenticated sources and Tor connectivity remain disabled/unimplemented by design.

## Commits

- 244f581 — DMDO 3.3 research core and audited baseline
- a98de60 — DMDO 3.3 web search and isolated browser providers
- 54fda4e — DMDO 3.3 evidence citations and bounded orchestration
- 93e631f — DMDO 3.3 approved web Knowledge and download quarantine
- e5bca48 — DMDO 3.3 shared research services and permission boundaries
- 7e27e7d — DMDO 3.3 Qt Research workspace and desktop integration
- f952053 — DMDO 3.3 research reliability and live validation
- The final commit, DMDO 3.3 release documentation and version, records this report and version 3.3.0.

Full compilation and all 258 tests were rerun after the final reliability changes and passed. Changed-file scans found no legacy UI imports, credential-shaped values, private keys or absolute personal Windows paths in 57 release files. These are targeted scans, not a claim of exhaustive secret detection. Git whitespace validation and pip dependency checks passed.

## File manifest

The manifest is relative to v3.2.5 and is generated before the final documentation commit.

<!-- generated manifest -->

| Change | File |
|---|---|
| Modified | `ARCHITECTURE_3.md` |
| Modified | `DEPLOYMENT_DESIGN.md` |
| Modified | `PACKAGING_WINDOWS.md` |
| Modified | `README.md` |
| Added | `RESEARCH_ARCHITECTURE.md` |
| Added | `RESEARCH_RELEASE_REPORT.md` |
| Modified | `ROADMAP.md` |
| Modified | `dmdo/agent/executor.py` |
| Modified | `dmdo/agent/model_router.py` |
| Modified | `dmdo/agent/permission_service.py` |
| Modified | `dmdo/application/data_controller.py` |
| Added | `dmdo/application/research_controller.py` |
| Added | `dmdo/application/research_data.py` |
| Modified | `dmdo/application/service_container.py` |
| Modified | `dmdo/config.py` |
| Modified | `dmdo/knowledge/source.py` |
| Added | `dmdo/research/__init__.py` |
| Added | `dmdo/research/browser.py` |
| Added | `dmdo/research/browser_proxy.py` |
| Added | `dmdo/research/cache.py` |
| Added | `dmdo/research/citations.py` |
| Added | `dmdo/research/evidence.py` |
| Added | `dmdo/research/extraction.py` |
| Added | `dmdo/research/http.py` |
| Added | `dmdo/research/models.py` |
| Added | `dmdo/research/orchestrator.py` |
| Added | `dmdo/research/planner.py` |
| Added | `dmdo/research/providers.py` |
| Added | `dmdo/research/quarantine.py` |
| Added | `dmdo/research/repository.py` |
| Added | `dmdo/research/search.py` |
| Added | `dmdo/research/settings.py` |
| Added | `dmdo/research/tools.py` |
| Added | `dmdo/research/urls.py` |
| Added | `dmdo/research/web_knowledge.py` |
| Modified | `dmdo/services/backup_service.py` |
| Modified | `dmdo/ui_qt/dialogs/projects.py` |
| Added | `dmdo/ui_qt/dialogs/research_downloads.py` |
| Added | `dmdo/ui_qt/dialogs/web_knowledge.py` |
| Modified | `dmdo/ui_qt/feature_registry.py` |
| Modified | `dmdo/ui_qt/studio/actions.py` |
| Modified | `dmdo/ui_qt/studio/window.py` |
| Modified | `dmdo/ui_qt/window_manager.py` |
| Modified | `dmdo/ui_qt/windows/chat.py` |
| Modified | `dmdo/ui_qt/windows/data.py` |
| Added | `dmdo/ui_qt/windows/research.py` |
| Modified | `dmdo/ui_qt/windows/settings.py` |
| Modified | `pyproject.toml` |
| Modified | `requirements.txt` |
| Modified | `scripts/qt_desktop_smoke.py` |
| Added | `scripts/research_live_smoke.py` |
| Modified | `tests/test_qt_ui.py` |
| Added | `tests/test_research_core.py` |
| Added | `tests/test_research_evidence.py` |
| Added | `tests/test_research_integration.py` |
| Added | `tests/test_research_providers.py` |
| Added | `tests/test_web_knowledge.py` |
