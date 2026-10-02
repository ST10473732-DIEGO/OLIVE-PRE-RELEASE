# OLIVE 3.3 Research architecture

> **Status (OLIVE 1.0, 2026-10-02).** This is the 3.3 research architecture: evidence
> identities, quarantine and approval-gated Knowledge still apply. Chat's live research
> is now OLIVE NOW ([research](../features/research.md)); the browser provider
> (Playwright) is optional and HTTP research works without it.

## Baseline audit

Development starts from annotated `v3.2.5`, commit `364cf8f`, with a clean worktree. Compileall, all 184 existing tests and all 27 existing visible Qt smoke checks passed before implementation. Smoke data was isolated from personal OLIVE data. No high-confidence baseline defect required a separate audit-fix commit.

The service container, queued Qt runtime, feature registry, KnowledgeSource, LearningService, model router, ToolRegistry, permissions, indexing scheduler and existing research-provider contracts were inspected. The prior research implementation contained contracts, not network browsing. Existing 3.2.5 services and the Qt framework remain the baseline.

## Boundaries

Research is a separate persistent task/evidence workflow, not a Chat mode rewrite. Session state and transient page cache are separate from approved Knowledge. Active interrupted sessions recover paused; restart never initiates searches or page loads. Permanent learning requires an explicit user decision.

Page observations, planner output and evidence are data. They cannot add tools, authorize actions, change policies or invoke the terminal. The planner returns a strict bounded schema with no executable actions. Network tools will remain behind the established deterministic tool/permission/confirmation boundary. Qt updates continue through the existing queued bridge.

## Provider choice

The initial free search route uses the maintained DDGS adapter with its Bing backend. It is a compatibility route to a consumer search service and can be rate-limited or blocked; OLIVE does not solve CAPTCHAs or bypass restrictions. The initial DuckDuckGo route proved intermittent during live testing; Bing returned official documentation in the final smoke. An optional SearXNG JSON adapter provides a replaceable structured route. No paid search API is required. [DDGS provider interface](https://github.com/deedy5/ddgs), [SearXNG search API](https://docs.searxng.org/dev/search_api.html).

Static HTML reading handles ordinary documentation efficiently. Playwright supplies rendered DOM observations when needed, independently of Qt presentation. Each rendered read creates a fresh nonpersistent browser context; no normal browser profile or storage state is imported. Installed Edge may be used as the executable; otherwise missing Chromium produces manual setup guidance. Python dependency installation does not install browser binaries or models. [Playwright contexts](https://playwright.dev/python/docs/browser-contexts), [browser installation/channels](https://playwright.dev/python/docs/browsers).

Public HTTP reads validate destinations, pin the resolved public address, retain normal TLS hostname verification and revalidate every redirect. Rendered browsing uses an ephemeral public-only egress proxy so DNS changes cannot silently redirect a browser request to a private address. File, credential-bearing, intranet and onion URLs are rejected. Page downloads, non-read requests, service workers and unnecessary media are blocked. A fixed DOM extraction expression is internal implementation, never an arbitrary JavaScript tool.

## Storage and limits

ResearchSession records contain plans, query attempts, source metadata, bounded evidence references, state, settings, timestamps and reports. Page bodies are not duplicated into each evidence item. Cache size, source/page/query counts, depth, concurrency and runtime have hard limits. URL normalization removes fragments and common trackers while preserving potentially meaningful slash/query differences. Canonical tags remain untrusted metadata rather than unconditional identity overrides.

Source material is not a verified fact. Content hashes identify duplicates so mirrors cannot manufacture corroboration. Source dates and retrieval timestamps are separate. Subscription records default to disabled/manual. Tor and authenticated-provider contracts confer no connectivity, personal cookies, passwords or host authority.

## Lifecycle and UI

ResearchController owns one active session at a time, independently of Chat, Agent and Studio. Planning, search, reading, evaluation and synthesis persist at operation boundaries. Pause occurs between operations; cancel interrupts awaited work and prevents further operations. The total elapsed budget survives retries. Ollama failure retains sources/evidence, and interrupted active sessions recover paused. Explicit user URLs are read as bounded seeds; explicit `site:` constraints are retained deterministically.

ResearchWindow is a lazy singleton with history, plan, findings and source/evidence tabs. Citations navigate to read-only source details. Native dialogs expose reviewed website scopes and distinct download/read/save/import actions. Settings and Diagnostics share the existing controllers. Studio hands off only a bounded question, file/selection/error and project identifier; the user starts the investigation. `research.run` gives Agent normalized untrusted findings without filesystem or terminal authority.

## Evidence and Knowledge

Evidence stores bounded quotations and offsets into a hashed source version, not repeated whole pages. Citation validation rejects missing/unread sources, mismatched versions, duplicate evidence IDs, model-supplied URLs, false direct quotations and lexically unsupported findings. Short prompt citation labels map deterministically back to persisted evidence IDs. Markdown escapes source-provided text; source inspection runs no page scripts.

Conflict detection flags possible disagreement for synthesis; it is not a general fact checker. Lexical support checks cannot prove semantic entailment. Publication dates are source claims and unknown dates remain unknown. Duplicates are not counted as independent evidence. No political or popularity-based credibility score is assigned.

Approved pages flow through LearningService, KnowledgeSourceRepository and existing RAG chunk/embedding services. Web namespaces separate global/project retrieval. Unchanged hashes skip embeddings; changed versions retain prior metadata. Interrupted indexing is marked requires_reindex. Collections are metadata, and subscription records stay disabled/manual. Local Knowledge, project description and memories are bounded untrusted context, not instructions. Current requests skip stale cached web Knowledge.

Additive storage files are `research_sessions.json`, `research_reports.json`, `web_knowledge.json` and `web_subscriptions.json`, plus existing `knowledge_sources.json` and `rag.sqlite3`. Backups include approved content and session state; temporary cache and quarantined file bytes are excluded. Existing data formats are not deleted or rewritten.

## Limitations to retain in release review

Free consumer search can be blocked, empty or poorly ranked; there is no access bypass. SearXNG currently requires a public HTTP(S) endpoint. Rendered pages receive a short bounded settle interval, so complex interactive sites may remain unreadable. Browser screenshots are not yet exposed. Authenticated sessions and Tor remain contracts only. Subscription scheduling is not active. Research quality depends on the installed local model; large CPU-bound models may reach time limits. Clean-machine packaging remains unverified.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](legacy-dmdo-compatibility.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
