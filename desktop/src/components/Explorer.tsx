import { useState, useRef } from "react";
import { ChevronDown, ChevronRight, FileCode2 } from "lucide-react";

const gitWord = (letter: string) =>
  ({ M: "modified", A: "added", D: "deleted", U: "untracked", R: "renamed", C: "copied", "!": "conflict", "•": "contains changes" } as Record<string, string>)[letter] || "changed";

export interface Entry {
  path: string;
  directory: boolean;
}
export function visibleEntries(entries: Entry[], collapsed: Set<string>) {
  return [...entries]
    .sort((a, b) => {
      const left = a.path.split("/");
      const right = b.path.split("/");
      for (let i = 0; i < Math.min(left.length, right.length); i++) {
        if (left[i] === right[i]) continue;
        const ld = i < left.length - 1 || a.directory;
        const rd = i < right.length - 1 || b.directory;
        return ld !== rd ? (ld ? -1 : 1) : left[i].localeCompare(right[i]);
      }
      return left.length - right.length;
    })
    .filter((e) => ![...collapsed].some((p) => e.path.startsWith(p + "/")));
}
/** Spoken form of a row's decorations, so they are never colour or glyph only. */
function describe(path: string, decorations: ExplorerDecorations): string {
  const parts: string[] = [];
  const git = decorations.git?.get(path);
  if (git) parts.push(gitWord(git));
  const counts = decorations.problems?.get(path);
  if (counts?.errors) parts.push(`${counts.errors} ${counts.errors === 1 ? "error" : "errors"}`);
  if (counts?.warnings) parts.push(`${counts.warnings} ${counts.warnings === 1 ? "warning" : "warnings"}`);
  if (decorations.dirty?.has(path)) parts.push("unsaved changes");
  return parts.join(", ");
}
export interface ExplorerDecorations {
  /** Git letter per path (M, A, D, U, !) or "•" for a folder with changes. */
  git?: Map<string, string>;
  /** Diagnostic counts per file path from the Problems store. */
  problems?: Map<string, { errors: number; warnings: number }>;
  /** Paths with unsaved editor changes. */
  dirty?: Set<string>;
}
export function Explorer({
  entries,
  active,
  open,
  decorations = {},
  collapseSignal = 0,
}: {
  entries: Entry[];
  active: string;
  open: (path: string) => void;
  decorations?: ExplorerDecorations;
  /** Bumped by "Collapse folders"; every folder collapses. */
  collapseSignal?: number;
}) {
  const [collapsed, setCollapsed] = useState(new Set<string>());
  const [signal, setSignal] = useState(collapseSignal);
  if (signal !== collapseSignal) {
    setSignal(collapseSignal);
    setCollapsed(new Set(entries.filter((e) => e.directory).map((e) => e.path)));
  }
  const [focused, setFocused] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const rows = visibleEntries(entries, collapsed);
  const toggle = (path: string) =>
    setCollapsed((old) => {
      const next = new Set(old);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  const focus = (index: number) => {
    const path = rows[index]?.path;
    if (path) {
      setFocused(path);
      root.current
        ?.querySelectorAll<HTMLElement>('[role="treeitem"]')
        .item(index)?.focus();
    }
  };
  return (
    <div ref={root} role="tree" aria-label="Workspace files">
      {rows.map((entry, index) => (
        <button
          key={entry.path}
          role="treeitem"
          aria-label={entry.path.split("/").pop()}
          aria-description={describe(entry.path, decorations) || undefined}
          title={entry.path}
          aria-level={entry.path.split("/").length}
          aria-expanded={
            entry.directory ? !collapsed.has(entry.path) : undefined
          }
          aria-selected={active === entry.path}
          tabIndex={
            entry.path ===
            (rows.some((e) => e.path === focused) ? focused : rows[0]?.path)
              ? 0
              : -1
          }
          className={active === entry.path ? "selected" : ""}
          data-git={decorations.git?.get(entry.path)}
          data-problems={
            decorations.problems?.get(entry.path)?.errors
              ? "error"
              : decorations.problems?.get(entry.path)?.warnings
                ? "warning"
                : undefined
          }
          // Indentation stops growing after eight levels so deep paths stay readable;
          // the title carries the full path and the sidebar is resizable.
          style={{
            paddingLeft:
              6 + Math.min(entry.path.split("/").length - 1, 8) * 12 + (entry.directory ? 0 : 14),
          }}
          onFocus={() => setFocused(entry.path)}
          onClick={() =>
            entry.directory ? toggle(entry.path) : open(entry.path)
          }
          onKeyDown={(event) => {
            if (
              ![
                "ArrowDown",
                "ArrowUp",
                "ArrowLeft",
                "ArrowRight",
                "Home",
                "End",
              ].includes(event.key)
            )
              return;
            event.preventDefault();
            if (event.key === "ArrowDown")
              focus(Math.min(index + 1, rows.length - 1));
            if (event.key === "ArrowUp") focus(Math.max(index - 1, 0));
            if (event.key === "Home") focus(0);
            if (event.key === "End") focus(rows.length - 1);
            if (event.key === "ArrowRight" && entry.directory) {
              if (collapsed.has(entry.path)) toggle(entry.path);
              else focus(index + 1);
            }
            if (event.key === "ArrowLeft") {
              if (entry.directory && !collapsed.has(entry.path))
                toggle(entry.path);
              else
                focus(
                  rows.findIndex(
                    (e) =>
                      e.path === entry.path.split("/").slice(0, -1).join("/"),
                  ),
                );
            }
          }}
        >
          {entry.directory ? (
            <>
              {collapsed.has(entry.path) ? (
                <ChevronRight size={12} aria-hidden="true" />
              ) : (
                <ChevronDown size={12} aria-hidden="true" />
              )}
            </>
          ) : (
            <FileCode2 size={14} aria-hidden="true" />
          )}
          <span className="tree-name">{entry.path.split("/").pop()}</span>
          {decorations.dirty?.has(entry.path) && (
            <span className="tree-dirty" title="Unsaved changes" aria-hidden="true">●</span>
          )}
          {(() => {
            const counts = decorations.problems?.get(entry.path);
            const total = (counts?.errors || 0) + (counts?.warnings || 0);
            return total ? (
              <span className="tree-problems" title={`${counts!.errors} errors, ${counts!.warnings} warnings`} aria-hidden="true">
                {total}
              </span>
            ) : null;
          })()}
          {decorations.git?.get(entry.path) && (
            <span className="tree-git" aria-hidden="true" title={gitWord(decorations.git.get(entry.path)!)}>
              {decorations.git.get(entry.path)}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
