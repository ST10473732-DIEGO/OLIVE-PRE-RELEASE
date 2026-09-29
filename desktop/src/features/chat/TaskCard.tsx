import { useState } from "react";
import { Check, X, Circle, Loader2, FolderCode, Globe, FileDiff, Square, Undo2 } from "lucide-react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Sheet } from "../../components/Sheet";
import "./task.css";

/** Renderer view of one OLIVE task (see olive/bridge/agent_routes.task_view). */
export interface TaskView {
  id: string;
  user_request: string;
  state: string;
  active: boolean;
  chat_id?: string | null;
  message_id?: string | null;
  workspace_id?: string | null;
  status_text: string;
  timeline: { time: string; status: "done" | "failed" | "info" | "running"; text: string }[];
  changes: { path: string; change: "created" | "modified" }[];
  validation: {
    passed?: boolean;
    commands?: { name: string; exit_code: number | null; state: string }[];
    tests?: { passed: number; failed: number; skipped?: number; total: number; framework: string };
  };
  preview: { session_id?: string; url?: string; state?: string; error?: string };
  failure_category: string;
  error?: string | null;
  plan: { step_id: string; description: string; state: string }[];
  constraints: string[];
}

const HEADLINES: Record<string, string> = {
  planning: "Planning…",
  running: "Working…",
  waiting_for_confirmation: "Waiting for approval…",
  waiting_confirmation: "Waiting for approval…",
  waiting_permission: "Waiting for approval…",
  waiting_user: "Waiting for you",
  paused: "Paused",
  stopping: "Stopping…",
  completed: "Completed",
  failed: "Task incomplete",
  cancelled: "Stopped",
};

export function useChatTasks(chatId: string) {
  const resource = useResource(
    () => call<TaskView[]>("agent.chat_tasks", { chat_id: chatId }),
    ["agent"],
    chatId,
  );
  const byMessage: Record<string, TaskView[]> = {};
  for (const task of resource.data || []) {
    if (task.message_id) (byMessage[task.message_id] ||= []).push(task);
  }
  return byMessage;
}

function Mark({ status }: { status: string }) {
  if (status === "done") return <Check size={13} aria-label="Done" className="task-mark" data-status="done" />;
  if (status === "failed") return <X size={13} aria-label="Failed" className="task-mark" data-status="failed" />;
  if (status === "running") return <Loader2 size={13} aria-label="Running" className="task-mark task-spin" />;
  return <Circle size={8} aria-hidden="true" className="task-mark" data-status="info" />;
}

