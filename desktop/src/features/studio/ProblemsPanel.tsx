import { AlertCircle, AlertTriangle, ChevronDown, ChevronRight, Info } from "lucide-react";
import { useMemo, useState } from "react";
import { groupProblems } from "./studioModel";
import { useTooling, relativePath, type Problem } from "./tooling";

export interface ProblemRow {
  file: string;
  line: number;
  column: number;
  severity: "error" | "warning" | "info";
  message: string;
  source: string;
}
// Problems come from two real places: the language server's live diagnostics
// for open documents and the parsed output of the last build or run.
export function useProblems(workspaceId: string, root: string): ProblemRow[] {
  const slice = useTooling(workspaceId);
  return useMemo(() => {
    const rows: ProblemRow[] = [];
    for (const [path, items] of Object.entries(slice.diagnostics))
      for (const item of items)
        rows.push({
          file: relativePath(root, path),
          line: item.range.start.line + 1,
          column: item.range.start.character + 1,
          severity: item.severity === 1 ? "error" : item.severity === 2 ? "warning" : "info",
          message: item.message,
          // V2 shows the origin as source(code), e.g. pyflakes(F401).
          source: `${item.source || "language server"}${item.code ? `(${item.code})` : ""}`,
        });
    const live = new Set(rows.map((row) => row.file.toLowerCase()));
    for (const item of slice.problems as Problem[]) {
      const file = item.file ? relativePath(root, item.file) : "";
      // The language server is authoritative for files it is watching.
      if (file && live.has(file.toLowerCase())) continue;
      rows.push({
        file,
        line: item.line || 0,
        column: item.column || 0,
        severity: item.severity === "warning" ? "warning" : item.severity === "info" ? "info" : "error",
        message: item.message,
        source: item.source || "build output",
      });
    }
    return rows.sort(
      (a, b) =>
        a.file.localeCompare(b.file) || a.line - b.line || a.column - b.column,
    );
  }, [slice.diagnostics, slice.problems, root]);
}
export function ProblemsPanel({
  problems,
  openFile,
  languageState,
  languageFailed = false,
}: {
  problems: ProblemRow[];
  openFile: (path: string, line?: number, column?: number) => void;
  languageState: string;
  languageFailed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const groups = groupProblems(problems);
  return (
    <div className="dock-panel problems-panel">
      {languageFailed && (
        <p className="dock-note" role="status">
          <AlertTriangle size={13} aria-hidden="true" /> Code intelligence stopped ({languageState}). Language-server diagnostics are unavailable until it restarts; build and run problems still appear.
        </p>
      )}
      {problems.length === 0 ? (
        <div className="dock-empty">
          <p className="dock-empty-line">
            No problems have been detected in the workspace. Diagnostics from the language server and the last build or run appear here as they happen.
          </p>
        </div>
      ) : (
        <ul className="problem-list" aria-label="Problems">
          {groups.map((group) => {
            const open = !collapsed.has(group.file);
            return (
              <li key={group.file || "(no file)"} className="problem-group">
                <button
                  className="problem-file"
                  aria-expanded={open}
                  onClick={() =>
                    setCollapsed((current) => {
                      const next = new Set(current);
                      if (next.has(group.file)) next.delete(group.file);
                      else next.add(group.file);
                      return next;
                    })
                  }
                >
                  {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
                  <strong>{group.file ? group.file.split("/").pop() : "No file"}</strong>
                  {group.file.includes("/") && <span className="problem-folder">{group.file.split("/").slice(0, -1).join("/")}</span>}
                  <span className="count" data-tone={group.errors ? "error" : "warning"} aria-label={`${group.errors} errors, ${group.warnings} warnings`}>
                    {group.items.length}
                  </span>
                </button>
                {open && (
                  <ul>
                    {group.items.map((problem, index) => (
                      <li key={index} data-severity={problem.severity}>
                        <button
                          className="problem-row"
                          disabled={!problem.file}
                          onClick={() => openFile(problem.file, problem.line || undefined, problem.column || undefined)}
                          title={problem.file ? `Go to ${problem.file}:${problem.line}:${problem.column}` : undefined}
                        >
                          {problem.severity === "error" ? (
                            <AlertCircle size={14} aria-label="Error" />
                          ) : problem.severity === "warning" ? (
                            <AlertTriangle size={14} aria-label="Warning" />
                          ) : (
                            <Info size={14} aria-label="Information" />
                          )}
                          <span className="problem-message">{problem.message}</span>
                          <span className="problem-source">{problem.source}</span>
                          {problem.line ? (
                            <span className="problem-where">
                              [Ln {problem.line}, Col {problem.column || 1}]
                            </span>
                          ) : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
