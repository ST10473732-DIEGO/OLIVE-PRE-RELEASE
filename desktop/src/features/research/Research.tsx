import type { RecordTarget } from "../../services/handoff";
import { useEffect, useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { WorkspacePage, Details } from "../../components/WorkspacePage";
import { GrowingComposer } from "../../components/GrowingComposer";
import { Markdown } from "../../components/Markdown";
import { Sheet } from "../../components/Sheet";
import type { ResearchSummary, ResearchSession, ResearchSource } from "./types";
import { WebLibrary } from "./WebLibrary";

export default function Research({
  target,
  chatId,
  report,
}: {
  target?: RecordTarget;
  chatId: string;
  report: (e: unknown) => void;
}) {
  const [search, setSearch] = useState("");
  const [historyPage, setHistoryPage] = useState(0);
  const resource = useResource(async () => {
    const [history, current, projects, preferences] = await Promise.all([
      call<ResearchSummary[]>("research.history", {query:search,offset:historyPage*100}),
      call<{ session: ResearchSession | null; active: boolean }>(
        "research.current",
        {},
      ),
      call<{ id: string; title: string }[]>("data.projects", {}),
      call<{ depth: string }>("research.preferences", {}),
    ]);
    return { history, current, projects, preferences };
  }, ["research", "projects"], `${historyPage}:${search}`);
  const [question, setQuestion] = useState(() => {
    try { return sessionStorage.getItem(`olive.research.draft:${chatId}`) || ""; }
    catch { return ""; }
  });
  useEffect(() => {
    try { sessionStorage.setItem(`olive.research.draft:${chatId}`, question); }
    catch { /* A full browser store must not discard the current in-memory draft. */ }
  }, [chatId, question]);
  const [depth, setDepth] = useState("");
  const [project, setProject] = useState("");
  const [selectedId, setSelectedId] = useState("");
  useEffect(() => {
    if (target) {
      setSelectedId(target.id);
      setSourceIds([]);
      setFindingIds([]);
    }
  }, [target]);
  const [selectedSource, setSelectedSource] = useState<ResearchSource>();
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("Findings");
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [findingIds, setFindingIds] = useState<number[]>([]);
  const id =
    selectedId === "new"
      ? ""
      : selectedId ||
        resource.data?.current.session?.id ||
        resource.data?.history[0]?.id ||
        "";
  const detail = useResource(
    () =>
      id
        ? call<ResearchSession>("research.get", { session_id: id })
        : Promise.resolve(undefined),
    ["research"],
    id,
  );
  const session =
    resource.data?.current.session?.id === id
      ? resource.data.current.session
      : detail.data?.id === id
        ? detail.data
        : undefined;
  const active = Boolean(resource.data?.current.active || running);
  const operation = async (fn: () => Promise<unknown>, message: string) => {
    try {
      await fn();
      setNotice(message);
      await resource.refresh();
      await detail.refresh();
    } catch (e) {
      report(e);
    }
  };
  const start = async () => {
    if (active || !question.trim()) return;
    setRunning(true);
    setSelectedId("");
    setSourceIds([]);
    setFindingIds([]);
    setNotice("Starting research…");
    try {
      await call("interaction.research", {
        chat_id: chatId,
        question,
        depth: (depth || resource.data?.preferences.depth || "Standard") as
          "Quick" | "Standard" | "Deep",
        ...(project ? { project_id: project } : {}),
      });
      await resource.refresh();
    } catch (e) {
      report(e);
    } finally {
      setRunning(false);
      setNotice("");
    }
  };
  const inspectLink = (url: string) => {
    const source = session?.sources.find(
      (s) => s.url === url || encodeURI(s.url) === url,
    );
    if (source) setSelectedSource(source);
    else void window.olive.openExternal(url).catch(report);
  };
  return (
    <WorkspacePage
      title="Research"
      description="Investigate a question and follow the evidence."
    >
      <div className="objective-surface">
        <GrowingComposer
          aria-label="Research question"
          placeholder="What would you like to investigate?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <div className="row">
          <select
            aria-label="Research depth"
            value={depth || resource.data?.preferences.depth || "Standard"}
            onChange={(e) => setDepth(e.target.value)}
            disabled={active}
          >
            {["Quick", "Standard", "Deep"].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
          <select
            aria-label="Research project"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            disabled={active}
          >
            <option value="">Global research</option>
            {resource.data?.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
          <button
            className="primary"
            disabled={active || !question.trim()}
            onClick={() => void start()}
          >
            Start research
          </button>
          <button
            disabled={active}
            onClick={() => {
              setQuestion("");
              setSelectedId("new");
              setSourceIds([]);
              setFindingIds([]);
            }}
          >
            New investigation
          </button>
          {active && (
            <>
              <button
                onClick={() =>
                  void operation(
                    () => call("research.pause", {}),
                    "Pause requested; the current operation may finish first.",
                  )
                }
              >
                Pause research
              </button>
              <button
                onClick={() =>
                  void operation(
                    () => call("research.cancel", {}),
                    "Research cancellation requested.",
                  )
                }
              >
                Cancel research
              </button>
            </>
          )}
        </div>
      </div>
      <p role="status">{notice}</p>
      {resource.error && <p role="alert">{resource.error}</p>}
      {detail.error && (
        <p role="alert">
          {detail.error}
          <button onClick={() => void detail.refresh()}>
            Retry investigation
          </button>
        </p>
      )}
      <div className="project-layout">
        <aside>
          <h2>Investigations</h2>
          <label className="search">
            <input
              aria-label="Search investigations"
              placeholder="Find a question…"
              value={search}
              onChange={(e) => {setSearch(e.target.value);setHistoryPage(0);}}
            />
          </label>
          <div className="record-list">
            {resource.data?.history
              .filter((s) =>
                s.question.toLowerCase().includes(search.toLowerCase()),
              )
              .map((s) => (
                <button
                  key={s.id}
                  className={`record-card project-card ${id === s.id ? "selected" : ""}`}
                  onClick={() => {
                    setSelectedId(s.id);
                    setSourceIds([]);
                    setFindingIds([]);
                  }}
                >
                  <strong>{s.question}</strong>
                  <span className="muted">
                    {s.status} · {s.updated_at}
                  </span>
                </button>
              ))}
          </div>
          {(historyPage>0 || resource.data?.history.length===100) && <div className="row">
            <button disabled={!historyPage || resource.loading} onClick={()=>setHistoryPage(value=>value-1)}>Previous history</button>
            <span>Page {historyPage+1}</span>
            <button disabled={resource.loading || (resource.data?.history.length||0)<100} onClick={()=>setHistoryPage(value=>value+1)}>Older history</button>
          </div>}
          {resource.data?.history.length === 0 && (
            <p className="muted">{search || historyPage ? "No matching investigations on this page." : "No investigations yet."}</p>
          )}
        </aside>
        <section>
          {session ? (
            <>
              <div className="row">
                <h2>{session.final_report ? "Findings" : session.question}</h2>
                <span className="badge" data-research-state={session.status}>
                  {session.status}
                </span>
                {["paused", "failed"].includes(session.status) && !active && (
                  <button
                    onClick={() =>
                      void operation(
                        () =>
                          call("research.resume", { session_id: session.id }),
                        "Inspect the investigation status for its result.",
                      )
                    }
                  >
                    Resume investigation
                  </button>
                )}
              </div>
              <p>{session.activity}</p>
              <Details value={session.plan} title="Research plan" />
              {session.error && (
                <>
                  <p>
                    Research needs attention. Any gathered evidence remains
                    available.
                  </p>
                  <Details value={session.error} title="Failure details" />
                </>
              )}
              <div className="category-tabs">
                <button
                  className={tab === "Findings" ? "selected" : ""}
                  onClick={() => setTab("Findings")}
                >
                  Findings
                </button>
                <button
                  className={tab === "Sources" ? "selected" : ""}
                  onClick={() => setTab("Sources")}
                >
                  Sources and evidence ({session.sources.length})
                </button>
              </div>
              {tab === "Findings" ? (
                <>
                  {session.final_report ? (
                    <div className="research-report">
                    <Markdown
                      text={session.final_report}
                      onLink={inspectLink}
                    />
                    </div>
                  ) : (
                    <p className="muted">
                      No final report yet. Follow actual source and activity
                      state.
                    </p>
                  )}
                  {session.final_report && (
                    <>
                      <label className="field">
                        Save findings to project
                        <select
                          aria-label="Report project"
                          value={project}
                          onChange={(e) => setProject(e.target.value)}
                        >
                          <option value="">Choose a project</option>
                          {resource.data?.projects.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="row">
                        <button
                          disabled={!project}
                          onClick={() =>
                            void operation(
                              () =>
                                call("research.save_report", {
                                  session_id: session.id,
                                  project_id: project,
                                  approved: true,
                                }),
                              "Report saved to the selected project.",
                            )
                          }
                        >
                          Save report to project
                        </button>
                        <button
                          onClick={() =>
                            void navigator.clipboard
                              .writeText(session.final_report)
                              .catch(report)
                          }
                        >
                          Copy report
                        </button>
                      </div>
                      <details>
                        <summary>Select individual findings</summary>
                        {session.findings.map((f, index) => (
                          <label className="check-field" key={index}>
                            <input
                              type="checkbox"
                              checked={findingIds.includes(index)}
                              onChange={(e) =>
                                setFindingIds(
                                  e.target.checked
                                    ? [...findingIds, index]
                                    : findingIds.filter((i) => i !== index),
                                )
                              }
                            />
                            <span>
                              {f.text}{" "}
                              <span className="muted">
                                ({f.kind.replaceAll("_", " ")})
                              </span>
                            </span>
                          </label>
                        ))}
                        <button
                          disabled={!project || !findingIds.length}
                          onClick={() =>
                            void operation(
                              () =>
                                call("research.save_report", {
                                  session_id: session.id,
                                  project_id: project,
                                  approved: true,
                                  finding_indices: findingIds,
                                }),
                              "Selected findings saved to the project.",
                            )
                          }
                        >
                          Save selected findings
                        </button>
                      </details>
                    </>
                  )}
                </>
              ) : (
                <>
                  <div className="row">
                    <button
                      disabled={!sourceIds.length}
                      onClick={() =>
                        void operation(
                          () =>
                            call("research.save_sources", {
                              session_id: session.id,
                              source_ids: sourceIds,
                            }),
                          "Selected sources saved to Knowledge.",
                        )
                      }
                    >
                      Save selected sources to Knowledge
                    </button>
                    <button
                      disabled={
                        !session.sources.some(
                          (s) =>
                            ["read", "evidence", "saved"].includes(s.status) &&
                            /^https?:/.test(s.url),
                        )
                      }
                      onClick={() =>
                        void operation(
                          () =>
                            call("research.save_sources", {
                              session_id: session.id,
                              source_ids: session.sources
                                .filter(
                                  (s) =>
                                    ["read", "evidence", "saved"].includes(
                                      s.status,
                                    ) && /^https?:/.test(s.url),
                                )
                                .map((s) => s.id),
                            }),
                          "Read sources saved to Knowledge.",
                        )
                      }
                    >
                      Save read web sources
                    </button>
                  </div>
                  {session.sources.map((source) => (
                    <article className="record-card" key={source.id}>
                      <label className="check-field">
                        <input
                          type="checkbox"
                          disabled={
                            !["read", "evidence", "saved"].includes(
                              source.status,
                            ) || !/^https?:/.test(source.url)
                          }
                          checked={sourceIds.includes(source.id)}
                          onChange={(e) =>
                            setSourceIds(
                              e.target.checked
                                ? [...sourceIds, source.id]
                                : sourceIds.filter((id) => id !== source.id),
                            )
                          }
                        />
                        <strong>{source.title}</strong>
                      </label>
                      <p className="muted">
                        {source.domain} · {source.status}
                      </p>
                      <p className="source-url">{source.url}</p>
                      <button onClick={() => setSelectedSource(source)}>
                        Inspect source and evidence
                      </button>
                    </article>
                  ))}
                </>
              )}
              <Details value={session} title="Research developer details" />
            </>
          ) : (
            <div className="empty-workspace">
              <h2>{id ? "Loading investigation…" : "Begin with a question"}</h2>
              <p>
                Sources and findings will appear as the investigation
                progresses.
              </p>
            </div>
          )}
        </section>
      </div>
      <Sheet
        open={Boolean(selectedSource)}
        onOpenChange={(open) => {
          if (!open) setSelectedSource(undefined);
        }}
        title={selectedSource?.title || "Source"}
        description="Inspect the material actually recorded for this source."
      >
        {selectedSource && (
          <>
            <p className="source-url">{selectedSource.url}</p>
            <p>
              {selectedSource.status} · retrieved{" "}
              {selectedSource.retrieved_at || "Not recorded"} · published{" "}
              {selectedSource.publication_date || "Unknown"}
            </p>
            {/^https?:/.test(selectedSource.url) && (
              <button
                onClick={() =>
                  void window.olive
                    .openExternal(selectedSource.url)
                    .catch(report)
                }
              >
                Open source in browser
              </button>
            )}
            {session?.evidence
              .filter((e) => e.source_id === selectedSource.id)
              .map((e) => (
                <article className="record-card" key={e.id}>
                  <p>{e.claim}</p>
                  <blockquote>{e.quote}</blockquote>
                  <p className="muted">{e.subquestion}</p>
                </article>
              ))}
            <Details value={selectedSource} />
          </>
        )}
      </Sheet>
      <details>
        <summary>Website learning and saved material</summary>
        <WebLibrary report={report} />
        <button
          disabled={active}
          onClick={() =>
            void operation(
              () => call("research.clear_cache", {}),
              "Temporary page cache cleared. Saved Knowledge remains available.",
            )
          }
        >
          Clear temporary page cache
        </button>
      </details>
    </WorkspacePage>
  );
}
