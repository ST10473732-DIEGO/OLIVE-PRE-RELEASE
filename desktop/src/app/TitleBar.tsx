import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Bell, ChevronDown, ChevronRight, Menu, Moon, Search, Sun } from "lucide-react";
import { RailCore } from "../components/RailCore";
import { OliveLogo } from "../components/OliveLogo";
import { MenuButton } from "../components/MenuButton";
import { featureById, footSpaces, spaceOf, spaces } from "../navigation/features";
import type { RuntimeState, StatusSummary } from "../services/runtimeState";

// Workspaces that need title-bar controls (Studio: workspace switcher, Local /
// Remote, run controls) portal them into these slots. A hidden workspace
// renders nothing into them, so the bar only ever shows the visible space.
export interface TitleBarSlots {
  context: HTMLElement | null;
  actions: HTMLElement | null;
}
export const TitleBarSlotContext = createContext<TitleBarSlots>({ context: null, actions: null });
export function TitleBarPortal({ slot, children }: { slot: keyof TitleBarSlots; children: ReactNode }) {
  const target = useContext(TitleBarSlotContext)[slot];
  return target ? createPortal(children, target) : null;
}

/** The olive mark: the app identity (the same drawing as the app icon). */
export function OliveMark({ size = 16 }: { size?: number }) {
  return <OliveLogo className="olive-mark" size={size} />;
}

// Grove title bar: where you are (Space › view), the centred command field,
// one status chip for the local AI, the theme toggle and Activity. The living
// Core sits in the navigation brand; when the pane is hidden it moves here.
export function TitleBar({
  route,
  navigate,
  navHidden,
  openNavigation,
  context,
  openPalette,
  activity,
  runtime,
  openActivity,
  model,
  attention,
  compactStatus,
  setContextSlot,
  setActionsSlot,
  openSpace,
  theme,
  toggleTheme,
}: {
  route: string;
  navigate: (id: string) => void;
  /** The navigation pane is not on screen (narrow window or Studio). */
  navHidden: boolean;
  openNavigation: () => void;
  /** Context crumb: conversation title, workspace, category. */
  context?: string;
  openPalette: () => void;
  /** Raw runtime activity; drives the Core. */
  activity: string;
  runtime: RuntimeState;
  openActivity: () => void;
  model: StatusSummary;
  /** Items that need the person: approvals and due reminders. */
  attention: number;
  /** Hide the model chip (Studio uses the room for run controls). */
  compactStatus: boolean;
  setContextSlot: (element: HTMLElement | null) => void;
  setActionsSlot: (element: HTMLElement | null) => void;
  openSpace: (space: string) => void;
  theme: string;
  toggleTheme: () => void;
  /** Accepted for call-site compatibility; the bar no longer shows them. */
  connect?: StatusSummary;
  developer?: boolean;
}) {
  const space = spaceOf(route);
  const view = space.routes.length > 1 ? (featureById(route)?.view ?? featureById(route)?.label) : undefined;
  const working = runtime.tone === "working";
  return (
    <header className="titlebar" data-route={route}>
      {navHidden && (
        <button
          className="tb-icon"
          aria-label="Open navigation"
          title="Open navigation (Ctrl+Shift+O)"
          onClick={openNavigation}
        >
          <Menu size={16} aria-hidden="true" />
        </button>
      )}
      {navHidden && (
        <button className="tb-brand" aria-label="OLIVE Home" title="Home" onClick={() => openSpace("home")}>
          <RailCore state={activity} />
          <span className="tb-wordmark">OLIVE</span>
        </button>
      )}
      <nav className="tb-crumb-trail" aria-label="Location">
        {navHidden ? (
          <MenuButton
            label={`Space: ${space.label}. Switch space`}
            className="tb-space"
            title="Switch space"
            items={[...spaces, ...footSpaces].map((item) => ({
              id: item.id,
              label: item.label,
              icon: <item.icon size={14} aria-hidden="true" />,
              current: item.id === space.id,
              onSelect: () => openSpace(item.id),
            }))}
          >
            <span>{space.label}</span>
            <ChevronDown size={13} aria-hidden="true" />
          </MenuButton>
        ) : (
          <span className="tb-space static">{space.label}</span>
        )}
        {view && route !== "studio" && (
          <>
            <ChevronRight size={14} className="tb-crumb-sep" aria-hidden="true" />
            <span className="tb-view">{view}</span>
          </>
        )}
        {route === "studio" && (
          <span className="tb-views" role="group" aria-label={`${space.label} views`}>
            {space.routes.map((id) => (
              <button key={id} aria-pressed={route === id} onClick={() => navigate(id)}>
                {featureById(id)?.label}
              </button>
            ))}
          </span>
        )}
      </nav>
      <span className="tb-context" ref={setContextSlot}>
        {context && <span className="tb-crumb" title={context}>{context}</span>}
      </span>
      <span className="tb-grow" />
      <button className="tb-command" aria-label="Find anything" title="Search, ask OLIVE or run a command (Ctrl+K)" onClick={openPalette}>
        <Search size={14} aria-hidden="true" />
        <span className="tb-command-text">Search or ask OLIVE</span>
        <kbd className="kbd">Ctrl K</kbd>
      </button>
      <span className="tb-grow" />
      <span className="tb-actions" ref={setActionsSlot} />
      {!compactStatus && (
        <button
          className="tb-status tb-model"
          data-tone={model.tone}
          aria-label={`Model: ${model.label}`}
          title={`${model.full} Open Settings › Models.`}
          onClick={() => navigate("settings")}
        >
          <span className="tb-live" data-busy={working || undefined} aria-hidden="true" />
          <span className="tb-status-text">{working ? `${model.label.split(" ")[0]} · working` : model.label.replace(/ ready$/, " · ready")}</span>
        </button>
      )}
      <button
        className="tb-icon tb-theme"
        aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}
        title="Switch theme (Ctrl+Shift+L)"
        onClick={toggleTheme}
      >
        {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
      </button>
      <button
        className="tb-icon tb-bell"
        aria-label="OLIVE activity"
        aria-description={attention ? `Notifications: ${attention} need your attention` : "Notifications: nothing needs you"}
        title={`${runtime.label}${runtime.detail ? ` · ${runtime.detail}` : ""} — activity and approvals`}
        onClick={openActivity}
      >
        <Bell size={16} aria-hidden="true" />
        {attention > 0 && <span className="tb-bell-dot" aria-hidden="true" />}
      </button>
    </header>
  );
}
