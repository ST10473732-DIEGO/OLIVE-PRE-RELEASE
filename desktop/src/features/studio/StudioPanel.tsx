import { useRef, type ReactNode } from "react";
import { ChevronDown, ChevronUp, Maximize2, Minimize2, X } from "lucide-react";
import { PANEL_LABELS, type PanelTab } from "./studioModel";

// Studio V2 §8: the bottom panel. Uppercase tabs with a blue underline, counts
// as badges, tab-specific actions on the right, then Maximise and Close. It is
// collapsible (Ctrl+J), resizable from its top edge (mouse or keyboard) and
// the tab strip is a proper tablist with arrow-key navigation.
export function StudioPanel({
  tabs,
  active,
  select,
  open,
  close,
  height,
  setHeight,
  maximised,
  setMaximised,
  counts,
  actions,
  children,
}: {
  tabs: PanelTab[];
  active: PanelTab;
  select: (tab: PanelTab) => void;
  open: boolean;
  close: () => void;
  height: number;
  setHeight: (value: number) => void;
  maximised: boolean;
  setMaximised: (value: boolean) => void;
  counts: Partial<Record<PanelTab, { count: number; tone?: "error" | "warning" | "info"; spoken: string }>>;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const list = useRef<HTMLDivElement>(null);
  const startDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startY = event.clientY;
    const start = height;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const moveTo = (e: PointerEvent) => setHeight(start + (startY - e.clientY));
    const stop = () => {
      target.removeEventListener("pointermove", moveTo);
      target.removeEventListener("pointerup", stop);
    };
    target.addEventListener("pointermove", moveTo);
    target.addEventListener("pointerup", stop);
  };
  return (
    <section
      className="studio-dock studio-panel"
      role="region"
      aria-label="Workspace tools"
      hidden={!open}
      data-maximised={maximised || undefined}
      style={maximised ? undefined : { height }}
    >
      <div
        className="panel-resizer"
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize panel"
        aria-valuenow={Math.round(height)}
        tabIndex={0}
        onPointerDown={startDrag}
        onKeyDown={(event) => {
          if (event.key === "ArrowUp") {
            event.preventDefault();
            setHeight(height + 16);
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            setHeight(height - 16);
          }
        }}
      />
      <div className="panel-head">
        <div className="panel-tabs" role="tablist" aria-label="Panel" ref={list}>
          {tabs.map((tab, index) => {
            const count = counts[tab];
            return (
              <button
                key={tab}
                role="tab"
                id={`panel-tab-${tab}`}
                aria-selected={active === tab}
                aria-controls={`panel-body-${tab}`}
                aria-label={count && count.count ? `${PANEL_LABELS[tab]}, ${count.spoken}` : PANEL_LABELS[tab]}
                tabIndex={active === tab ? 0 : -1}
                className="panel-tab"
                onClick={() => select(tab)}
                onKeyDown={(event) => {
                  const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
                  if (!step && event.key !== "Home" && event.key !== "End") return;
                  event.preventDefault();
                  const next =
                    event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + step + tabs.length) % tabs.length;
                  select(tabs[next]);
                  list.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
                }}
              >
                {PANEL_LABELS[tab]}
                {count && count.count > 0 && (
                  <span className="count" data-tone={count.tone || "neutral"} aria-hidden="true">
                    {count.count > 99 ? "99+" : count.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <div className="panel-actions">
          {actions}
          <button
            className="icon-button"
            aria-label={maximised ? "Restore panel size" : "Maximise panel"}
            title={maximised ? "Restore panel size" : "Maximise panel"}
            onClick={() => setMaximised(!maximised)}
          >
            {maximised ? <Minimize2 size={14} aria-hidden="true" /> : <Maximize2 size={14} aria-hidden="true" />}
          </button>
          <button className="icon-button" aria-label="Close panel" title="Close panel (Ctrl+J)" onClick={close}>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="panel-body" id={`panel-body-${active}`} role="tabpanel" aria-labelledby={`panel-tab-${active}`}>
        {children}
      </div>
    </section>
  );
}

/** A collapsed-panel affordance kept in the status bar when the panel is closed. */
export function PanelToggle({ open, toggle }: { open: boolean; toggle: () => void }) {
  return (
    <button className="status-item" aria-label={open ? "Hide panel" : "Show panel"} title="Toggle panel (Ctrl+J)" onClick={toggle}>
      {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronUp size={12} aria-hidden="true" />}
    </button>
  );
}
