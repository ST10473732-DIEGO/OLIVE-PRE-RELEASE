import type { RecordTarget } from "../services/handoff";
import { useEffect, useState } from "react";
import { call } from "../services/api";
import { useResource } from "../services/useResource";
import {
  WorkspacePage,
  Details,
  Main,
  Side,
  Panel,
  EmptyState,
  Pill,
  Facts,
  Disclosure,
} from "../components/WorkspacePage";
import { Sheet } from "../components/Sheet";
import {
  BookOpen,
  Search,
  Plus,
  RefreshCw,
  ListTodo,
  ScanSearch,
  FileText,
  Activity,
  Wrench,
  Globe,
  Info,
} from "lucide-react";
const UPGRADE_LABEL: Record<string, string> = {
  completed: "Completed",
  partial: "Partially completed",
  blocked: "Blocked / unavailable",
  cancelled: "Cancelled",
  failed: "Failed",
  running: "Working",
};
const healthTone = (health: string): "success" | "warning" | "error" | undefined =>
  /ok|healthy|ready|indexed/i.test(health)
    ? "success"
    : /missing|error|fail|broken/i.test(health)
      ? "error"
      : /stale|pending|partial|lexical/i.test(health)
        ? "warning"
        : undefined;
import { WebLibrary } from "./research/WebLibrary";
interface Source {
  id: string;
  name: string;
  kind: string;
  chat_id: string;
  chat_title: string;
  health: string;
  chunk_count: number;
  indexed: boolean;
  embedding_indexed: boolean;
}
interface Job {
  id: string;
  filename: string;
  state: string;
  error?: string;
  progress: number;
}
interface Evidence {
  label?: string;
  name?: string;
  text?: string;
  excerpt?: string;
  score: number;
  lexical: number;
  semantic: number;
}
export default function Knowledge({
  target,
  chatId,
  report,
}: {
  target?: RecordTarget;
  chatId: string;
  report: (e: unknown) => void;
}) {
  const resource = useResource(
    async () => ({
      sources: await call<Source[]>("knowledge.list", {}),
      jobs: await call<Job[]>("knowledge.jobs", {}),
      upgrade: await call<{
        state: string;
        summary: string;
        completed: number;
        total: number;
      }>("knowledge.upgrade_status", {}),
    }),
    ["knowledge", "indexing", "knowledge.upgrade"],
  );
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("All");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Source>();
  useEffect(() => {
    if (!target || target.kind === "Web Knowledge") return;
    let live = true;
    void call<Source[]>("knowledge.list", {})
      .then((sources) => {
        if (live)
          setSelected(
            sources.find(
              (source) =>
                source.id === target.id &&
                (!target.chat_id || source.chat_id === target.chat_id),
            ),
          );
      })
      .catch(report);
    return () => {
      live = false;
    };
  }, [target]);
  const [remove, setRemove] = useState<Source>();
  const [jobs, setJobs] = useState(false);
  const [inspect, setInspect] = useState(false);
  const [question, setQuestion] = useState("");
  const [evidence, setEvidence] = useState<Evidence[]>();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const sources = (resource.data?.sources || []).filter(
    (s) =>
      (kind === "All" || s.kind === kind) &&
      `${s.name} ${s.chat_title} ${s.health}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const operation = async (fn: () => Promise<unknown>, message?: string) => {
    setBusy(true);
    setNotice("Working…");
    try {
      await fn();
      setNotice(message || "");
      await resource.refresh();
    } catch (e) {
      setNotice("The operation did not complete.");
      report(e);
    } finally {
      setBusy(false);
    }
  };
  const sourceAction = (action: "reindex" | "remove", source: Source) =>
    call(`knowledge.${action}`, {
      chat_id: source.chat_id,
      document_id: source.id,
    });
  const all = resource.data?.sources || [];
  const semantic = all.filter((s) => s.embedding_indexed).length;
  const lexical = all.filter((s) => s.indexed && !s.embedding_indexed).length;
  const unindexed = all.filter((s) => !s.indexed).length;
  const activeJobs = (resource.data?.jobs || []).filter((j) => ["queued", "running", "paused"].includes(j.state));
  const recentJobs = (resource.data?.jobs || []).slice(-5).reverse();
  const upgrade = resource.data?.upgrade;
  return (
    <WorkspacePage
      layout="fill"
      className="knowledge"
      icon={<BookOpen size={18} />}
      title="Knowledge"
      description="Local sources, index health and retrieval evidence."
      status={activeJobs.length ? `${activeJobs.length} indexing` : all.length ? `${all.length} source${all.length === 1 ? "" : "s"}` : undefined}
      statusTone={activeJobs.length ? "live" : "idle"}
      actions={
        <>
          <button onClick={() => setJobs(true)}>
            <ListTodo size={15} aria-hidden="true" />
            Indexing jobs
          </button>
          <button onClick={() => setInspect(true)}>
            <ScanSearch size={15} aria-hidden="true" />
            Retrieval inspector
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() =>
              void operation(
                () =>
                  window.olive.fileAction({
                    action: "attach",
                    chat_id: chatId,
                    permanent: true,
                  }),
                "Source selection finished. Inspect indexing jobs for progress.",
              )
            }
          >
            <Plus size={16} aria-hidden="true" />
            Add source
          </button>
        </>
      }
      toolbar={
        <>
          <label className="search">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search knowledge"
              placeholder="Find a source, conversation or health state…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <select
            aria-label="Source type"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setPage(0);
            }}
          >
            <option>All</option>
            {[...new Set(resource.data?.sources.map((s) => s.kind))].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
          <span className="grow" />
          <span className="knowledge-count">
            {resource.loading && !resource.data ? "Loading…" : `${sources.length} of ${all.length} source${all.length === 1 ? "" : "s"}`}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh knowledge"
            title="Refresh"
            disabled={resource.loading}
            onClick={() => void resource.refresh()}
          >
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </>
      }
      side={
        <Side title="Index" label="Index health and jobs">
          <Panel title="Index health" icon={<Activity size={15} />} headingLevel={3}>
            <Facts
              items={[
                ["Sources", String(all.length)],
                ["Semantic + lexical", String(semantic)],
                ["Lexical only", String(lexical)],
                ["Not indexed", String(unindexed)],
                ["Jobs in flight", String(activeJobs.length)],
              ]}
            />
          </Panel>
          <Panel
            title="Indexing jobs"
            sub={recentJobs.length ? "Most recent first" : "Nothing queued"}
            icon={<ListTodo size={15} />}
            headingLevel={3}
            tight={recentJobs.length > 0}
            actions={
              <button className="quiet" onClick={() => setJobs(true)}>
                All jobs
              </button>
            }
          >
            {recentJobs.length ? (
              <div className="ws-list">
                {recentJobs.map((j) => (
                  <div className="ws-row knowledge-job" key={j.id}>
                    <span className="ws-row-text">
                      <strong>{j.filename}</strong>
                      {j.state === "running" && <span>{Math.round(j.progress)}% of indexing work</span>}
                      {j.error && <span>{String(j.error).slice(0, 80)}</span>}
                    </span>
                    <Pill tone={j.state === "failed" ? "error" : j.state === "running" ? "accent" : j.state === "completed" ? "success" : undefined}>
                      {j.state}
                    </Pill>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted small knowledge-note">Jobs appear here while sources are being indexed.</p>
            )}
          </Panel>
          <Disclosure summary="Index maintenance" className="knowledge-maintenance">
            <p className="muted small">
              Upgrade lexical-only sources when the configured local embedding model
              is available.
            </p>
            <button
              disabled={busy}
              onClick={() =>
                void operation(async () => {
                  await call<{ summary: string }>(
                    "knowledge.upgrade",
                    {},
                  );
                })
              }
            >
              <Wrench size={14} aria-hidden="true" />
              Upgrade lexical indexes
            </button>
            <p role="status" className="small muted">{upgrade?.summary}</p>
            {upgrade?.state === "running" && (
              <button
                className="quiet"
                onClick={() =>
                  void call("knowledge.cancel_upgrade", {}).catch(report)
                }
              >
                Cancel index upgrade
              </button>
            )}
          </Disclosure>
        </Side>
      }
    >
      <Main className="knowledge-main" label="Sources">
        {resource.error && <p role="alert">{resource.error}</p>}
        <p role="status" className="knowledge-status">
          {notice ||
            (resource.loading && !resource.data ? "Loading local sources…" : "")}
        </p>
        {upgrade && upgrade.state !== "idle" && (
          <section aria-label="Index upgrade outcome" role="status" className="record-card ws-notice knowledge-upgrade" data-tone={upgrade.state === "blocked" || upgrade.state === "failed" ? "warning" : "accent"}>
            <Info size={15} aria-hidden="true" />
            <div className="grow">
              <strong>{UPGRADE_LABEL[upgrade.state] || upgrade.state}</strong>
              <p>{upgrade.summary}</p>
            </div>
          </section>
        )}
        {!sources.length && resource.data && (
          <EmptyState
            className="empty-workspace"
            icon={<BookOpen size={26} />}
            title={query ? "No matching sources" : "Build on what you know"}
            actions={
              !query && (
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    void operation(
                      () =>
                        window.olive.fileAction({
                          action: "attach",
                          chat_id: chatId,
                          permanent: true,
                        }),
                      "Source selection finished. Inspect indexing jobs for progress.",
                    )
                  }
                >
                  <Plus size={14} aria-hidden="true" />
                  Add a local document
                </button>
              )
            }
          >
            {query
              ? "Nothing matches that search or type filter."
              : "Add local documents to retrieve relevant chunks with source evidence. Files stay where they are; OLIVE keeps an index."}
          </EmptyState>
        )}
        <div className="record-list ws-cards knowledge-sources">
          {sources.slice(page * 30, page * 30 + 30).map((s) => (
            <article className="record-card ws-card knowledge-source" key={`${s.chat_id}:${s.id}`}>
              <div className="ws-card-head">
                <span className="ws-card-icon" aria-hidden="true">
                  <FileText size={16} />
                </span>
                <div className="ws-card-text">
                  <h3>{s.name}</h3>
                  <p className="ws-card-sub">
                    {s.chat_title} · {s.kind}
                  </p>
                </div>
                <Pill tone={healthTone(s.health)}>{s.health}</Pill>
              </div>
              <p className="muted knowledge-source-meta">
                {s.chunk_count} chunks ·{" "}
                {s.embedding_indexed
                  ? "Semantic and lexical index"
                  : s.indexed
                    ? "Lexical index"
                    : "Not indexed"}
              </p>
              <div className="ws-card-foot">
                <button className="quiet" onClick={() => setSelected(s)}>Source details</button>
                <span className="spacer" />
                <button
                  className="quiet"
                  disabled={busy}
                  onClick={() =>
                    void operation(
                      () => sourceAction("reindex", s),
                      "Re-index requested. Inspect indexing jobs for status.",
                    )
                  }
                >
                  Re-index
                </button>
                <button
                  className="quiet"
                  disabled={busy}
                  onClick={() =>
                    void operation(
                      () =>
                        window.olive.fileAction({
                          action: "relink",
                          chat_id: s.chat_id,
                          document_id: s.id,
                        }),
                      "Source selection finished.",
                    )
                  }
                >
                  Relink
                </button>
                <button className="quiet danger-action" onClick={() => setRemove(s)}>Remove</button>
              </div>
            </article>
          ))}
        </div>
        {sources.length > 30 && (
          <div className="row">
            <button className="quiet" disabled={!page} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <span>Page {page + 1}</span>
            <button
              className="quiet"
              disabled={(page + 1) * 30 >= sources.length}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        )}
        <Disclosure
          summary={
            <>
              <Globe size={15} aria-hidden="true" />
              Website learning and saved material
            </>
          }
          className="knowledge-web"
        >
          <WebLibrary
            target={target?.kind === "Web Knowledge" ? target : undefined}
            report={report}
          />
        </Disclosure>
      </Main>
      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelected(undefined);
        }}
        title={selected?.name || "Source details"}
        description="The original source and its local indexing state."
      >
        {selected && (
          <>
            <p>{selected.chat_title}</p>
            <p>
              {selected.health} · {selected.chunk_count} chunks
            </p>
            <Details value={selected} />
          </>
        )}
      </Sheet>
      <Sheet
        open={Boolean(remove)}
        onOpenChange={(open) => {
          if (!open) setRemove(undefined);
        }}
        title="Remove this source from Knowledge?"
        description="The source index is removed from OLIVE. The original file is retained."
      >
        <p>{remove?.name}</p>
        <button
          disabled={busy}
          onClick={() => {
            if (remove)
              void operation(async () => {
                await sourceAction("remove", remove);
                setRemove(undefined);
              }, "Source removed from Knowledge.");
          }}
        >
          Remove source
        </button>
      </Sheet>
      <Sheet
        open={jobs}
        onOpenChange={setJobs}
        title="Indexing jobs"
        description="Actual job state from the shared scheduler."
      >
        {!resource.data?.jobs.length && <p>No indexing jobs.</p>}
        {resource.data?.jobs
          .slice(-50)
          .reverse()
          .map((j) => (
            <article className="record-card" key={j.id}>
              <h3>{j.filename}</h3>
              <p>
                {j.state}
                {j.state === "running" &&
                  ` · ${Math.round(j.progress)}% of indexing work`}
              </p>
              {j.error && <Details value={j.error} title="Failure details" />}
              <div className="row">
                {(["pause", "resume", "cancel", "retry"] as const)
                  .filter((a) =>
                    a === "pause"
                      ? ["queued", "running"].includes(j.state)
                      : a === "resume"
                        ? j.state === "paused"
                        : a === "retry"
                          ? ["failed", "cancelled"].includes(j.state)
                          : ["queued", "running", "paused"].includes(j.state),
                  )
                  .map((action) => (
                    <button
                      key={action}
                      onClick={() =>
                        void operation(
                          () =>
                            call("knowledge.job_action", {
                              job_id: j.id,
                              action,
                            }),
                          `${action} requested.`,
                        )
                      }
                    >
                      {action[0].toUpperCase() + action.slice(1)}
                    </button>
                  ))}
              </div>
            </article>
          ))}
      </Sheet>
      <Sheet
        open={inspect}
        onOpenChange={setInspect}
        title="Retrieval inspector"
        description="Query the current conversation’s local sources. Scores come from retrieval, not model prose."
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void operation(
              async () =>
                setEvidence(
                  await call("knowledge.retrieve", {
                    chat_id: chatId,
                    query: question,
                  }),
                ),
              "Retrieval finished.",
            );
          }}
        >
          <label className="field">
            Retrieval query
            <input
              required
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          <button className="primary" disabled={busy || !question.trim()}>
            Inspect retrieval
          </button>
        </form>
        {evidence?.length === 0 && <p>No relevant chunks found.</p>}
        {evidence?.map((item, index) => (
          <article className="record-card" key={index}>
            <h3>{item.label || item.name || `Source ${index + 1}`}</h3>
            <p>{item.text || item.excerpt}</p>
            <p className="muted">
              Score {item.score.toFixed(3)} · lexical {item.lexical.toFixed(3)}{" "}
              · semantic {item.semantic.toFixed(3)}
            </p>
            <Details value={item} />
          </article>
        ))}
      </Sheet>
    </WorkspacePage>
  );
}
