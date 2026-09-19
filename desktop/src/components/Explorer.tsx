import { useState, useRef } from "react";
import { ChevronDown, ChevronRight, FileCode2, Folder } from "lucide-react";

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
export function Explorer({
  entries,
  active,
  open,
}: {
  entries: Entry[];
  active: string;
  open: (path: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(new Set<string>());
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
          // Indentation stops growing after six levels so deep paths stay readable;
          // the title carries the full path and the explorer is resizable.
          style={{
            paddingLeft:
              8 + Math.min(entry.path.split("/").length - 1, 6) * 14,
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
                <ChevronRight size={12} />
              ) : (
                <ChevronDown size={12} />
              )}
              <Folder size={15} />
            </>
          ) : (
            <FileCode2 size={15} />
          )}
          <span>{entry.path.split("/").pop()}</span>
        </button>
      ))}
    </div>
  );
}
