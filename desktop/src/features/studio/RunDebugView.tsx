import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Bug,
  ChevronDown,
  ChevronRight,
  Circle,
  Pause,
  Play,
  Plus,
  Square,
  StepForward,
  X,
} from "lucide-react";
import type { Debugger, Variable } from "./debugClient";
import { relativePath } from "./tooling";

// Everything here comes from the debug adapter (debugpy or netcoredbg over
// DAP): frames, scopes, variables and evaluation results are fetched live and
// dropped as soon as execution resumes. Enable/disable breakpoints, inline
// values, restart and data breakpoints do not exist and are not offered.

export function debugStateText(debug: Debugger): string {
  const status = debug.status;
  if (!status) return "No debug session";
  if (status.state === "suspended") return "Paused";
  if (status.state === "running") return "Running";
  if (status.state === "starting") return "Starting";
  if (status.state === "terminated") return `Ended${status.exit_code !== null ? ` · exit ${status.exit_code}` : ""}`;
  if (status.state === "failed") return `Failed · ${status.detail}`;
  return "Stopped";
}

function Section({ id, title, count, children, open, toggle }: { id: string; title: string; count?: number; children: React.ReactNode; open: boolean; toggle: (id: string) => void }) {
  return (
    <div className="side-section">
      <div className="side-section-head">
        <button className="side-section-toggle" aria-expanded={open} onClick={() => toggle(id)}>
          {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
          <span>{title}</span>
          {count ? <span className="count" data-tone="neutral" aria-hidden="true">{count}</span> : null}
        </button>
      </div>
      {open && <div className="side-section-body">{children}</div>}
    </div>
  );
}

export function RunDebugView({
  debug,
  root,
  launch,
  busy,
  launchable,
  openFile,
}: {
  debug: Debugger;
  root: string;
  launch: () => void;
  busy: boolean;
  /** The launch configuration in words, or "" when nothing can be debugged. */
  launchable: string;
  openFile: (path: string, line?: number) => void;
}) {
  const { active } = debug;
  const paused = Boolean(active?.suspended);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const toggle = (id: string) => setClosed((c) => ({ ...c, [id]: !c[id] }));
  const [watchDraft, setWatchDraft] = useState("");
  const [filters, setFilters] = useState<string[] | null>(null);
  const exceptionFilters = active?.exception_filters || [];
  const activeFilters = filters ?? exceptionFilters.filter((f) => f.default).map((f) => f.filter);
  const breakpoints = Object.entries(debug.breakpoints).flatMap(([path, items]) =>
    items.map((item) => ({ path: relativePath(root, path), ...item })),
  );
  return (
    <div className="sidebar-view debug-view">
      <div className="side-head">
        <h2>Run and Debug</h2>
      </div>
      <div className="side-scroll">
        {!active ? (
          <div className="side-pad debug-launch">
            <p className="debug-config" title={launchable || "Nothing to debug in this workspace"}>
              <Bug size={13} aria-hidden="true" />
              {launchable || "No debuggable project in this workspace"}
            </p>
            <button className="primary" disabled={busy || !launchable} onClick={launch} title="Start debugging (F5)">
              <Play size={14} aria-hidden="true" />
              Start debugging
            </button>
            <p className="side-note">Click the gutter or press F9 to toggle a breakpoint, then press F5.</p>
          </div>
        ) : (
          <p className="side-note debug-state" data-state={debug.status?.state} role="status">
            {debugStateText(debug)} · {debug.status?.provider}
          </p>
        )}
        {active && (
          <>
            <Section id="variables" title="Variables" open={!closed.variables} toggle={toggle}>
              {paused ? (
                debug.scopes.map((scope, index) => (
                  <VariableTree key={scope.variablesReference} name={scope.name} reference={scope.variablesReference} variables={debug.variables} expand={debug.expand} root={index === 0} />
                ))
              ) : (
                <p className="side-note">Variables appear while the program is paused.</p>
              )}
            </Section>
            <Section id="watch" title="Watch" count={debug.watches.length} open={!closed.watch} toggle={toggle}>
              <form
                className="row watch-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (watchDraft.trim()) debug.addWatch(watchDraft.trim());
                  setWatchDraft("");
                }}
              >
                <input aria-label="Watch expression" placeholder="Expression to watch" value={watchDraft} onChange={(e) => setWatchDraft(e.target.value)} />
                <button type="submit" className="icon-button" aria-label="Add watch">
                  <Plus size={14} aria-hidden="true" />
                </button>
              </form>
              <ul className="watch-list">
                {debug.watches.map((expression) => {
                  const result = debug.watchResults.find((item) => item.expression === expression);
                  return (
                    <li key={expression}>
                      <code>{expression}</code>
                      <span className={result?.error ? "muted" : "variable-value"}>
                        {result ? (result.error ? `— ${result.error}` : result.result) : paused ? "…" : "— not paused"}
                      </span>
                      <button className="icon-button" aria-label={`Remove watch ${expression}`} onClick={() => debug.removeWatch(expression)}>
                        <X size={12} aria-hidden="true" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Section>
            <Section id="stack" title="Call stack" open={!closed.stack} toggle={toggle}>
              {!paused ? (
                <p className="side-note">Pause or hit a breakpoint to inspect frames.</p>
              ) : (
                <ul className="frame-list" aria-label="Call stack">
                  <li className="side-note thread-row">
                    <span className="ws-pill" data-tone="warning">Paused</span>
                  </li>
                  {debug.frames.map((frame) => (
                    <li key={frame.id}>
                      <button
                        className={`frame-row ${debug.frameId === frame.id ? "selected" : ""}`}
                        onClick={() => void debug.selectFrame(frame)}
                        aria-current={debug.frameId === frame.id ? "true" : undefined}
                      >
                        <span className="frame-name">{frame.name}</span>
                        {frame.source?.path && (
                          <span className="frame-where">
                            {relativePath(root, frame.source.path).split("/").pop()}:{frame.line}:{frame.column}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </>
        )}
        <Section id="breakpoints" title="Breakpoints" count={breakpoints.length} open={!closed.breakpoints} toggle={toggle}>
          {breakpoints.length === 0 ? (
            <p className="side-note">No breakpoints. Click the gutter or press F9.</p>
          ) : (
            <ul className="breakpoint-list" aria-label="Breakpoints">
              {breakpoints.map((bp) => (
                <li key={`${bp.path}:${bp.line}`} data-verified={bp.verified || undefined}>
                  <button className="breakpoint-row" onClick={() => openFile(bp.path, bp.line)} title={bp.message || bp.path}>
                    <Circle size={9} aria-hidden="true" className={bp.condition ? "bp-conditional" : bp.verified ? "bp-verified" : "bp-unverified"} />
                    <span className="scm-name">{bp.path.split("/").pop()}</span>
                    <span className="scm-folder">
                      {bp.line}
                      {bp.condition ? ` · if ${bp.condition}` : ""}
                      {!bp.verified ? " · not verified" : ""}
                    </span>
                  </button>
                  <button className="icon-button" aria-label={`Remove breakpoint ${bp.path}:${bp.line}`} onClick={() => void debug.toggleBreakpoint(bp.path, bp.line)}>
                    <X size={12} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Section>
        {active && exceptionFilters.length > 0 && (
          <Section id="exceptions" title="Exception filters" open={!closed.exceptions} toggle={toggle}>
            <ul className="watch-list">
              {exceptionFilters.map((item) => (
                <li key={item.filter}>
                  <label className="small">
                    <input
                      type="checkbox"
                      checked={activeFilters.includes(item.filter)}
                      onChange={(e) => {
                        const next = e.target.checked ? [...activeFilters, item.filter] : activeFilters.filter((value) => value !== item.filter);
                        setFilters(next);
                        void debug.setExceptionFilters(next);
                      }}
                    />
                    {item.label || item.filter}
                  </label>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>
    </div>
  );
}

/** Floating debug toolbar over the editor (Studio V2 §6.4). No Restart. */
export function DebugToolbar({ debug }: { debug: Debugger }) {
  const { active } = debug;
  if (!active) return null;
  const paused = Boolean(active.suspended);
  return (
    <div className="debug-toolbar" role="toolbar" aria-label="Debugger controls">
      <span className="debug-grip" aria-hidden="true" />
      {paused ? (
        <button className="icon-button" onClick={() => void debug.step("continue")} title="Continue (F5)" aria-label="Continue">
          <Play size={14} aria-hidden="true" />
        </button>
      ) : (
        <button className="icon-button" onClick={() => void debug.step("pause")} title="Pause" aria-label="Pause">
          <Pause size={14} aria-hidden="true" />
        </button>
      )}
      <button className="icon-button" disabled={!paused} onClick={() => void debug.step("next")} title="Step over (F10)" aria-label="Step over">
        <StepForward size={14} aria-hidden="true" />
      </button>
      <button className="icon-button" disabled={!paused} onClick={() => void debug.step("stepIn")} title="Step into (F11)" aria-label="Step into">
        <ArrowDownToLine size={14} aria-hidden="true" />
      </button>
      <button className="icon-button" disabled={!paused} onClick={() => void debug.step("stepOut")} title="Step out (Shift+F11)" aria-label="Step out">
        <ArrowUpFromLine size={14} aria-hidden="true" />
      </button>
      <button className="icon-button debug-stop" onClick={() => void debug.stop()} title="Stop debugging (Shift+F5)" aria-label="Stop debugging">
        <Square size={13} aria-hidden="true" />
      </button>
    </div>
  );
}

/** Debug console panel tab: adapter output plus evaluation in the selected frame. */
export function DebugConsole({ debug }: { debug: Debugger }) {
  const paused = Boolean(debug.active?.suspended);
  const [draft, setDraft] = useState("");
  const [lines, setLines] = useState<{ input?: string; output: string; error?: boolean }[]>([]);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [debug.console.length, lines.length]);
  useEffect(() => {
    if (!debug.active) setLines([]);
  }, [debug.active?.session_id]);
  return (
    <div className="dock-panel debug-console">
      <div className="debug-console-lines" role="log" aria-label="Debug console output">
        {debug.console.length === 0 && lines.length === 0 && (
          <p className="dock-empty-line">{debug.active ? "Adapter output and evaluations appear here." : "Start debugging to see adapter output here."}</p>
        )}
        {debug.console.map((line, index) => (
          <pre key={index} data-category={line.category}>{line.output}</pre>
        ))}
        {lines.map((line, index) => (
          <pre key={`repl-${index}`} data-category={line.error ? "stderr" : "repl"}>
            {line.input !== undefined && <span className="muted">› {line.input}{"\n"}</span>}
            {line.output}
          </pre>
        ))}
        <div ref={end} />
      </div>
      <form
        className="debug-console-input"
        onSubmit={(event) => {
          event.preventDefault();
          const expression = draft.trim();
          if (!expression) return;
          setDraft("");
          void debug
            .evaluate(expression)
            .then((body) => setLines((current) => [...current, { input: expression, output: body.result }]))
            .catch((error) => setLines((current) => [...current, { input: expression, output: error instanceof Error ? error.message : String(error), error: true }]));
        }}
      >
        <span aria-hidden="true">›</span>
        <input
          aria-label="Debug console input"
          placeholder={paused ? "Evaluate an expression in the selected frame" : "Pause the program to evaluate"}
          disabled={!paused}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
      </form>
    </div>
  );
}

function VariableTree({
  name,
  reference,
  variables,
  expand,
  root = false,
  depth = 0,
}: {
  name: string;
  reference: number;
  variables: Record<number, Variable[]>;
  expand: (reference: number) => Promise<void>;
  root?: boolean;
  depth?: number;
}) {
  const [open, setOpen] = useState(root);
  const children = variables[reference];
  useEffect(() => {
    if (open && reference && !children) void expand(reference);
  }, [open, reference, children, expand]);
  return (
    <div className="variable-node">
      <button className="variable-row" style={{ paddingLeft: 4 + depth * 12 }} onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        <span className="variable-scope">{name}</span>
      </button>
      {open && (
        <ul className="variable-list">
          {(children || []).map((item) => (
            <li key={item.name}>
              {item.variablesReference > 0 ? (
                <VariableTree name={`${item.name} = ${item.value}`} reference={item.variablesReference} variables={variables} expand={expand} depth={depth + 1} />
              ) : (
                <div className="variable-leaf" style={{ paddingLeft: 20 + (depth + 1) * 12 }}>
                  <code className="variable-name">{item.name}</code>
                  <span className="variable-value" data-type={item.type || undefined}>{item.value}</span>
                </div>
              )}
            </li>
          ))}
          {children && children.length === 0 && <li className="side-note">Empty</li>}
          {!children && <li className="side-note">Loading…</li>}
        </ul>
      )}
    </div>
  );
}
