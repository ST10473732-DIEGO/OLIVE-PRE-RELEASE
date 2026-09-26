import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Bell, ChevronDown, Cpu, Menu, MonitorSmartphone, Moon, Search, Sun } from "lucide-react";
import { RailCore } from "../components/RailCore";
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

/** The olive mark: the app identity, drawn in CSS (no image asset). */
export function OliveMark({ size = 14 }: { size?: number }) {
  return <span className="olive-mark" style={{ width: size, height: size + 1 }} aria-hidden="true" />;
}

// Grove title bar, shared by every space: where you are (with the space's views
// as a switcher), the command centre, and a status cluster that only reports
// real state. The brand lives in the navigation unless the pane is hidden.
// Window controls stay with the operating system's own frame (see
// docs/OLIVE_DESIGN_V2_IMPLEMENTATION.md, "Window controls").
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
  connect,
  attention,
  developer,
  compactStatus,
  setContextSlot,
  setActionsSlot,
  openSpace,
  theme,
  toggleTheme,
}: {
  openSpace: (space: string) => void;
  theme: string;
  toggleTheme: () => void;
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
  connect: StatusSummary;
  /** Items that need the person: approvals and due reminders. */
  attention: number;
  developer: boolean;
  /** Hide the model/Connect cluster (Studio uses the room for run controls). */
  compactStatus: boolean;
  setContextSlot: (element: HTMLElement | null) => void;
  setActionsSlot: (element: HTMLElement | null) => void;
}) {
  const space = spaceOf(route);
  const all = developer ? [...spaces, ...footSpaces] : [...spaces, ...footSpaces];
  const activityLabel =
    runtime.tone === "attention" || runtime.tone === "error" || runtime.tone === "working"
      ? runtime.label
      : "Idle";
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
          <OliveMark />
          <span className="tb-wordmark">OLIVE</span>
        </button>
      )}
      {navHidden ? (
        <MenuButton
          label={`Space: ${space.label}. Switch space`}
          className="tb-space"
          title="Switch space"
          items={all.map((item) => ({
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
      {space.routes.length > 1 && (
        <span className="tb-views" role="group" aria-label={`${space.label} views`}>
          {space.routes.map((id) => (
            <button key={id} aria-pressed={route === id} onClick={() => navigate(id)}>
              {featureById(id)?.label}
            </button>
          ))}
        </span>
      )}
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
      <button
        className="tb-status tb-activity activity-button"
        aria-label="OLIVE activity"
        data-tone={runtime.tone}
        title={`${runtime.label}${runtime.detail ? ` · ${runtime.detail}` : ""} — open activity`}
        onClick={openActivity}
      >
        <RailCore state={activity} />
        <span className="tb-status-text" aria-hidden="true">{activityLabel}</span>
      </button>
      {!compactStatus && (
        <>
          <button
            className="tb-status"
            data-tone={model.tone}
            aria-label={`Model: ${model.label}`}
            title={`${model.full} Open Settings › Models.`}
            onClick={() => navigate("settings")}
          >
            <Cpu size={13} aria-hidden="true" />
            <span className="tb-status-text">{model.label}</span>
          </button>
          <button
            className="tb-status"
            data-tone={connect.tone}
            aria-label={`Connect: ${connect.label}`}
            title={`${connect.full} Open Devices.`}
            onClick={() => navigate("devices")}
          >
            <MonitorSmartphone size={13} aria-hidden="true" />
            <span className="tb-status-text">{connect.label}</span>
          </button>
        </>
      )}
      <button
        className="tb-icon tb-theme"
        aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}
        title="Switch theme"
        onClick={toggleTheme}
      >
        {theme === "dark" ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
      </button>
      <button
        className="tb-icon tb-bell"
        aria-label={attention ? `Notifications: ${attention} need your attention` : "Notifications: nothing needs you"}
        title="Approvals and reminders"
        onClick={openActivity}
      >
        <Bell size={15} aria-hidden="true" />
        {attention > 0 && (
          <span className="count" data-tone="warning" aria-hidden="true">
            {attention > 99 ? "99+" : attention}
          </span>
        )}
      </button>
    </header>
  );
}
