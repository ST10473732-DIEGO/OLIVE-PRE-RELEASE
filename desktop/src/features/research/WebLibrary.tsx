import type { RecordTarget } from "../../services/handoff";
import { useEffect, useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Details } from "../../components/WorkspacePage";
import { Sheet } from "../../components/Sheet";

interface Source {
  id: string;
  title: string;
  name?: string;
  url: string;
  status: string;
  chunk_count: number;
  collection: string;
}
interface Download {
  id: string;
  filename: string;
  url: string;
  size: number;
  state: string;
  content_type: string;
}
interface Scope {
  urls: string[];
  mode: string;
  estimated_pages: number;
  note: string;
}
interface Learned {
  url: string;
  status?: string;
  source?: { title?: string; id: string };
  error?: string;
}

export function WebLibrary({
  report,
  target,
}: {
  report: (error: unknown) => void;
  target?: RecordTarget;
}) {
  const resource = useResource(async () => {
    const [sources, downloads, projects] = await Promise.all([
      call<Source[]>("research.web_sources", {}),
      call<Download[]>("research.downloads", {}),
      call<{ id: string; title: string }[]>("data.projects", {}),
    ]);
    return { sources, downloads, projects };
  }, ["web_knowledge", "projects"]);
  const [tab, setTab] = useState("Saved websites");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [urls, setUrls] = useState("");
  const [mode, setMode] = useState<
    "single" | "selected" | "subsection" | "sitemap"
  >("single");
  const [limit, setLimit] = useState(5);
  const [scope, setScope] = useState<Scope>();
  const [project, setProject] = useState("");
  const [collection, setCollection] = useState("Web Knowledge");
  const [downloadUrl, setDownloadUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [learned, setLearned] = useState<Learned[]>();
  const [preview, setPreview] = useState<{
    title: string;
    text: string;
    details: unknown;
  }>();
  useEffect(() => {
    if (!target) return;
    let live = true;
    void call<{ source: Source; text: string }>("research.web_source", {
      source_id: target.id,
    })
      .then((value) => {
        if (live)
          setPreview({
            title: value.source.title || value.source.url,
            text: value.text,
            details: value.source,
          });
      })
      .catch(report);
    return () => {
      live = false;
    };
  }, [target]);
  const [remove, setRemove] = useState<{
    kind: "source" | "download";
    id: string;
    name: string;
  }>();
  const operation = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setNotice("Waiting for the operation or its approval.");
    try {
      const value = await fn();
      setNotice(value === null ? "Cancelled; no export was created." : message);
      await resource.refresh();
    } catch (error) {
      setNotice("The operation did not complete. Review the reported result.");
      report(error);
    } finally {
      setBusy(false);
    }
  };
  const sources = (resource.data?.sources || []).filter((s) =>
    `${s.title} ${s.name} ${s.url} ${s.collection}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const downloads = (resource.data?.downloads || []).filter((s) =>
    `${s.filename} ${s.url}`.toLowerCase().includes(query.toLowerCase()),
  );
  const count = tab === "Downloads" ? downloads.length : sources.length;
  const currentPage = Math.min(page, Math.max(0, Math.ceil(count / 30) - 1));
  return (
    <section aria-label="Web library">
      <div className="category-tabs">
        {["Saved websites", "Learn a website", "Downloads"].map((name) => (
          <button
            key={name}
            className={name === tab ? "selected" : ""}
            onClick={() => {
              setTab(name);
              setPage(0);
            }}
          >
            {name}
          </button>
        ))}
      </div>
      <p role="status">{notice}</p>
      {resource.error && <p role="alert">{resource.error}</p>}
      {tab === "Learn a website" ? (
        <>
          <h2>Choose a bounded website scope</h2>
          <p>
            Preview the exact pages before requesting permission to store them
            in Knowledge.
          </p>
          <label className="field">
            Website URLs, one per line
            <textarea
              aria-label="Website URLs"
              disabled={busy}
              value={urls}
              onChange={(e) => {
                setUrls(e.target.value);
                setScope(undefined);
              }}
              rows={3}
              maxLength={32000}
            />
          </label>
          <div className="row">
            <select
              aria-label="Website scope"
              disabled={busy}
              value={mode}
              onChange={(e) => {
                setMode(e.target.value as typeof mode);
                setScope(undefined);
              }}
            >
              {[
                ["single", "One page"],
                ["selected", "Selected pages"],
                ["subsection", "Subsection"],
                ["sitemap", "Page sitemap"],
              ].map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
            <label>
              Page limit{" "}
              <input
                aria-label="Website page limit"
                disabled={busy}
                type="number"
                min={1}
                max={30}
                value={limit}
                onChange={(e) => {
                  setLimit(Number(e.target.value));
                  setScope(undefined);
                }}
              />
            </label>
            <button
              disabled={busy || !urls.trim()}
              onClick={() =>
                void operation(async () => {
                  setScope(
                    await call<Scope>("research.scope", {
                      urls: urls
                        .split(/\r?\n/)
                        .map((s) => s.trim())
                        .filter(Boolean),
                      mode,
                      limit,
                    }),
                  );
                }, "Scope ready for review.")
              }
            >
              Preview scope
            </button>
          </div>
          {scope && (
            <article className="record-card">
              <h3>Pages in this scope ({scope.urls.length})</h3>
              <ul>
                {scope.urls.map((url) => (
                  <li className="source-url" key={url}>
                    {url}
                  </li>
                ))}
              </ul>
              <p>{scope.note}</p>
              <label className="field">
                Collection
                <input
                  value={collection}
                  onChange={(e) => setCollection(e.target.value)}
                  maxLength={200}
                />
              </label>
              <label className="field">
                Project
                <select
                  value={project}
                  onChange={(e) => setProject(e.target.value)}
                >
                  <option value="">Global Knowledge</option>
                  {resource.data?.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={busy || !scope.urls.length}
                onClick={() =>
                  void operation(async () => {
                    const result = await call<{ results: Learned[] }>(
                      "research.learn_urls",
                      {
                        urls: scope.urls,
                        collection,
                        ...(project ? { project_id: project } : {}),
                      },
                    );
                    setLearned(result.results);
                  }, "Website learning finished; inspect each page result below.")
                }
              >
                Review and learn these pages
              </button>
            </article>
          )}
          {learned?.map((result, index) => (
            <article className="record-card" key={index}>
              <p className="source-url">{result.url}</p>
              <strong>
                {result.status === "failed"
                  ? "Failed"
                  : result.source
                    ? "Saved to Knowledge"
                    : "Inspect result"}
              </strong>
              {result.error && (
                <Details value={result.error} title="Failure details" />
              )}
              <Details value={result} />
            </article>
          ))}
        </>
      ) : (
        <>
          <label className="search">
            <input
              aria-label="Search web library"
              placeholder="Search saved material"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
          {tab === "Downloads" && (
            <>
              <h2>Quarantined downloads</h2>
              <p>
                Downloaded files stay inert. Reading supports text and PDF;
                exporting does not run a file.
              </p>
              <div className="row">
                <input
                  aria-label="Download URL"
                  placeholder="https://…"
                  value={downloadUrl}
                  onChange={(e) => setDownloadUrl(e.target.value)}
                />
                <button
                  disabled={busy || !downloadUrl.trim()}
                  onClick={() =>
                    void operation(
                      () => call("research.download", { url: downloadUrl }),
                      "Download stored in quarantine.",
                    )
                  }
                >
                  Review download
                </button>
              </div>
            </>
          )}
          {tab === "Saved websites"
            ? sources
                .slice(currentPage * 30, currentPage * 30 + 30)
                .map((source) => (
                  <article className="record-card" key={source.id}>
                    <h3>{source.title || source.name || source.url}</h3>
                    <p className="source-url">{source.url}</p>
                    <p>
                      {source.status} · {source.chunk_count} chunks ·{" "}
                      {source.collection}
                    </p>
                    <div className="row">
                      <button
                        disabled={busy}
                        onClick={() =>
                          void operation(async () => {
                            const value = await call<{
                              source: unknown;
                              text: string;
                            }>("research.web_source", { source_id: source.id });
                            setPreview({
                              title: source.title || source.url,
                              text: value.text,
                              details: value.source,
                            });
                          }, "Saved source opened.")
                        }
                      >
                        Read saved content
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          void operation(
                            () =>
                              call("research.refresh_web", {
                                source_id: source.id,
                              }),
                            "Source refresh finished.",
                          )
                        }
                      >
                        Refresh source
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          setRemove({
                            kind: "source",
                            id: source.id,
                            name: source.title || source.url,
                          })
                        }
                      >
                        Remove source
                      </button>
                    </div>
                  </article>
                ))
            : downloads
                .slice(currentPage * 30, currentPage * 30 + 30)
                .map((download) => (
                  <article className="record-card" key={download.id}>
                    <h3>{download.filename}</h3>
                    <p>
                      {download.state} · {Math.ceil(download.size / 1024)} KB ·{" "}
                      {download.content_type}
                    </p>
                    <p className="source-url">{download.url}</p>
                    <div className="row">
                      <button
                        disabled={busy}
                        onClick={() =>
                          void operation(async () => {
                            const value = await call<{ text: string }>(
                              "research.read_download",
                              { download_id: download.id },
                            );
                            setPreview({
                              title: download.filename,
                              text: value.text,
                              details: download,
                            });
                          }, "Document read without execution.")
                        }
                      >
                        Read document
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          void operation(
                            () =>
                              call("research.import_download", {
                                download_id: download.id,
                                ...(project ? { project_id: project } : {}),
                                collection: "Downloads",
                              }),
                            "Document imported into Knowledge.",
                          )
                        }
                      >
                        Import into Knowledge
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          void operation(
                            () =>
                              window.olive.fileAction({
                                action: "export-download",
                                download_id: download.id,
                              }),
                            "Download exported; no file was executed.",
                          )
                        }
                      >
                        Export to new file
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          setRemove({
                            kind: "download",
                            id: download.id,
                            name: download.filename,
                          })
                        }
                      >
                        Remove download
                      </button>
                    </div>
                    <Details value={download} />
                  </article>
                ))}
          {!count && (
            <p className="muted">
              {query ? "No matching saved material." : "No saved material yet."}
            </p>
          )}
          {count > 30 && (
            <div className="row">
              <button
                disabled={!currentPage}
                onClick={() => setPage(currentPage - 1)}
              >
                Previous
              </button>
              <span>
                Page {currentPage + 1} of {Math.ceil(count / 30)}
              </span>
              <button
                disabled={(currentPage + 1) * 30 >= count}
                onClick={() => setPage(currentPage + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      <Sheet
        open={Boolean(preview)}
        onOpenChange={(open) => {
          if (!open) setPreview(undefined);
        }}
        title={preview?.title || "Saved content"}
        description="Plain text from the saved source; embedded content does not execute."
      >
        {preview && (
          <>
            <pre className="source-text">{preview.text.slice(0, 100000)}</pre>
            {preview.text.length > 100000 && (
              <p>Preview limited to 100,000 characters.</p>
            )}
            <Details value={preview.details} />
          </>
        )}
      </Sheet>
      <Sheet
        open={Boolean(remove)}
        onOpenChange={(open) => {
          if (!open) setRemove(undefined);
        }}
        title="Remove local material"
        description={remove?.name || ""}
      >
        <p>This removes the local record. The original website is unchanged.</p>
        <div className="row">
          <button onClick={() => setRemove(undefined)}>Keep material</button>
          <button
            disabled={busy}
            onClick={() =>
              void operation(async () => {
                if (!remove) return;
                await (remove.kind === "source"
                  ? call("research.remove_web", { source_id: remove.id })
                  : call("research.remove_download", {
                      download_id: remove.id,
                    }));
                setRemove(undefined);
              }, "Local material removed.")
            }
          >
            Remove local material
          </button>
        </div>
      </Sheet>
    </section>
  );
}
