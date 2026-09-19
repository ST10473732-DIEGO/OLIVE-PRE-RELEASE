import { useEffect, useRef } from "react";
import { PanelLeftClose, PanelLeftOpen, Command, X } from "lucide-react";
import { RailCore } from "../components/RailCore";
import {
  categories,
  navigationRows,
  type Feature,
} from "../navigation/features";

// A restrained, labelled navigation pane. Labels stay readable at normal desktop
// widths; compact mode is the user's choice, not something a route change does.
// On narrow windows the same pane becomes a dismissable overlay.
export function Navigation({
  route,
  navigate,
  activity,
  state,
  detail,
  approvals,
  compact,
  setCompact,
  developer,
  overlay,
  closeOverlay,
  openPalette,
  openActivity,
}: {
  route: string;
  navigate: (id: string) => void;
  /** Raw runtime activity; drives the Core animation. */
  activity: string;
  /** Friendly label shown to the person. */
  state: string;
  detail: string;
  approvals: number;
  compact: boolean;
  setCompact: (value: boolean) => void;
  /** Developer Mode adds the Diagnostics shortcut. */
  developer: boolean;
  overlay: boolean;
  closeOverlay: () => void;
  openPalette: () => void;
  openActivity: () => void;
}) {
  const pane = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!overlay) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeOverlay();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [overlay, closeOverlay]);
  const rows = navigationRows(developer);
  const grouped = categories
    .map((category) => ({
      category,
      // Settings is pinned in the foot so it never needs scrolling to reach.
      items: rows.filter(
        (f) => f.category === category && f.id !== "home" && f.id !== "settings",
      ),
    }))
    .filter((group) => group.items.length > 0);
  const row = (feature: Feature) => {
    const selected = route === feature.id;
    return (
      <button
        key={feature.id}
        className={`nav-row ${selected ? "selected" : ""}`}
        aria-current={selected ? "page" : undefined}
        // Compact mode hides the text, so name the row explicitly: the feature
        // is identified the same way at every width, never only by hovering.
        aria-label={feature.label}
        title={compact ? `${feature.label} — ${feature.description}` : feature.description}
        onClick={() => navigate(feature.id)}
      >
        <feature.icon size={17} aria-hidden="true" />
        <span className="nav-label">{feature.label}</span>
      </button>
    );
  };
  return (
    <>
      {overlay && <div className="nav-scrim" onClick={closeOverlay} aria-hidden="true" />}
      <nav
        ref={pane}
        className={`navigation ${compact ? "compact" : ""} ${overlay ? "nav-overlay" : ""}`}
        aria-label="Main navigation"
        data-state={activity}
      >
        <div className="nav-head">
          <button
            className="nav-identity activity-button"
            aria-label="OLIVE activity"
            title={`${state}${detail ? ` · ${detail}` : ""} — open activity`}
            onClick={openActivity}
          >
            <RailCore state={activity} />
            <span className="nav-identity-text">
              <strong>OLIVE</strong>
              <span className="nav-state" data-state={state}>
                {state}
                {detail ? ` · ${detail}` : ""}
                {approvals > 0 ? ` · ${approvals}` : ""}
              </span>
            </span>
          </button>
          {overlay && (
            <button className="icon-button" aria-label="Close navigation" onClick={closeOverlay}>
              <X size={18} />
            </button>
          )}
        </div>
        <div className="nav-scroll">
          {row(rows.find((f) => f.id === "home")!)}
          {grouped.map((group) => (
            <div className="nav-group" key={group.category}>
              <span className="nav-group-label">{group.category}</span>
              {group.items.map(row)}
            </div>
          ))}
        </div>
        <div className="nav-foot">
          {row(rows.find((f) => f.id === "settings")!)}
          <button className="nav-row" onClick={openPalette} title="Find anything · Ctrl+Shift+P">
            <Command size={17} aria-hidden="true" />
            <span className="nav-label">Find anything</span>
            <kbd className="kbd nav-kbd">Ctrl+Shift+P</kbd>
          </button>
          {!overlay && (
            <button
              className="nav-row nav-compact-toggle"
              aria-pressed={compact}
              aria-label={compact ? "Expand navigation" : "Collapse navigation"}
              title={compact ? "Expand navigation" : "Collapse navigation"}
              onClick={() => setCompact(!compact)}
            >
              {compact ? (
                <PanelLeftOpen size={17} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={17} aria-hidden="true" />
              )}
              <span className="nav-label">Collapse</span>
            </button>
          )}
        </div>
      </nav>
    </>
  );
}
