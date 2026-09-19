import { useRef, type ReactNode } from "react";
export function ActionMenu({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDetailsElement>(null);
  return (
    <details
      ref={root}
      className="workspace-menu"
      onKeyDown={(e) => {
        if (e.key === "Escape" && root.current) {
          root.current.open = false;
          root.current.querySelector("summary")?.focus();
          e.stopPropagation();
        }
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget) && root.current)
          root.current.open = false;
      }}
    >
      <summary>Workspace actions</summary>
      <div className="workspace-menu-items">{children}</div>
    </details>
  );
}
