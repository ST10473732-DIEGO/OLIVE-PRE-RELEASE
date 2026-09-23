import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Bell, ChevronDown, Command, Cpu, Menu, MonitorSmartphone } from "lucide-react";
import { RailCore } from "../components/RailCore";
import { MenuButton } from "../components/MenuButton";
import { featureById, navigationRows } from "../navigation/features";
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

// V2 §13: one 34 px title bar shared by every space. Identity, where you are,
// the command centre, and a status cluster that only reports real state.
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
  connect: StatusSummary;
  /** Items that need the person: approvals and due reminders. */
  attention: number;
  developer: boolean;
  /** Hide the model/Connect cluster (Studio uses the room for run controls). */
  compactStatus: boolean;
  setContextSlot: (element: HTMLElement | null) => void;
  setActionsSlot: (element: HTMLElement | null) => void;
}) {
  const feature = featureById(route);
  const spaces = navigationRows(developer);
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
      <button className="tb-brand" aria-label="OLIVE Home" title="Home" onClick={() => navigate("home")}>
        <OliveMark />
        <span className="tb-wordmark">OLIVE</span>
      </button>
      <span className="tb-sep" aria-hidden="true" />
      {navHidden ? (
        <MenuButton
          label={`Space: ${feature?.label || "Home"}. Switch space`}
          className="tb-space"
          title="Switch space"
          items={spaces.map((space) => ({
            id: space.id,
            label: space.label,
            icon: <space.icon size={14} aria-hidden="true" />,
            current: space.id === route,
            onSelect: () => navigate(space.id),
          }))}
        >
          <span>{feature?.label || "Home"}</span>
          <ChevronDown size={13} aria-hidden="true" />
        </MenuButton>
      ) : (
        <span className="tb-space static">{feature?.label || "Home"}</span>
      )}
      <span className="tb-context" ref={setContextSlot}>
        {context && <span className="tb-crumb" title={context}>{context}</span>}
      </span>
      <span className="tb-grow" />
      <button className="tb-command" aria-label="Find anything" title="Search or run a command (Ctrl+Shift+P)" onClick={openPalette}>
        <Command size={13} aria-hidden="true" />
        <span className="tb-command-text">Search or run a command</span>
        <kbd className="kbd">Ctrl+Shift+P</kbd>
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
