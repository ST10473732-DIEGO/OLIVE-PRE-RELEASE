import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { call } from "../../services/api";
import { relativePath } from "./tooling";
import { workspaceSymbols } from "./languageClient";
import { symbolTag } from "./studioModel";

// Studio V2 §6.2 on the two search APIs that exist: plain, case-insensitive
// text search (studio.search: first 200 matches, UTF-8 text, no binaries or
// files over 2 MB) and workspace symbols from the running language server.
// Match case, whole word, regex, globs and replace do not exist, so they are
// not offered.
export function SearchView({
  workspaceId,
  root,
  languages,
  openFile,
  report,
  focusSignal,
}: {
  workspaceId: string;
  root: string;
  languages: string[];
  openFile: (path: string, line?: number) => void;
  report: (error: unknown) => void;
  focusSignal: number;
}) {
  const [mode, setMode] = useState<"text" | "symbols">("text");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [matches, setMatches] = useState<[string, number, string][] | null>(null);
  const [symbols, setSymbols] = useState<{ name: string; kind: number; containerName: string; path: string; line: number }[] | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, [focusSignal]);
  useEffect(() => {
    setMatches(null);
    setSymbols(null);
  }, [workspaceId]);
  const run = async () => {
    const text = query.trim();
    if (!text) return;
    setBusy(true);
    try {
      if (mode === "text") {
        const value = await call<{ matches: [string, number, string][] }>("studio.search", { workspace_id: workspaceId, query: text });
        setMatches(value.matches);
      } else {
        const items = await workspaceSymbols(workspaceId, languages[0], text);
        setSymbols(items.map((item) => ({ name: item.name, kind: item.kind, containerName: item.containerName, path: relativePath(root, item.path), line: item.range.start.line + 1 })));
      }
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  const grouped = useMemo(() => {
    const map = new Map<string, [number, string][]>();
    for (const [file, line, text] of matches || []) map.set(file, [...(map.get(file) || []), [line, text]]);
    return [...map.entries()];
  }, [matches]);
  const highlight = (text: string) => {
    const at = text.toLowerCase().indexOf(query.trim().toLowerCase());
    if (at < 0 || !query.trim()) return text;
    return (
      <>
        {text.slice(0, at)}
        <mark>{text.slice(at, at + query.trim().length)}</mark>
        {text.slice(at + query.trim().length)}
      </>
    );
  };
  return (
    <div className="sidebar-view search-view">
      <div className="side-head">
        <h2>Search</h2>
      </div>
      <div className="side-pad">
        <div className="segmented" role="group" aria-label="Search mode">
          <button aria-pressed={mode === "text"} onClick={() => setMode("text")}>Text</button>
          <button
            aria-pressed={mode === "symbols"}
            disabled={!languages.length}
            title={languages.length ? "Workspace symbols from the language server" : "Symbols need a running language server (open a Python or C# file)"}
            onClick={() => setMode("symbols")}
          >
            Symbols
          </button>
        </div>
        <form
          className="search side-search"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <Search size={13} aria-hidden="true" />
          <input
            ref={input}
            aria-label={mode === "text" ? "Search text in workspace" : "Search workspace symbols"}
            placeholder={mode === "text" ? "Search (Enter)" : "Symbol name (Enter)"}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
        <p className="side-note">
          {mode === "text" ? "Plain text, case-insensitive, first 200 matches." : "Symbols reported by the language server."}
        </p>
      </div>
      <div className="side-scroll" aria-busy={busy}>
        {busy && <p className="side-note" role="status">Searching…</p>}
        {mode === "text" && matches && !busy && (
          <>
            <p className="side-note" role="status">
              {matches.length === 0
                ? "No matching lines."
                : `${matches.length}${matches.length === 200 ? "+" : ""} ${matches.length === 1 ? "result" : "results"} in ${grouped.length} ${grouped.length === 1 ? "file" : "files"}${matches.length === 200 ? " · narrow the query for more" : ""}`}
            </p>
            <ul className="search-results" aria-label="Search results">
              {grouped.map(([file, rows]) => (
                <li key={file}>
                  <button
                    className="search-file"
                    aria-expanded={!collapsed.has(file)}
                    onClick={() =>
                      setCollapsed((current) => {
                        const next = new Set(current);
                        if (next.has(file)) next.delete(file);
                        else next.add(file);
                        return next;
                      })
                    }
                    title={file}
                  >
                    {collapsed.has(file) ? <ChevronRight size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
                    <span className="scm-name">{file.split("/").pop()}</span>
                    <span className="scm-folder">{file.split("/").slice(0, -1).join("/")}</span>
                    <span className="count" data-tone="neutral" aria-label={`${rows.length} matches`}>{rows.length}</span>
                  </button>
                  {!collapsed.has(file) && (
                    <ul>
                      {rows.map(([line, text], index) => (
                        <li key={index}>
                          <button className="search-match" onClick={() => openFile(file, line)} title={`${file}:${line}`}>
                            <span className="search-text">{highlight(text.trim())}</span>
                            <span className="search-line">{line}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        {mode === "symbols" && symbols && !busy && (
          <ul className="search-results" aria-label="Symbol results">
            {symbols.slice(0, 100).map((item, index) => (
              <li key={index}>
                <button className="search-match" onClick={() => openFile(item.path, item.line)} title={`${item.path}:${item.line}`}>
                  <span className="symbol-tag" title={symbolTag(item.kind).label} aria-hidden="true">{symbolTag(item.kind).tag}</span>
                  <span className="search-text">{item.name}</span>
                  <span className="search-line">{item.containerName || item.path}</span>
                </button>
              </li>
            ))}
            {symbols.length === 0 && <li className="side-note">No symbols match.</li>}
          </ul>
        )}
      </div>
    </div>
  );
}
