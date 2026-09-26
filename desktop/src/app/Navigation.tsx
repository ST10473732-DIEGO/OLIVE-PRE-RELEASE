import { useEffect, useLayoutEffect, useRef } from "react";
import { Activity, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { footSpaces, spaceOf, spaces, type Space } from "../navigation/features";
import { OliveMark } from "./TitleBar";
import { RailCore } from "../components/RailCore";

/** Where the navigation pane sits for a window width and space.
 *  "expanded" 232 px, "rail" 64 px icons, "hidden" (overlay on demand). */
export type NavMode = "expanded" | "rail" | "hidden";
export function navModeFor(width: number, route: string, userCompact: boolean): NavMode {
  if (route === "studio") return width >= 1600 ? "rail" : "hidden";
  if (width < 1100) return "hidden";
  if (width < 1280) return "rail";
  return userCompact ? "rail" : "expanded";
}

// Grove navigation: the brand, seven spaces, and Devices and Settings pinned to
// the foot. One highlight glides to the current space; views within a space
// (Plan's Calendar, Tasks and Reminders, for example) switch in the title bar.
export function Navigation({
  route,
  openSpace,
  badges,
  compact,
  setCompact,
  canExpand,
  developer,
  overlay,
  closeOverlay,
  navigate,
  activity = "Ready",
}: {
  /** Raw runtime activity; drives the Core in the brand. */
  activity?: string;
  route: string;
  openSpace: (space: string) => void;
  /** Attention counts per route id (approvals, due reminders). */
  badges: Record<string, number>;
  compact: boolean;
  setCompact: (value: boolean) => void;
  /** False when the window is too narrow for the expanded pane. */
  canExpand: boolean;
  /** Developer Mode adds the Diagnostics shortcut. */
  developer: boolean;
  overlay: boolean;
  closeOverlay: () => void;
  navigate: (id: string) => void;
}) {
  const pane = useRef<HTMLElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const current = spaceOf(route).id;
  useEffect(() => {
    if (!overlay) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeOverlay();
    };
    document.addEventListener("keydown", onKey);
    pane.current?.querySelector<HTMLElement>('[aria-current="page"], .nav-row')?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [overlay, closeOverlay]);
  // The highlight is one element that moves; it never re-renders per row, so
  // switching spaces is a single transform on the compositor.
  useLayoutEffect(() => {
    const place = () => {
      const host = pane.current, marker = pill.current;
      const active = host?.querySelector<HTMLElement>('.nav-row[aria-current="page"]');
      if (!host || !marker) return;
      if (!active) { marker.style.opacity = "0"; return; }
      marker.style.opacity = "1";
      marker.style.transform = `translateY(${active.offsetTop}px)`;
      marker.style.height = `${active.offsetHeight}px`;
    };
    place();
    const first = pill.current;
    if (first?.dataset.placed !== "true" && first) {
      requestAnimationFrame(() => requestAnimationFrame(() => { first.dataset.placed = "true"; }));
    }
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [current, compact, overlay, developer]);
  const showCompact = compact && !overlay;
  const count = (space: Space) =>
    [...space.routes, ...(space.also || [])].reduce((sum, id) => sum + (badges[id] || 0), 0);
  const row = (space: Space) => {
    const selected = current === space.id;
    const badge = count(space);
    const views = space.routes.length > 1 ? ` — ${space.routes.length} views` : "";
    return (
      <button
        key={space.id}
        className={`nav-row ${selected ? "selected" : ""}`}
        aria-current={selected ? "page" : undefined}
        aria-label={space.label}
        aria-description={badge ? `${badge} need${badge === 1 ? "s" : ""} attention` : undefined}
        title={showCompact ? `${space.label}${views}` : undefined}
        onClick={() => openSpace(space.id)}
      >
        <space.icon size={18} aria-hidden="true" />
        <span className="nav-label">{space.label}</span>
        {badge > 0 && (
          <span className="count" data-tone={space.id === "devices" || space.id === "plan" ? "warning" : undefined} aria-hidden="true">
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </button>
    );
  };
  return (
    <>
      {overlay && <div className="nav-scrim" onClick={closeOverlay} aria-hidden="true" />}
      <nav
        ref={pane}
        className={`navigation ${showCompact ? "compact" : ""} ${overlay ? "nav-overlay" : ""}`}
        aria-label="Main navigation"
      >
        <span ref={pill} className="nav-pill" aria-hidden="true" />
        <div className="nav-head">
          <button className="nav-brand" aria-label="OLIVE Home" title="Home" onClick={() => openSpace("home")} tabIndex={-1}>
            {overlay ? <OliveMark size={22} /> : <RailCore state={activity} />}
            <span className="nav-wordmark">OLIVE</span>
          </button>
          {overlay && (
            <button className="icon-button" aria-label="Close navigation" onClick={closeOverlay}>
              <X size={16} />
            </button>
          )}
        </div>
        <div className="nav-scroll">{spaces.map(row)}</div>
        <div className="nav-foot">
          {footSpaces.map(row)}
          {developer && (
            <button
              className="nav-row"
              aria-label="Diagnostics"
              title={showCompact ? "Diagnostics" : undefined}
              onClick={() => navigate("diagnostics")}
            >
              <Activity size={18} aria-hidden="true" />
              <span className="nav-label">Diagnostics</span>
            </button>
          )}
          {!overlay && canExpand && (
            <button
              className="nav-row nav-compact-toggle"
              aria-pressed={compact}
              aria-label={compact ? "Expand navigation" : "Collapse navigation"}
              title={compact ? "Expand navigation (Ctrl+Shift+O)" : "Collapse navigation (Ctrl+Shift+O)"}
              onClick={() => setCompact(!compact)}
            >
              {compact ? (
                <PanelLeftOpen size={18} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={18} aria-hidden="true" />
              )}
              <span className="nav-label">Collapse</span>
            </button>
          )}
        </div>
      </nav>
    </>
  );
}
