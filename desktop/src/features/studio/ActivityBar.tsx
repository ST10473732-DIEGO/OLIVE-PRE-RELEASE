import { useRef, type ReactNode } from "react";
import { Bug, FlaskConical, Files, GitBranch, Search, Settings } from "lucide-react";
import { ACTIVITY_ITEMS, REMOTE_UNAVAILABLE, type StudioView } from "./studioModel";

const ICONS: Record<StudioView, typeof Files> = {
  explorer: Files,
  search: Search,
  scm: GitBranch,
  debug: Bug,
  testing: FlaskConical,
};

// Studio V2 §5: a 44 px vertical toolbar with roving tabindex. The active
// item has a 2 px blue indicator; clicking it again toggles the sidebar.
// Views that do not exist for a remote workspace are disabled and say why.
export function ActivityBar({
  view,
  sidebarOpen,
  select,
  availability,
  badges,
  openSettings,
}: {
  view: StudioView;
  sidebarOpen: boolean;
  select: (view: StudioView) => void;
  availability: Record<StudioView, boolean>;
  badges: Partial<Record<StudioView, { count?: number; text?: string; tone?: "error" | "warning" | "info"; spoken: string }>>;
  openSettings: () => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const move = (event: React.KeyboardEvent, index: number) => {
    const buttons = [...(bar.current?.querySelectorAll<HTMLButtonElement>("button") || [])];
    let next = -1;
    if (event.key === "ArrowDown") next = (index + 1) % buttons.length;
    if (event.key === "ArrowUp") next = (index - 1 + buttons.length) % buttons.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = buttons.length - 1;
    if (next >= 0) {
      event.preventDefault();
      buttons[next]?.focus();
    }
  };
  const item = (
    id: string,
    label: string,
    icon: ReactNode,
    index: number,
    onClick: () => void,
    options: { current?: boolean; tabStop?: boolean; disabled?: boolean; badge?: (typeof badges)[StudioView]; keys?: string } = {},
  ) => (
    <button
      key={id}
      className="activity-item"
      aria-label={options.badge ? `${label}, ${options.badge.spoken}` : label}
      aria-pressed={options.current}
      aria-disabled={options.disabled || undefined}
      title={options.disabled ? `${label} · ${REMOTE_UNAVAILABLE}` : `${label}${options.keys ? ` (${options.keys})` : ""}`}
      tabIndex={options.tabStop ? 0 : -1}
      data-current={options.current || undefined}
      onKeyDown={(event) => move(event, index)}
      onClick={() => {
        if (!options.disabled) onClick();
      }}
    >
      {icon}
      {options.badge && (options.badge.count || options.badge.text) ? (
        <span className="activity-badge count" data-tone={options.badge.tone} aria-hidden="true">
          {options.badge.text || (options.badge.count! > 99 ? "99+" : options.badge.count)}
        </span>
      ) : null}
    </button>
  );
  return (
    <div className="activity-bar" role="toolbar" aria-orientation="vertical" aria-label="Studio views" ref={bar}>
      <div className="activity-top">
        {ACTIVITY_ITEMS.map((activity, index) => {
          const Icon = ICONS[activity.id];
          return item(
            activity.id,
            activity.label,
            <Icon size={20} strokeWidth={1.5} aria-hidden="true" />,
            index,
            () => select(activity.id),
            {
              current: sidebarOpen && view === activity.id,
              tabStop: view === activity.id,
              disabled: !availability[activity.id],
              badge: badges[activity.id],
              keys: activity.keys,
            },
          );
        })}
      </div>
      <div className="activity-bottom">
        {item("settings", "Studio settings", <Settings size={20} strokeWidth={1.5} aria-hidden="true" />, ACTIVITY_ITEMS.length, openSettings)}
      </div>
    </div>
  );
}
