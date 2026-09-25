import {
  responseAfter,
  type ConversationAnchor,
} from "../services/conversation";
import type { RecordTarget } from "../services/handoff";
import { useEffect, useState } from "react";
import { call, type Chat, type Workspace } from "../services/api";
import { useResource } from "../services/useResource";
import {
  WorkspacePage,
  Details,
  Rail,
  Main,
  Panel,
  EmptyState,
  Pill,
  Disclosure,
  Notice,
} from "../components/WorkspacePage";
import { GrowingComposer } from "../components/GrowingComposer";
import { Markdown } from "../components/Markdown";
import {
  Bot,
  Search,
  FolderOpen,
  FolderKanban,
  Play,
  Square,
  Pause,
  ListOrdered,
  ClipboardCheck,
  FileDiff,
  AlertTriangle,
  History,
  Sparkles,
} from "lucide-react";
import { whenLabel } from "../services/when";
const toneOf = (state: string): "success" | "error" | "warning" | "accent" | undefined =>
  state === "completed" || state === "passed"
    ? "success"
    : ["failed", "blocked"].includes(state)
      ? "error"
      : ["paused", "awaiting_approval", "waiting_for_confirmation", "cancelled", "pausing"].includes(state)
        ? "warning"
        : ["running", "planning"].includes(state)
          ? "accent"
          : undefined;
