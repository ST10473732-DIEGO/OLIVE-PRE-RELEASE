// Renderer-side store for the Studio tooling runtime (language servers, debug
// adapters, terminals, build/test jobs). Everything here mirrors real events
// from the Python runtime; nothing is synthesised. Views subscribe through
// `useTooling(workspaceId)` and read a per-workspace slice.
import { useSyncExternalStore } from "react";
import { call, type WireEvent } from "../../services/api";

export interface Position {
  line: number;
  character: number;
}
export interface Range {
  start: Position;
  end: Position;
}
export interface Diagnostic {
  range: Range;
  severity: number;
  code: string;
  source: string;
  message: string;
}
export interface LanguageStatus {
  workspace_id: string;
  language: string;
  state: string;
  detail: string;
  features: string[];
  documents: number;
  restarts: number;
  provider: string;
}
export interface WorkspaceEdit {
  files: {
    path: string;
    edits: { range: Range; newText: string }[];
    open: boolean;
  }[];
  total: number;
  label?: string;
}
export interface DebugStatus {
  session_id: string;
  workspace_id: string;
  adapter: string;
  state: string;
  detail: string;
  suspended: boolean;
  thread_id: number | null;
  generation: number;
  exit_code: number | null;
  provider: string;
  capabilities: Record<string, boolean>;
  exception_filters: { filter: string; label: string; default: boolean }[];
}
export interface DebugEvent {
  session_id: string;
  workspace_id: string;
  event: string;
  body: Record<string, unknown>;
  generation: number;
  state: string;
}
export interface Breakpoint {
  line: number;
  requested_line?: number;
  verified: boolean;
  message: string;
  condition: string;
  id?: number;
}
export interface TerminalStatus {
  session_id: string;
  workspace_id: string;
  title: string;
  shell: string;
  cwd: string;
  state: string;
  pid: number | null;
  exit_code: number | null;
  columns: number;
  rows: number;
  trust: string;
  created_at: number;
}
export interface Job {
  id: string;
  workspace_id: string;
  kind: string;
  label: string;
  command: string[];
  state: string;
  started_at: number;
  ended_at: number | null;
  exit_code: number | null;
  output?: string;
  session_id: string | null;
  cancelled: boolean;
  diagnostics?: unknown[];
  error?: string;
  runner?: string;
  tests?: { full_name: string; name: string; file?: string; line?: number }[];
  summary?: TestsReport["summary"];
  results?: TestResult[];
}
export interface TestResult {
  name: string;
  full_name: string;
  state: string;
  duration_seconds: number;
  message: string;
  stack_trace: string;
  file: string;
  line: number | null;
  relative_file?: string;
}
export interface TestsReport {
  workspace_id: string;
  job_id: string;
  summary: {
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    duration_seconds: number;
  };
  results: TestResult[];
  error?: string;
}
export interface Problem {
  file?: string;
  line?: number;
  column?: number;
  severity: string;
  message: string;
  source?: string;
}
export interface RunRecord {
  id: string;
  workspace_id: string;
  state: string;
  local_url: string | null;
  application_type: string;
  command: string[];
  exit_code: number | null;
}
export interface WorkspaceTooling {
  languages: Record<string, LanguageStatus>;
  diagnostics: Record<string, Diagnostic[]>;
  proposedEdits: WorkspaceEdit[];
  debug: DebugStatus | null;
  debugEvents: DebugEvent[];
  debugConsole: { category: string; output: string }[];
  breakpoints: Record<string, Breakpoint[]>;
  terminals: Record<string, TerminalStatus>;
  jobs: Record<string, Job>;
  tests: TestsReport | null;
  discovered: Job["tests"] | null;
  problems: Problem[];
  runs: Record<string, RunRecord>;
}
const empty = (): WorkspaceTooling => ({
  languages: {},
  diagnostics: {},
  proposedEdits: [],
  debug: null,
  debugEvents: [],
  debugConsole: [],
  breakpoints: {},
  terminals: {},
  jobs: {},
  tests: null,
  discovered: null,
  problems: [],
  runs: {},
});
type Listener = () => void;
type DataListener = (data: string) => void;
class ToolingStore {
  private slices = new Map<string, WorkspaceTooling>();
  private listeners = new Set<Listener>();
  private terminalListeners = new Map<string, Set<DataListener>>();
  private terminalBuffers = new Map<string, string>();
  private hydrated = new Set<string>();
  slice(workspaceId: string): WorkspaceTooling {
    return this.slices.get(workspaceId) || (this.slices.set(workspaceId, empty()), this.slices.get(workspaceId)!);
  }
  private update(workspaceId: string, patch: Partial<WorkspaceTooling>) {
    this.slices.set(workspaceId, { ...this.slice(workspaceId), ...patch });
    for (const listener of this.listeners) listener();
  }
  // The single application-wide event subscription lives in App; it forwards
  // every event here through handle(). A lazy chunk registering its own
  // contextBridge subscription is unreliable under the sandbox.
  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  received: Record<string, number> = {};
  handle(event: WireEvent) {
    this.received[event.topic] = (this.received[event.topic] || 0) + 1;
    const data = event.data as Record<string, unknown>;
    const ws = String(data?.workspace_id || "");
    switch (event.topic) {
      case "lsp.state": {
        const status = event.data as LanguageStatus;
        const slice = this.slice(ws);
        this.update(ws, {
          languages: { ...slice.languages, [status.language]: status },
        });
        break;
      }
      case "lsp.diagnostics": {
        const slice = this.slice(ws);
        const path = String(data.path);
        const items = (data.diagnostics as Diagnostic[]) || [];
        const next = { ...slice.diagnostics };
        if (items.length) next[path] = items;
        else delete next[path];
        this.update(ws, { diagnostics: next });
        break;
      }
      case "lsp.apply_edit": {
        const slice = this.slice(ws);
        this.update(ws, {
          proposedEdits: [...slice.proposedEdits, event.data as WorkspaceEdit].slice(-10),
        });
        break;
      }
      case "dap.state": {
        const status = event.data as DebugStatus;
        const slice = this.slice(ws);
        const active = ["starting", "running", "suspended"].includes(status.state);
        this.update(ws, {
          debug: active || slice.debug?.session_id === status.session_id ? status : slice.debug,
        });
        break;
      }
      case "dap.event": {
        const item = event.data as DebugEvent;
        const slice = this.slice(ws);
        const consoleLines =
          item.event === "output"
            ? [
                ...slice.debugConsole,
                {
                  category: String(item.body.category || "console"),
                  output: String(item.body.output || ""),
                },
              ].slice(-2000)
            : slice.debugConsole;
        let breakpoints = slice.breakpoints;
        if (item.event === "breakpoint") {
          const bp = (item.body.breakpoint || {}) as {
            id?: number;
            line?: number;
            verified?: boolean;
            message?: string;
            source?: { path?: string };
          };
          const path = bp.source?.path;
          if (path && breakpoints[path])
            breakpoints = {
              ...breakpoints,
              [path]: breakpoints[path].map((stored) =>
                stored.id === bp.id || stored.line === bp.line
                  ? {
                      ...stored,
                      verified: Boolean(bp.verified),
                      message: bp.message || "",
                      id: bp.id,
                    }
                  : stored,
              ),
            };
        }
        this.update(ws, {
          debugEvents: [...slice.debugEvents, item].slice(-200),
          debugConsole: consoleLines,
          breakpoints,
          // Only stop/resume events change suspension; an interleaved "output"
          // or "thread" event must not clear the paused state.
          debug: slice.debug
            ? {
                ...slice.debug,
                state: ["stopped", "continued", "terminated", "exited"].includes(item.event) ? item.state : slice.debug.state,
                generation: item.generation,
                suspended:
                  item.event === "stopped"
                    ? true
                    : ["continued", "terminated", "exited"].includes(item.event)
                      ? false
                      : slice.debug.suspended,
                thread_id:
                  item.event === "stopped"
                    ? Number(item.body.threadId ?? slice.debug.thread_id)
                    : slice.debug.thread_id,
              }
            : slice.debug,
        });
        break;
      }
      case "terminal.state": {
        const status = event.data as TerminalStatus;
        const slice = this.slice(ws);
        const terminals = { ...slice.terminals };
        if (status.state === "closed") {
          delete terminals[status.session_id];
          this.terminalBuffers.delete(status.session_id);
        } else terminals[status.session_id] = status;
        this.update(ws, { terminals });
        break;
      }
      case "terminal.data": {
        const id = String(data.session_id);
        const chunk = String(data.data || "");
        const buffer = (this.terminalBuffers.get(id) || "") + chunk;
        this.terminalBuffers.set(id, buffer.slice(-200000));
        for (const listener of this.terminalListeners.get(id) || []) listener(chunk);
        break;
      }
      case "build.progress":
      case "build.result": {
        const job = event.data as Job;
        const slice = this.slice(ws);
        const previous = slice.jobs[job.id];
        const merged: Job = {
          ...previous,
          ...job,
          output: job.output ?? previous?.output ?? "",
        };
        const patch: Partial<WorkspaceTooling> = {
          jobs: { ...slice.jobs, [job.id]: merged },
        };
        if (event.topic === "build.result" && job.kind === "test-list" && job.tests)
          patch.discovered = job.tests;
        this.update(ws, patch);
        break;
      }
      case "tests.results":
        this.update(ws, { tests: event.data as TestsReport });
        break;
      case "problems":
        this.update(ws, { problems: (data.items as Problem[]) || [] });
        break;
      case "run": {
        const run = event.data as RunRecord;
        const slice = this.slice(ws);
        this.update(ws, { runs: { ...slice.runs, [run.id]: run } });
        break;
      }
      default:
        break;
    }
  }
  onTerminalData(sessionId: string, listener: DataListener) {
    const set = this.terminalListeners.get(sessionId) || new Set();
    set.add(listener);
    this.terminalListeners.set(sessionId, set);
    return () => {
      set.delete(listener);
    };
  }
  terminalReplay(sessionId: string) {
    return this.terminalBuffers.get(sessionId) || "";
  }
  setBreakpoints(workspaceId: string, path: string, items: Breakpoint[]) {
    const slice = this.slice(workspaceId);
    const breakpoints = { ...slice.breakpoints };
    if (items.length) breakpoints[path] = items;
    else delete breakpoints[path];
    this.update(workspaceId, { breakpoints });
  }
  clearDebug(workspaceId: string) {
    this.update(workspaceId, { debugEvents: [], debugConsole: [] });
  }
  dismissEdit(workspaceId: string, edit: WorkspaceEdit) {
    const slice = this.slice(workspaceId);
    this.update(workspaceId, {
      proposedEdits: slice.proposedEdits.filter((item) => item !== edit),
    });
  }
  // Late-mounted views read the runtime's actual state instead of trusting
  // whatever events happened to arrive while Studio was closed.
  async hydrate(workspaceId: string, force = false) {
    if (!workspaceId || (this.hydrated.has(workspaceId) && !force)) return;
    this.hydrated.add(workspaceId);
    const [languages, debug, terminals, jobs, diagnostics] = await Promise.all([
      call<{ sessions: LanguageStatus[] }>("lsp.status", { workspace_id: workspaceId }).catch(() => ({ sessions: [] })),
      call<{
        active: DebugStatus | null;
        output: { category: string; output: string }[];
        breakpoints: Record<string, Breakpoint[]>;
      }>("dap.status", { workspace_id: workspaceId }).catch(() => ({ active: null, output: [], breakpoints: {} })),
      call<{ sessions: TerminalStatus[] }>("terminal.list", { workspace_id: workspaceId }).catch(() => ({ sessions: [] })),
      call<{ jobs: Job[] }>("project.jobs", { workspace_id: workspaceId }).catch(() => ({ jobs: [] })),
      call<{ files: { path: string; diagnostics: Diagnostic[] }[] }>("lsp.diagnostics", { workspace_id: workspaceId }).catch(() => ({ files: [] })),
    ]);
    const slice = this.slice(workspaceId);
    this.update(workspaceId, {
      languages: Object.fromEntries(languages.sessions.map((s) => [s.language, s])),
      debug: debug.active,
      debugConsole: debug.output,
      breakpoints: { ...debug.breakpoints, ...slice.breakpoints },
      terminals: Object.fromEntries(terminals.sessions.map((s) => [s.session_id, s])),
      jobs: Object.fromEntries(jobs.jobs.map((j) => [j.id, { ...slice.jobs[j.id], ...j }])),
      diagnostics: Object.fromEntries(diagnostics.files.map((f) => [f.path, f.diagnostics])),
    });
  }
}
export const tooling = new ToolingStore();
const emptySlice = empty();
export function useTooling(workspaceId: string): WorkspaceTooling {
  return useSyncExternalStore(
    tooling.subscribe,
    () => (workspaceId ? tooling.slice(workspaceId) : emptySlice),
    () => emptySlice,
  );
}
// Paths from the runtime are absolute and canonical; Studio works in
// workspace-relative POSIX form.
export function relativePath(root: string, path: string) {
  const norm = (value: string) => value.replace(/\\/g, "/").replace(/\/+$/, "");
  const base = norm(root).toLowerCase();
  const target = norm(path);
  if (target.toLowerCase().startsWith(base + "/")) return target.slice(base.length + 1);
  return target;
}
export function absolutePath(root: string, path: string) {
  if (/^[A-Za-z]:[\\/]/.test(path) || path.startsWith("/")) return path;
  return root.replace(/[\\/]+$/, "") + "\\" + path.replace(/\//g, "\\");
}
export const samePath = (a: string, b: string) =>
  a.replace(/\\/g, "/").toLowerCase() === b.replace(/\\/g, "/").toLowerCase();
