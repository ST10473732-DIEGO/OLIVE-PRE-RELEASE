import { useEffect, useRef } from "react";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import {
  categories,
  navigationRows,
  type Feature,
} from "../navigation/features";

/** Where the navigation pane sits for a window width and space (V2 §15).
 *  "expanded" 216 px, "rail" 48 px icons, "hidden" (overlay on demand). */
export type NavMode = "expanded" | "rail" | "hidden";
export function navModeFor(width: number, route: string, userCompact: boolean): NavMode {
  if (route === "studio") return width >= 1600 ? "rail" : "hidden";
  if (width < 1100) return "hidden";
  if (width < 1280) return "rail";
  return userCompact ? "rail" : "expanded";
}

// V2 navigation: 216 px, grouped, 30 px rows, olive 2 px active indicator and
// badges for attention. Identity and status live in the title bar. The pane
// collapses to a 48 px icon rail; on narrow windows and in Studio it is an
// overlay opened from the title bar.
export function Navigation({
  route,
  navigate,
  badges,
  compact,
  setCompact,
  canExpand,
  developer,
  overlay,
  closeOverlay,
}: {
  route: string;
  navigate: (id: string) => void;
  /** Attention counts per feature id (approvals, due reminders). */
  badges: Record<string, number>;
  compact: boolean;
  setCompact: (value: boolean) => void;
  /** False when the window is too narrow for the expanded pane. */
  canExpand: boolean;
  /** Developer Mode adds the Diagnostics shortcut. */
  developer: boolean;
  overlay: boolean;
  closeOverlay: () => void;
}) {
  const pane = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!overlay) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeOverlay();
    };
    document.addEventListener("keydown", onKey);
    pane.current?.querySelector<HTMLElement>('[aria-current="page"], .nav-row')?.focus();
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
  const showCompact = compact && !overlay;
  const row = (feature: Feature) => {
    const selected = route === feature.id;
    const badge = badges[feature.id] || 0;
    return (
      <button
        key={feature.id}
        className={`nav-row ${selected ? "selected" : ""}`}
        aria-current={selected ? "page" : undefined}
        // Compact mode hides the text, so name the row explicitly: the feature
        // is identified the same way at every width, never only by hovering.
        aria-label={feature.label}
        aria-description={badge ? `${badge} need${badge === 1 ? "s" : ""} attention` : undefined}
        title={showCompact ? `${feature.label} — ${feature.description}` : feature.description}
        onClick={() => navigate(feature.id)}
      >
        <feature.icon size={16} aria-hidden="true" />
        <span className="nav-label">{feature.label}</span>
        {badge > 0 && (
          <span className="count" data-tone={feature.id === "devices" || feature.id === "reminders" ? "warning" : undefined} aria-hidden="true">
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
        {overlay && (
          <div className="nav-head">
            <span className="eyebrow">Spaces</span>
            <button className="icon-button" aria-label="Close navigation" onClick={closeOverlay}>
              <X size={16} />
            </button>
          </div>
        )}
        <div className="nav-scroll">
          {row(rows.find((f) => f.id === "home")!)}
          {grouped.map((group) => (
            <div className="nav-group" key={group.category} role="group" aria-label={group.category}>
              <span className="nav-group-label" aria-hidden="true">{group.category}</span>
              {group.items.map(row)}
            </div>
          ))}
        </div>
        <div className="nav-foot">
          {row(rows.find((f) => f.id === "settings")!)}
          {!overlay && canExpand && (
            <button
              className="nav-row nav-compact-toggle"
              aria-pressed={compact}
              aria-label={compact ? "Expand navigation" : "Collapse navigation"}
              title={compact ? "Expand navigation" : "Collapse navigation"}
              onClick={() => setCompact(!compact)}
            >
              {compact ? (
                <PanelLeftOpen size={16} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={16} aria-hidden="true" />
              )}
              <span className="nav-label">Collapse</span>
            </button>
          )}
        </div>
      </nav>
    </>
  );
}
