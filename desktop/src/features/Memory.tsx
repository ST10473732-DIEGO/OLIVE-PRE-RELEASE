import type { RecordTarget } from "../services/handoff";
import { useEffect, useState } from "react";
import { call } from "../services/api";
import { useResource } from "../services/useResource";
import {
  WorkspacePage,
  Details,
  Rail,
  Main,
  Side,
  Seg,
  Panel,
  EmptyState,
  SectionHead,
  Pill,
} from "../components/WorkspacePage";
import { Sheet } from "../components/Sheet";
import {
  Brain,
  Search,
  Plus,
  RefreshCw,
  Download,
  Sparkles,
  Pencil,
  Trash2,
  Layers,
  Info,
} from "lucide-react";
interface MemoryRecord {
  id: string;
  content: string;
  category: string;
  source_title?: string;
  source_excerpt?: string;
  created_at?: string;
  confidence?: number;
}
export default function Memory({
  report,
  target,
}: {
  report: (e: unknown) => void;
  target?: RecordTarget;
}) {
  const [linked, setLinked] = useState<MemoryRecord>();
  useEffect(() => {
    if (!target) return;
    let live = true;
    void call<MemoryRecord[]>("data.memories", {})
      .then((records) => {
        const found = records.find((record) => record.id === target.id);
        if (!found)
          throw new Error("This linked memory is no longer available.");
        if (live) setLinked(found);
      })
      .catch(report);
    return () => {
      live = false;
    };
  }, [target]);
  const [suggestionDrafts, setSuggestionDrafts] = useState<
    Record<string, string>
  >({});
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const resource = useResource(
    async () => ({
      memories: await call<MemoryRecord[]>("data.memories", {}),
      suggestions: await call<MemoryRecord[]>("data.suggestions", {}),
    }),
    ["memories", "memory_suggestion"],
  );
  const [edit, setEdit] = useState<MemoryRecord>();
  const [remove, setRemove] = useState<MemoryRecord>();
  const [suggestion, setSuggestion] = useState(false);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  const rows = (resource.data?.memories || []).filter(
    (m) =>
      (category === "All" || m.category === category) &&
      `${m.content} ${m.source_title || ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const operation = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await resource.refresh();
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  const all = resource.data?.memories || [];
  const categories = [...new Set(all.map((m) => m.category))].sort();
  const countOf = (c: string) => all.filter((m) => m.category === c).length;
  const visible = rows.slice(page * 30, page * 30 + 30);
  const groups = category === "All"
    ? [...new Set(visible.map((m) => m.category))].map((c) => [c, visible.filter((m) => m.category === c)] as const)
    : [[category, visible] as const];
  const suggestions = resource.data?.suggestions || [];
  const addMemory = () => setEdit({ id: "", content: "", category: "manual" });
  return (
    <WorkspacePage
      layout="fill"
      className="memory"
      icon={<Brain size={18} />}
      title="Memory"
      description="Useful facts and preferences, with their sources."
      status={suggestions.length ? `${suggestions.length} to review` : all.length ? `${all.length} saved` : undefined}
      statusTone={suggestions.length ? "warning" : "idle"}
      actions={
        <>
          <button onClick={() => setSuggestion(true)}>
            <Sparkles size={15} aria-hidden="true" />
            Suggestions ({suggestions.length})
          </button>
          <button
            onClick={() =>
              void window.olive
                .fileAction({ action: "export-memory" })
                .catch(report)
            }
          >
            <Download size={15} aria-hidden="true" />
            Export
          </button>
          <button className="primary" onClick={addMemory}>
            <Plus size={16} aria-hidden="true" />
            Add memory
          </button>
        </>
      }
      rail={
        <Rail title="Categories" label="Memory categories">
          <Seg
            vertical
            label="Memory category"
            value={category}
            onChange={(value) => {
              setCategory(value);
              setPage(0);
            }}
            options={[
              { value: "All", label: "All memories", icon: <Layers size={15} aria-hidden="true" />, count: all.length },
              ...categories.map((c) => ({ value: c, label: c, count: countOf(c) })),
            ]}
          />
        </Rail>
      }
      side={
        <Side title="Review" label="Memory review">
          <Panel
            title="Suggestions"
            sub={suggestions.length ? "From recent conversations" : "Nothing waiting"}
            icon={<Sparkles size={15} />}
            headingLevel={3}
            tone={suggestions.length ? "accent" : undefined}
            actions={
              suggestions.length ? (
                <button className="quiet" onClick={() => setSuggestion(true)}>
                  Review
                </button>
              ) : undefined
            }
          >
            {suggestions.length ? (
              <ul className="memory-suggestion-preview">
                {suggestions.slice(0, 3).map((m) => (
                  <li key={m.id}>{m.content}</li>
                ))}
                {suggestions.length > 3 && <li className="muted">and {suggestions.length - 3} more…</li>}
              </ul>
            ) : (
              <p className="muted small memory-note">
                When a conversation reveals a durable fact or preference, OLIVE proposes it here. Nothing is saved until you approve it.
              </p>
            )}
          </Panel>
          <Panel title="What Memory is" icon={<Info size={15} />} headingLevel={3}>
            <ul className="memory-about">
              <li>Short, durable facts and preferences that OLIVE may use in future conversations.</li>
              <li>Each memory keeps its source: the conversation it came from, or “manual” when you wrote it.</li>
              <li>Stored only on this device. Edit or delete anything; export the whole set as a file.</li>
            </ul>
          </Panel>
        </Side>
      }
      toolbar={
        <>
          <label className="search">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search memories"
              placeholder="Search memories…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <span className="grow" />
          <span className="memory-count">
            {!resource.data ? "Loading…" : `${rows.length} of ${all.length} memor${all.length === 1 ? "y" : "ies"}`}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh memories"
            title="Refresh"
            disabled={resource.loading}
            onClick={() => void resource.refresh()}
          >
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </>
      }
    >
      <Main className="memory-main" label="Memories">
        {resource.error && <p role="alert">{resource.error}</p>}
        {!resource.data && <p role="status">Loading memories…</p>}
        {resource.data && !rows.length && (
          <EmptyState
            className="empty-workspace"
            icon={<Brain size={26} />}
            title={query ? "No matching memories" : "Keep what matters"}
            actions={
              !query && (
                <>
                  <button className="primary" onClick={addMemory}>
                    <Plus size={14} aria-hidden="true" />
                    Add a memory
                  </button>
                  {suggestions.length > 0 && (
                    <button onClick={() => setSuggestion(true)}>
                      Review {suggestions.length} suggestion{suggestions.length === 1 ? "" : "s"}
                    </button>
                  )}
                </>
              )
            }
          >
            {query
              ? "Nothing matches that search in this category."
              : "Add a durable fact or review a suggestion from a conversation. Memories are short, sourced and stay on this device."}
          </EmptyState>
        )}
        <div className="record-list memory-groups">
          {groups.map(([name, items]) => (
            <section className="memory-group" key={name} aria-label={name}>
              {category === "All" && (
                <SectionHead>
                  {name} · {items.length}
                </SectionHead>
              )}
              <div className="ws-cards memory-cards">
                {items.map((m) => (
                  <article className="record-card ws-card memory-card" key={m.id}>
                    <div className="memory-card-head">
                      <Pill tone={m.category === "manual" ? undefined : "olive"}>{m.category}</Pill>
                      {(m.source_title || "Manual").toLowerCase() !==
                        m.category.toLowerCase() && (
                        <span className="muted small">{m.source_title || "Manual"}</span>
                      )}
                      <span className="spacer" />
                      <div className="memory-card-actions">
                        <button className="icon-button" aria-label="Edit" title="Edit" onClick={() => setEdit({ ...m })}>
                          <Pencil size={14} aria-hidden="true" />
                        </button>
                        <button className="icon-button" aria-label="Delete" title="Delete" onClick={() => setRemove(m)}>
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      </div>
                    </div>
                    <p className="record-content">{m.content}</p>
                    <details>
                      <summary>Source and context</summary>
                      <p>{m.source_excerpt || "No source excerpt recorded."}</p>
                      <p className="muted">
                        {m.created_at}
                        {m.confidence !== undefined && ` · Confidence ${m.confidence}`}
                      </p>
                      <Details value={m} />
                    </details>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
        {rows.length > 30 && (
          <div className="row">
            <button className="quiet" disabled={!page} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <span>Page {page + 1}</span>
            <button
              className="quiet"
              disabled={(page + 1) * 30 >= rows.length}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        )}
      </Main>
      <Sheet
        open={Boolean(linked)}
        onOpenChange={(value) => {
          if (!value) setLinked(undefined);
        }}
        title="Linked memory"
        description="The saved record linked to this project."
      >
        <p>{linked?.content}</p>
        <p>{linked?.category}</p>
        <p>{linked?.source_excerpt || "No source excerpt recorded."}</p>
        <Details value={linked} title="Source and context" />
      </Sheet>
      <Sheet
        open={Boolean(edit)}
        onOpenChange={(open) => {
          if (!open && !busy) setEdit(undefined);
        }}
        title={edit?.id ? "Edit memory" : "Add memory"}
        description="Save a fact or preference to your native local Memory."
      >
        {edit && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void operation(async () => {
                await call("data.memory_save", {
                  content: edit.content,
                  category: edit.category,
                  ...(edit.id ? { memory_id: edit.id } : {}),
                });
                setEdit(undefined);
              });
            }}
          >
            <label className="field">
              Memory
              <textarea
                required
                rows={6}
                value={edit.content}
                onChange={(e) => setEdit({ ...edit, content: e.target.value })}
              />
            </label>
            <label className="field">
              Category
              <input
                required
                value={edit.category}
                onChange={(e) => setEdit({ ...edit, category: e.target.value })}
              />
            </label>
            <button className="primary" disabled={busy || !edit.content.trim()}>
              Save memory
            </button>
          </form>
        )}
      </Sheet>
      <Sheet
        open={Boolean(remove)}
        onOpenChange={(open) => {
          if (!open) setRemove(undefined);
        }}
        title="Delete this memory?"
        description="This removes the saved memory. The original conversation is retained."
      >
        <p>{remove?.content}</p>
        <button
          disabled={busy}
          onClick={() => {
            if (remove)
              void operation(async () => {
                await call("data.memory_delete", { memory_id: remove.id });
                setRemove(undefined);
              });
          }}
        >
          Delete memory
        </button>
      </Sheet>
      <Sheet
        open={suggestion}
        onOpenChange={setSuggestion}
        title="Memory suggestions"
        description="Review the content before it becomes a saved memory."
      >
        {!resource.data?.suggestions.length && <p>No pending suggestions.</p>}
        {resource.data?.suggestions.map((m) => (
          <article className="record-card" key={m.id}>
            <label className="field">
              Suggested memory
              <textarea
                aria-label={`Edit suggested memory ${m.id}`}
                value={suggestionDrafts[m.id] ?? m.content}
                onChange={(e) =>
                  setSuggestionDrafts((current) => ({
                    ...current,
                    [m.id]: e.target.value,
                  }))
                }
              />
            </label>
            <Details value={m} title="Suggestion source" />
            <div className="row">
              <button
                disabled={busy}
                onClick={() =>
                  void operation(() =>
                    call("data.review_suggestion", {
                      suggestion_id: m.id,
                      approve: false,
                    }),
                  )
                }
              >
                Reject
              </button>
              <button
                disabled={busy}
                className="primary"
                onClick={() =>
                  void operation(() =>
                    call("data.review_suggestion", {
                      suggestion_id: m.id,
                      approve: true,
                      content: suggestionDrafts[m.id] ?? m.content,
                    }),
                  )
                }
              >
                Approve memory
              </button>
            </div>
          </article>
        ))}
      </Sheet>
    </WorkspacePage>
  );
}
