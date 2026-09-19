import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import { useMemo } from "react";
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
          message: item.code ? `${item.code}: ${item.message}` : item.message,
          source: item.source || "language server",
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
}: {
  problems: ProblemRow[];
  openFile: (path: string, line?: number, column?: number) => void;
  languageState: string;
}) {
  const errors = problems.filter((p) => p.severity === "error").length;
  const warnings = problems.filter((p) => p.severity === "warning").length;
  return (
    <div className="dock-panel problems-panel">
      <div className="dock-toolbar">
        <span className="small">
          {problems.length === 0
            ? "No problems reported"
            : `${errors} ${errors === 1 ? "error" : "errors"} · ${warnings} ${warnings === 1 ? "warning" : "warnings"}`}
        </span>
        <span className="small muted">{languageState}</span>
      </div>
      {problems.length === 0 ? (
        <div className="dock-empty">
          <p className="muted">
            Diagnostics from the language server and the last build or run appear
            here as they happen.
          </p>
        </div>
      ) : (
        <ul className="problem-list" aria-label="Problems">
          {problems.map((problem, index) => (
            <li key={index} data-severity={problem.severity}>
              <button
                className="problem-row"
                disabled={!problem.file}
                onClick={() => openFile(problem.file, problem.line || undefined, problem.column || undefined)}
                title={problem.file ? `Open ${problem.file}:${problem.line}` : undefined}
              >
                {problem.severity === "error" ? (
                  <AlertCircle size={14} aria-hidden="true" />
                ) : problem.severity === "warning" ? (
                  <AlertTriangle size={14} aria-hidden="true" />
                ) : (
                  <Info size={14} aria-hidden="true" />
                )}
                <span className="problem-message">{problem.message}</span>
                <span className="problem-where small muted">
                  {problem.file}
                  {problem.line ? `:${problem.line}` : ""}
                  {problem.column ? `:${problem.column}` : ""} · {problem.source}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