interface TaskSummary {
  id: string;
  user_request: string;
  state: string;
  updated_at: string;
  validation_status: string;
}
interface Task extends TaskSummary {
  plan: {
    description: string;
    state: string;
    tool_name: string;
    result?: unknown;
  }[];
  completion_summary?: string;
  completion_evidence: string[];
  files_changed: string[];
  error?: string;
  implementation_status: string;
}
const labels: Record<string, string> = {
  created: "Created",
  planning: "Planning",
  running: "Working",
  waiting_for_confirmation: "Awaiting approval",
  paused: "Paused",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  pending: "Not attempted",
  not_run: "Not run",
  passed: "Passed",
  not_started: "Not started",
};
export default function Agent({
  target,
  chat,
  workspaces,
  workspaceId,
  setWorkspaceId,
  runtimeState,
  busy,
  submit,
  cancel,
  report,
}: {
  target?: RecordTarget;
  chat: Chat;
  workspaces: Workspace[];
  workspaceId: string;
  setWorkspaceId: (id: string) => void;
  runtimeState: string;
  busy: boolean;
  submit: (
    text: string,
    context?: { workspace_id: string; project_id: string },
  ) => Promise<void>;
  cancel: () => void;
  report: (e: unknown) => void;
}) {
  const [search, setSearch] = useState("");
  const [historyPage, setHistoryPage] = useState(0);
  const resource = useResource(async () => {
    const [current, history, projects] = await Promise.all([
      call<{ task: Task | null; active: boolean; paused: boolean; pause_state: string }>(
        "agent.current",
        {},
      ),
      call<TaskSummary[]>("agent.history", {query:search,offset:historyPage*100}),
      call<{ id: string; title: string }[]>("data.projects", {}),
    ]);
    return { current, history, projects };
  }, ["agent", "projects", "runtime.activity"], `${historyPage}:${search}`);
  const [objective, setObjective] = useState("");
  const workspace = workspaceId;
  const setWorkspace = setWorkspaceId;
  const [project, setProject] = useState("");
  const [selected, setSelected] = useState<Task>();
  useEffect(() => {
    if (!target) return;
    let live = true;
    void call<Task>("agent.get", { task_id: target.id })
      .then((task) => {
        if (live) setSelected(task);
      })
      .catch(report);
    return () => {
      live = false;
    };
  }, [target]);
  const [actions, setActions] = useState<unknown>();
  const [submittedAfter, setSubmittedAfter] = useState<ConversationAnchor>();
  const [resuming, setResuming] = useState(false);
  const current = resource.data?.current;
  const task =
    current?.active || (selected && selected.id === current?.task?.id)
      ? current?.task
      : selected || current?.task;
  const latest = chat.messages.at(-1);
  const response = responseAfter(chat, submittedAfter);
  const operation = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await resource.refresh();
    } catch (e) {
      report(e);
    }
  };
  const start = () => {
    if (busy || !objective.trim()) return;
    setSelected(undefined);
    setSubmittedAfter({ chatId: chat.id, after: latest?.id || "" });
    void submit(objective, {
      workspace_id: workspace,
      project_id: project,
    }).then(() => resource.refresh());
  };
  const history = resource.data?.history.filter((t) =>
    t.user_request.toLowerCase().includes(search.toLowerCase()),
  );
  const stateLabel = current?.active && current.pause_state === "pausing" ? "Pausing" : task ? labels[task.state] || task.state : "";
  const headerStatus = current?.active
    ? current.pause_state === "pausing"
      ? "Pause requested"
      : current.paused
        ? "Paused"
        : "Working"
    : busy
      ? runtimeState
      : "Idle";
  const workspaceTitle = workspaces.find((w) => w.id === workspace)?.title;
  const projectTitle = resource.data?.projects.find((p) => p.id === project)?.title;
  return (
    <WorkspacePage
      layout="fill"
      className="agent"
      icon={<Bot size={18} />}
      title="Agent"
      description="Give OLIVE an objective. Every step, file change and validation is recorded."
      status={headerStatus}
      statusTone={current?.active ? (current.pause_state === "pausing" || current.paused ? "warning" : "live") : busy ? "live" : "idle"}
      rail={
        <Rail wide title="Task history" label="Task history">
          <label className="search agent-search">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search Agent tasks"
              placeholder="Find an objective…"
              value={search}
              onChange={(e) => {setSearch(e.target.value);setHistoryPage(0);}}
            />
          </label>
          <div className="record-list agent-history">
            {history?.map((t) => (
              <button
                className={`ws-row record-card project-card ${task?.id === t.id ? "selected" : ""}`}
                aria-pressed={task?.id === t.id}
                key={t.id}
                onClick={() =>
                  void call<Task>("agent.get", { task_id: t.id })
                    .then(setSelected)
                    .catch(report)
                }
              >
                <span className="ws-row-text">
                  <strong>{t.user_request}</strong>
                  <span className="muted" title={t.updated_at}>
                    {labels[t.state] || t.state} · {whenLabel(t.updated_at)}
                  </span>
                </span>
                <span className="agent-history-dot" data-tone={toneOf(t.state)} aria-hidden="true" />
              </button>
            ))}
          </div>
          {(historyPage>0 || resource.data?.history.length===100) && <div className="row agent-paging">
            <button className="quiet" disabled={!historyPage || resource.loading} onClick={()=>setHistoryPage(value=>value-1)}>Previous history</button>
            <span>Page {historyPage+1}</span>
            <button className="quiet" disabled={resource.loading || (resource.data?.history.length||0)<100} onClick={()=>setHistoryPage(value=>value+1)}>Older history</button>
          </div>}
          {resource.data?.history.length === 0 && (
            <p className="muted agent-history-none">
              {search || historyPage ? "No matching tasks on this page." : "No Agent tasks yet. Your objectives use the same language core as Home and Chat."}
            </p>
          )}
        </Rail>
      }
    >
      <Main className="agent-main" label="Agent workspace">
        <section className="objective-surface ws-composer agent-composer" aria-label="Objective">
          <p className="ws-eyebrow">Objective</p>
          <GrowingComposer
            aria-label="Agent objective"
            placeholder="What would you like to accomplish?"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                start();
              }
            }}
          />
          <div className="ws-composer-bottom agent-composer-bottom">
            <div className="agent-context">
              <label className="agent-context-field" title={workspaceTitle || "Choose the folder the Agent may work in"}>
                <FolderOpen size={14} aria-hidden="true" />
                <select
                  aria-label="Agent workspace"
                  value={workspace}
                  disabled={busy}
                  onChange={(e) => setWorkspace(e.target.value)}
                >
                  <option value="">No workspace selected</option>
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="agent-context-field" title={projectTitle || "Link the task to a project"}>
                <FolderKanban size={14} aria-hidden="true" />
                <select
                  aria-label="Agent project"
                  value={project}
                  disabled={busy}
                  onChange={(e) => setProject(e.target.value)}
                >
                  <option value="">No project selected</option>
                  {resource.data?.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <span className="ws-composer-hint">Ctrl+Enter to start</span>
            {busy && (
              <button className="quiet" onClick={cancel}>
                <Square size={14} aria-hidden="true" />
                Cancel current request
              </button>
            )}
            <button
              className="primary agent-start"
              disabled={busy || !objective.trim()}
              onClick={start}
            >
              <Play size={15} aria-hidden="true" />
              Start objective
            </button>
          </div>
        </section>
        {busy && (
          <p role="status" className="agent-status">
            {current?.active
              ? "Agent is working. Its current tool finishes safely before a requested pause."
              : `${runtimeState}. OLIVE is handling your objective.`}
          </p>
        )}
        {resource.error && (
          <p role="alert" className="agent-alert">
            {resource.error}
            <button className="quiet" onClick={() => void resource.refresh()}>Retry</button>
          </p>
        )}
        {response && (
          <Panel as="section" title="Response" icon={<Sparkles size={15} />} className="record-card agent-response">
            <Markdown text={response.content} />
          </Panel>
        )}
        {task ? (
          <section className="agent-task" aria-label={current?.active ? "Active task" : "Selected task"}>
            <header className="agent-task-head">
              <div className="agent-task-title">
                <div className="row">
                  <h2>{current?.active ? "Active task" : "Selected task"}</h2>
                  <span className="badge ws-pill" data-tone={toneOf(current?.active && current.pause_state === "pausing" ? "pausing" : task.state)}>
                    {stateLabel}
                  </span>
                </div>
                <p className="agent-task-request">{task.user_request}</p>
              </div>
              <div className="agent-task-controls">
                {current?.active && current.pause_state === "none" && (
                  <button
                    onClick={() =>
                      void operation(() => call("agent.pause", {}))
                    }
                  >
                    <Pause size={14} aria-hidden="true" />
                    Pause after current tool
                  </button>
                )}
                {(task.state === "paused" || current?.pause_state === "pausing") && (
                  <button
                    className="primary"
                    disabled={resuming}
                    onClick={() => {
                      setResuming(true);
                      void operation(() =>
                        call("agent.resume", { task_id: task.id }),
                      ).finally(() => setResuming(false));
                    }}
                  >
                    <Play size={14} aria-hidden="true" />
                    Resume task
                  </button>
                )}
                {current?.active && (
                  <button
                    className="danger-action"
                    onClick={() =>
                      void operation(() => call("agent.cancel", {}))
                    }
                  >
                    <Square size={14} aria-hidden="true" />
                    Cancel Agent task
                  </button>
                )}
              </div>
            </header>
            {current?.active && current.pause_state === "pausing" && <p role="status" className="agent-status">Pause requested. The in-flight operation finishes safely before the next tool can start.</p>}
            {current?.paused && runtimeState !== "Paused" && <p role="status" className="agent-status">This Agent task is paused. Other activity keeps the global state {runtimeState.toLowerCase()}.</p>}
            <div className="ws-grid main-side agent-detail">
              <Panel title="Steps" sub={`${task.plan.length} planned step${task.plan.length === 1 ? "" : "s"}`} icon={<ListOrdered size={15} />} headingLevel={3}>
                {task.plan.length ? (
                  <ol className="task-timeline ws-timeline">
                    {task.plan.map((step, index) => (
                      <li key={`${task.id}:${index}`} data-state={step.state}>
                        <div className="ws-step">
                          <strong>{step.description}</strong>
                          <Pill tone={toneOf(step.state)}>
                            {labels[step.state] || step.state}
                          </Pill>
                        </div>
                        {step.result !== undefined && (
                          <Details
                            value={step.result}
                            title={step.tool_name || "Tool result"}
                          />
                        )}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted small">No steps have been planned yet.</p>
                )}
              </Panel>
              <div className="agent-outcome">
                <Panel title="Validation" icon={<ClipboardCheck size={15} />} headingLevel={3}
                  actions={<Pill tone={toneOf(task.validation_status)}>{labels[task.validation_status] || task.validation_status}</Pill>}
                >
                  <h3 className="sr-only">
                    Validation:{" "}
                    {labels[task.validation_status] || task.validation_status}
                  </h3>
                  {task.completion_summary ? (
                    <Markdown text={task.completion_summary} />
                  ) : (
                    <p className="muted small">No completion summary recorded.</p>
                  )}
                  {task.completion_evidence.length > 0 && (
                    <ul className="agent-evidence">
                      {task.completion_evidence.map((e, i) => (
                        <li key={i}>{e}</li>
                      ))}
                    </ul>
                  )}
                </Panel>
                <Panel title="Changed files" icon={<FileDiff size={15} />} headingLevel={3}
                  actions={<Pill>{task.files_changed.length}</Pill>}
                >
                  {task.files_changed.length > 0 ? (
                    <ul className="agent-files">
                      {task.files_changed.map((f) => (
                        <li key={f}><code>{f}</code></li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted small">No files were changed.</p>
                  )}
                </Panel>
                {task.error && (
                  <Notice tone="error" icon={<AlertTriangle size={15} />} role="note">
                    <p>The task stopped before completing all requested work.</p>
                    <Details value={task.error} title="Failure details" />
                  </Notice>
                )}
              </div>
            </div>
            <Disclosure summary="Developer details" className="agent-developer">
              <Details value={task} title="Task record" />
            </Disclosure>
          </section>
        ) : (
          <>
            <EmptyState
              className="empty-workspace agent-ready"
              icon={<Bot size={26} />}
              title="Ready for an objective"
            >
              Tasks show actual steps, changed files and validation. A
              conversation response does not imply an action was executed.
            </EmptyState>
            <div className="agent-how" aria-label="How the Agent works">
              <div className="ws-card">
                <span className="ws-card-icon" aria-hidden="true"><ListOrdered size={15} /></span>
                <strong>Plans</strong>
                <p>Breaks the objective into steps you can read before and while they run.</p>
              </div>
              <div className="ws-card">
                <span className="ws-card-icon" aria-hidden="true"><FileDiff size={15} /></span>
                <strong>Works in a workspace</strong>
                <p>Uses tools inside the approved folder you choose; every file change is listed.</p>
              </div>
              <div className="ws-card">
                <span className="ws-card-icon" aria-hidden="true"><ClipboardCheck size={15} /></span>
                <strong>Validates</strong>
                <p>Records evidence and a validation result, so a response never stands in for real work.</p>
              </div>
            </div>
          </>
        )}
        <Disclosure summary={<><History size={15} aria-hidden="true" />Recent tool audit</>} className="agent-audit">
          <button
            className="quiet"
            onClick={() =>
              void call("agent.actions", {}).then(setActions).catch(report)
            }
          >
            Load tool audit
          </button>
          {actions !== undefined && (
            <Details value={actions} title="Audit records" />
          )}
        </Disclosure>
      </Main>
    </WorkspacePage>
  );
}