export function TaskCard({
  task,
  openStudio,
  report,
  compact = false,
}: {
  task: TaskView;
  openStudio?: (workspaceId: string, previewSession?: string) => void;
  report: (e: unknown) => void;
  compact?: boolean;
}) {
  const [diffOpen, setDiffOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const act = (work: () => Promise<unknown>) => {
    setBusy(true);
    void work().catch(report).finally(() => setBusy(false));
  };
  const tests = task.validation?.tests;
  const previewLive = task.preview?.state === "running" && task.preview.url;
  const tone = task.state === "completed" ? (task.validation?.passed === false ? "warning" : "success")
    : ["failed"].includes(task.state) ? "error" : ["cancelled", "waiting_user", "paused"].includes(task.state) ? "warning" : "accent";
  const entries = compact ? task.timeline.slice(-6) : task.timeline;
  return (
    <section className="task-card" aria-label="OLIVE task" data-state={task.state}>
      <header className="task-card-head">
        <span className="ws-pill badge" data-tone={tone}>
          {task.active && <Loader2 size={12} className="task-spin" aria-hidden="true" />}
          {task.active ? task.status_text || HEADLINES[task.state] : task.state === "completed" && task.validation?.passed === false ? "Checks ran — failures found" : HEADLINES[task.state] || task.state}
        </span>
        {task.failure_category && !task.active && task.state !== "completed" && (
          <span className="task-category">{task.failure_category}</span>
        )}
      </header>
      <ol className="task-timeline" aria-label="Task timeline">
        {entries.map((entry, index) => (
          <li key={index} data-status={entry.status}>
            <Mark status={entry.status} />
            <span>{entry.text}</span>
          </li>
        ))}
        {task.active && (
          <li data-status="running">
            <Mark status="running" />
            <span>{task.status_text || "Working…"}</span>
          </li>
        )}
      </ol>
      {(tests || task.changes.length > 0 || previewLive) && (
        <dl className="task-evidence">
          {task.changes.length > 0 && (
            <div>
              <dt>Files</dt>
              <dd>{task.changes.map((c) => <code key={c.path} title={c.change}>{c.path}</code>)}</dd>
            </div>
          )}
          {tests && (
            <div>
              <dt>Tests</dt>
              <dd>
                <span data-status="done">✓ {tests.passed} passed</span>
                {tests.failed > 0 && <span data-status="failed"> ✗ {tests.failed} failed</span>}
                {!!tests.skipped && <span> · {tests.skipped} skipped</span>}
              </dd>
            </div>
          )}
          {previewLive && (
            <div>
              <dt>Preview</dt>
              <dd><code>{task.preview.url}</code></dd>
            </div>
          )}
        </dl>
      )}
      {task.constraints.length > 0 && (
        <p className="task-constraints small muted">Constraints: {task.constraints.join(" · ")}</p>
      )}
      <div className="task-actions">
        {task.active && (
          <button className="danger-action" disabled={busy} onClick={() => act(() => call("agent.stop_task", { task_id: task.id }))}>
            <Square size={13} aria-hidden="true" /> Stop
          </button>
        )}
        {task.workspace_id && openStudio && (
          <button onClick={() => openStudio(task.workspace_id!)}>
            <FolderCode size={13} aria-hidden="true" /> Open in Studio
          </button>
        )}
        {previewLive && openStudio && (
          <button onClick={() => openStudio(task.workspace_id!, task.preview.session_id)}>
            <Globe size={13} aria-hidden="true" /> Open preview
          </button>
        )}
        {task.changes.length > 0 && (
          <button onClick={() => setDiffOpen(true)}>
            <FileDiff size={13} aria-hidden="true" /> Show changes
          </button>
        )}
        {previewLive && !task.active && (
          <button className="quiet" disabled={busy} onClick={() => act(() => call("agent.stop_preview", { task_id: task.id }))}>
            Stop preview
          </button>
        )}
      </div>
      {diffOpen && <DiffSheet task={task} close={() => setDiffOpen(false)} report={report} />}
    </section>
  );
}

interface DiffFile { path: string; change: string; status: string; diff: string }

function DiffSheet({ task, close, report }: { task: TaskView; close: () => void; report: (e: unknown) => void }) {
  const diff = useResource(() => call<{ files: DiffFile[]; truncated: boolean }>("agent.task_diff", { task_id: task.id }), ["agent"], task.id);
  const [undoing, setUndoing] = useState(false);
  const [outcome, setOutcome] = useState<{ reverted: string[]; skipped: { path: string; reason: string }[] }>();
  return (
    <Sheet open onOpenChange={(open) => !open && close()} title="Changes made by this task"
      description="Exactly what OLIVE changed, from its own before-snapshots. Files edited afterwards are marked and never undone.">
      <div className="task-diff">
        {diff.error && <p role="alert">{diff.error}</p>}
        {diff.data?.files.map((file) => (
          <article key={file.path}>
            <h3><code>{file.path}</code> <span className="small muted">{file.change} · {file.status}</span></h3>
            <pre className="task-diff-body">{file.diff.split("\n").map((line, index) => (
              <span key={index} data-line={line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : undefined}>{line + "\n"}</span>
            ))}</pre>
          </article>
        ))}
        {diff.data?.truncated && <p className="small muted">The diff is longer than shown; open the files in Studio.</p>}
        {!task.active && (
          <div className="task-actions">
            <button disabled={undoing || !!outcome} onClick={() => {
              setUndoing(true);
              void call<typeof outcome>("agent.revert", { task_id: task.id }).then(setOutcome).catch(report).finally(() => setUndoing(false));
            }}>
              <Undo2 size={13} aria-hidden="true" /> Undo these changes
            </button>
          </div>
        )}
        {outcome && (
          <p role="status">
            {outcome.reverted.length ? `Undone: ${outcome.reverted.join(", ")}.` : "Nothing was undone."}
            {outcome.skipped.map((s) => ` ${s.path}: ${s.reason}.`).join("")}
          </p>
        )}
      </div>
    </Sheet>
  );
}
