import {
  responseAfter,
  type ConversationAnchor,
} from "../../services/conversation";
import { lazy, Suspense, useEffect, useState } from "react";
import { call, type Chat } from "../../services/api";
import { Markdown } from "../../components/Markdown";
import { useResource } from "../../services/useResource";
import {
  WorkspacePage,
  Details,
  Main,
  Panel,
  EmptyState,
  Pill,
  Facts,
} from "../../components/WorkspacePage";
import { GrowingComposer } from "../../components/GrowingComposer";
import {
  MonitorCog,
  Send,
  OctagonX,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  Settings2,
  Workflow,
  Sparkles,
  AlertTriangle,
  Wrench,
} from "lucide-react";
const phaseTone = (status: string): "success" | "error" | "warning" | "accent" | undefined =>
  /completed|done|passed|verified/i.test(status)
    ? "success"
    : /fail|error|blocked|denied/i.test(status)
      ? "error"
      : /pause|wait|approval|pending/i.test(status)
        ? "warning"
        : /running|active|in_progress/i.test(status)
          ? "accent"
          : undefined;
import type { DesktopState, Operation } from "./types";
const Inspector = lazy(() => import("./Inspector"));
const ApplicationTools = lazy(() => import("./ApplicationTools"));
const BrowserTools = lazy(() => import("./BrowserTools"));
const VisualTools = lazy(() => import("./VisualTools"));
export default function Desktop({
  submit,
  busy,
  report,
  settings,
  chat,
}: {
  submit: (text: string) => Promise<void>;
  busy: boolean;
  report: (e: unknown) => void;
  settings: () => void;
  chat: Chat;
}) {
  const resource = useResource(
    () => call<DesktopState>("desktop.status", {}),
    ["desktop"],
  );
  const [objective, setObjective] = useState("");
  const [submittedAfter, setSubmittedAfter] = useState<ConversationAnchor>();
  const latest = chat.messages.at(-1);
  const response = responseAfter(chat, submittedAfter);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState<unknown>();
  useEffect(() => window.olive.subscribe(event => {
    if (event.topic === "request.failure" && String((event.data as { method?: string }).method).startsWith("desktop.")) setFailure(event.data);
  }), []);
  const [developer, setDeveloper] = useState(false);
  const [tab, setTab] = useState("Application inspector");
  const [visited, setVisited] = useState<string[]>(["Application inspector"]);
  const state = resource.data;
  const active = Boolean(state?.active || pending);
  const operation: Operation = async (fn, message) => {
    setFailure(undefined);
    setPending(true);
    setNotice("Waiting for the operation or its approval.");
    try {
      await fn();
      setNotice(message);
      await resource.refresh();
    } catch (e) {
      setNotice(
        "The operation did not complete. Inspect the observed state before retrying.",
      );
      report(e);
    } finally {
      setPending(false);
    }
  };
  const stop = async () => {
    try {
      await window.olive.stopControl();
      setNotice("Stop requested. Active input is being cancelled.");
      await resource.refresh();
    } catch (e) {
      report(e);
    }
  };
  const enabled = state?.available !== false && Boolean(state?.settings.enabled);
  const headerStatus = !state
    ? "Checking"
    : state.available === false ? "Unavailable" : state.stopped
      ? "Stopped"
      : !enabled
        ? "Disabled"
        : state.active
          ? "Active"
          : "Idle";
  const headerTone = !state ? "idle" : state.stopped ? "error" : !enabled ? "warning" : state.active ? "live" : "idle";
  const policy = (value: string) => value.replaceAll("_", " ");
  return (
    <WorkspacePage
      layout="fill"
      className="desktop"
      icon={<MonitorCog size={18} />}
      title="Desktop Control"
      description="Work with your applications and inspect what actually happened."
      status={headerStatus}
      statusTone={headerTone}
    >
      <Main className="desktop-main" label="Desktop Control workspace">
        <section className="objective-surface ws-composer desktop-composer" aria-label="Objective">
          <p className="ws-eyebrow">Objective</p>
          <GrowingComposer
            aria-label="Desktop objective"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="What would you like OLIVE to do?"
          />
          <div className="ws-composer-bottom desktop-composer-bottom">
            <button className="quiet" onClick={settings}>
              <Settings2 size={14} aria-hidden="true" />
              Control permissions
            </button>
            <span className="ws-composer-hint">
              {enabled ? "Every action is recorded and can be stopped at any time." : "Desktop Control is disabled; the objective stays a conversation."}
            </span>
            <button
              className="primary desktop-submit"
              disabled={busy || active || !objective.trim()}
              onClick={() => {
                setSubmittedAfter({ chatId: chat.id, after: latest?.id || "" });
                void submit(objective);
              }}
            >
              <Send size={15} aria-hidden="true" />
              Submit objective
            </button>
          </div>
        </section>
        <div className="desktop-notices">
          <p role="status" className="desktop-status">{notice}</p>
          {failure !== undefined && <Details title="Attachment error details" value={failure} />}
          {busy && (
            <p role="status" className="desktop-status">
              OLIVE is handling your objective. Stop Control remains available
              independently of model reasoning.
            </p>
          )}
          {resource.error && <p role="alert" className="desktop-alert">{resource.error}</p>}
          {!enabled && state && (
            <div className="callout ws-notice desktop-disabled" role="note" data-tone="warning">
              <AlertTriangle size={15} aria-hidden="true" />
              <p className="grow">
                {state.available === false ? state.unavailable_reason : <>Desktop Control is disabled. Enable it in Settings when you want
                OLIVE to interact with applications. Local conversation remains
                available.</>}
              </p>
              <button className="text-button" onClick={settings}>
                Open Settings
              </button>
            </div>
          )}
        </div>
        {response && (
          <Panel as="section" title="Response" icon={<Sparkles size={15} />} className="record-card desktop-response">
            <Markdown text={response.content} />
          </Panel>
        )}
        <div className="ws-grid main-side desktop-grid">
          <Panel
            title="Active workflow"
            sub={state?.session ? state.session.application || "Application workflow" : "Nothing is being controlled"}
            icon={<Workflow size={15} />}
            className="desktop-workflow"
            actions={state?.session ? <Pill tone={phaseTone(state.session.status)}>{state.session.status.replaceAll("_", " ")}</Pill> : undefined}
          >
            {state?.session ? (
              <section className="record-card desktop-session" aria-label="Application workflow">
                <h2 className="desktop-session-title">{state.session.application || "Application workflow"}</h2>
                <p className="desktop-session-task">{state.session.task}</p>
                <dl className="approval-summary ws-facts">
                  <dt>Current action</dt>
                  <dd>{state.session.current_action || "No action in progress"}</dd>
                  <dt>Verification</dt>
                  <dd>{state.session.verification || "No result verified yet"}</dd>
                </dl>
                {state.workflow_phases.length > 0 && (
                  <ol className="task-timeline ws-timeline">
                    {state.workflow_phases.slice(-12).map((phase, index) => (
                      <li key={index} data-state={phase.status}>
                        <div className="ws-step">
                          <strong>{phase.operation}</strong>
                          <Pill tone={phaseTone(phase.status)}>{phase.status}</Pill>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
                <Details
                  value={state.session.history}
                  title="Recorded action history"
                />
              </section>
            ) : (
              <EmptyState
                className="empty-workspace"
                compact
                icon={<MonitorCog size={22} />}
                title="No active application workflow"
              >
                Current application, action, permission and verification state will
                appear here. Opening this workspace does not inspect your desktop.
              </EmptyState>
            )}
          </Panel>
          <div className="desktop-side">
            <Panel title="Controls" sub="Available at any time, independent of the model" icon={<OctagonX size={15} />} headingLevel={3} tone={state?.stopped ? "error" : undefined}>
              <div className="desktop-controls">
                <button
                  className="danger-action desktop-stop"
                  onClick={() => void stop()}
                  aria-label="Emergency stop desktop control"
                >
                  <OctagonX size={15} aria-hidden="true" />
                  Stop Control
                </button>
                {state?.active && (
                  <div className="row desktop-pause">
                    <button
                      disabled={!state.can_pause}
                      onClick={() =>
                        void call("desktop.pause", {})
                          .then(() => resource.refresh())
                          .catch(report)
                      }
                    >
                      <Pause size={14} aria-hidden="true" />
                      Pause control
                    </button>
                    <button
                      disabled={!state.can_resume}
                      onClick={() =>
                        void call("desktop.resume", {})
                          .then(() => resource.refresh())
                          .catch(report)
                      }
                    >
                      <Play size={14} aria-hidden="true" />
                      Resume control
                    </button>
                  </div>
                )}
                {state?.stopped && (
                  <article className="record-card desktop-stopped">
                    <strong>Control stopped</strong>
                    <p>
                      Reset the stop latch only when you are ready to review new work.
                    </p>
                    <button
                      disabled={active}
                      onClick={() =>
                        void operation(
                          () => call("desktop.reset", {}),
                          "Stop latch reset. No action was replayed.",
                        )
                      }
                    >
                      <RotateCcw size={14} aria-hidden="true" />
                      Reset Stop
                    </button>
                  </article>
                )}
                {!state?.stopped && (
                  <p className="muted small desktop-controls-note">
                    Stop cancels active input immediately and latches until you reset it.
                  </p>
                )}
              </div>
            </Panel>
            <Panel title="Permissions" sub={enabled ? "Applied to every objective" : "Disabled in Settings"} icon={<ShieldCheck size={15} />} headingLevel={3}
              actions={<button className="quiet" onClick={settings}>Change</button>}
            >
              {state ? (
                <Facts
                  items={[
                    ["Desktop Control", <Pill tone={enabled ? "success" : "warning"}>{enabled ? "Enabled" : "Disabled"}</Pill>],
                    ["Screen observation", state.settings.screen_observation ? "Allowed" : "Off"],
                    ["Vision fallback", state.settings.vision_fallback ? "Allowed" : "Off"],
                    ["Keyboard", policy(state.settings.keyboard_policy || "deny")],
                    ["Mouse", policy(state.settings.mouse_policy || "deny")],
                    ["Provider", state.provider || "None"],
                  ]}
                />
              ) : (
                <p className="muted small">Reading the current policies…</p>
              )}
            </Panel>
          </div>
        </div>
        <details
          className="ws-disclosure desktop-developer"
          open={developer}
          onToggle={(e) => setDeveloper(e.currentTarget.open)}
        >
          <summary>
            <Wrench size={15} aria-hidden="true" />
            Developer Details
          </summary>
          <div className="ws-disclosure-body">
            <p className="muted">
              These tools use the same permissions and focus protection as natural
              objectives.
            </p>
            {developer && (
              <>
                <div className="category-tabs">
                  {[
                    "Application inspector",
                    "Applications and tools",
                    "Interactive browser",
                    "Visual inspection",
                  ].map((name) => (
                    <button
                      key={name}
                      className={tab === name ? "selected" : ""}
                      onClick={() => {
                        setTab(name);
                        setVisited((values) =>
                          values.includes(name) ? values : [...values, name],
                        );
                      }}
                    >
                      {name}
                    </button>
                  ))}
                </div>
                <Suspense fallback={<p>Opening controls…</p>}>
                  {visited.includes("Application inspector") && (
                    <div hidden={tab !== "Application inspector"}>
                      <Inspector
                        state={state}
                        operation={operation}
                        busy={active}
                        objective={objective}
                      />
                    </div>
                  )}
                  {visited.includes("Applications and tools") && (
                    <div hidden={tab !== "Applications and tools"}>
                      <ApplicationTools operation={operation} busy={active} />
                    </div>
                  )}
                  {visited.includes("Interactive browser") && (
                    <div hidden={tab !== "Interactive browser"}>
                      <BrowserTools operation={operation} busy={active} />
                    </div>
                  )}
                  {visited.includes("Visual inspection") && (
                    <div hidden={tab !== "Visual inspection"}>
                      <VisualTools
                        operation={operation}
                        busy={active}
                        objective={objective}
                      />
                    </div>
                  )}
                </Suspense>
                <Details value={state} title="Desktop runtime details" />
              </>
            )}
          </div>
        </details>
      </Main>
    </WorkspacePage>
  );
}
