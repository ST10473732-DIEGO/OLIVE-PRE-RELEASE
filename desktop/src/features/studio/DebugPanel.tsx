import { useEffect, useRef, useState } from "react";
import {
  Bug,
  ChevronDown,
  ChevronRight,
  Pause,
  Play,
  Square,
  StepForward,
  ArrowDownToLine,
  ArrowUpFromLine,
  Plus,
  X,
} from "lucide-react";
import type { Debugger, Variable } from "./debugClient";
import { relativePath } from "./tooling";

// Everything shown here comes from the adapter: frames, scopes, variables and
// evaluation results are fetched live and dropped as soon as execution resumes.
export function DebugPanel({
  debug,
  root,
  launch,
  busy,
  launchable,
}: {
  debug: Debugger;
  root: string;
  launch: () => void;
  busy: boolean;
  launchable: string;
}) {
  const { status, active } = debug;
  const paused = Boolean(active?.suspended);
  const [tab, setTab] = useState<"variables" | "watch" | "console" | "exceptions">("variables");
  const [watchDraft, setWatchDraft] = useState("");
  const [replDraft, setReplDraft] = useState("");
  const [replLines, setReplLines] = useState<{ input?: string; output: string; error?: boolean }[]>([]);
  const consoleEnd = useRef<HTMLDivElement>(null);
  const [filters, setFilters] = useState<string[] | null>(null);
  useEffect(() => {
    consoleEnd.current?.scrollIntoView({ block: "end" });
  }, [debug.console.length, replLines.length]);
  useEffect(() => {
    if (!active) setReplLines([]);
  }, [active?.session_id]);
  const exceptionFilters = active?.exception_filters || [];
  const activeFilters = filters ?? exceptionFilters.filter((f) => f.default).map((f) => f.filter);
  const stateText = !status
    ? "No debug session"
    : status.state === "suspended"
      ? "Paused"
      : status.state === "running"
        ? "Running"
        : status.state === "starting"
          ? "Starting"
          : status.state === "terminated"
            ? `Ended${status.exit_code !== null ? ` · exit ${status.exit_code}` : ""}`
            : status.state === "failed"
              ? `Failed · ${status.detail}`
              : "Stopped";
  return (
    <div className="dock-panel debug-panel">
      <div className="dock-toolbar">
        <div className="row wrap debug-controls" role="group" aria-label="Debugger controls">
          {!active ? (
            <button className="primary-action quiet" disabled={busy || !launchable} onClick={launch} title={launchable || "Nothing to debug"}>
              <Bug size={14} aria-hidden="true" />
              Start debugging
            </button>
          ) : (
            <>
              {paused ? (
                <button className="quiet" onClick={() => void debug.step("continue")} title="Continue (F5)" aria-label="Continue">
                  <Play size={14} aria-hidden="true" />
                  Continue
                </button>
              ) : (
                <button className="quiet" onClick={() => void debug.step("pause")} title="Pause" aria-label="Pause">
                  <Pause size={14} aria-hidden="true" />
                  Pause
                </button>
              )}
              <button className="quiet" disabled={!paused} onClick={() => void debug.step("next")} title="Step over (F10)" aria-label="Step over">
                <StepForward size={14} aria-hidden="true" />
                Step over
              </button>
              <button className="quiet" disabled={!paused} onClick={() => void debug.step("stepIn")} title="Step into (F11)" aria-label="Step into">
                <ArrowDownToLine size={14} aria-hidden="true" />
                Step into
              </button>
              <button className="quiet" disabled={!paused} onClick={() => void debug.step("stepOut")} title="Step out (Shift+F11)" aria-label="Step out">
                <ArrowUpFromLine size={14} aria-hidden="true" />
                Step out
              </button>
              <button className="danger-action quiet" onClick={() => void debug.stop()} title="Stop debugging (Shift+F5)" aria-label="Stop debugging">
                <Square size={14} aria-hidden="true" />
                Stop
              </button>
            </>
          )}
        </div>
        <span className="small debug-state" data-state={status?.state || "none"} role="status">
          {stateText}
          {status && <span className="muted"> · {status.provider}</span>}
        </span>
      </div>
      <div className="debug-body">
        <section className="debug-stack" aria-label="Call stack">
          <h4>Call stack</h4>
          {!paused ? (
            <p className="small muted">{active ? "Pause or hit a breakpoint to inspect frames." : "Set breakpoints in the gutter, then start debugging."}</p>
          ) : (
            <ul>
              {debug.frames.map((frame) => (
                <li key={frame.id}>
                  <button
                    className={`frame-row ${debug.frameId === frame.id ? "selected" : ""}`}
                    onClick={() => void debug.selectFrame(frame)}
                    aria-current={debug.frameId === frame.id ? "true" : undefined}
                  >
                    <span className="frame-name">{frame.name}</span>
                    {frame.source?.path && (
                      <span className="small muted">
                        {relativePath(root, frame.source.path)}:{frame.line}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="debug-inspect" aria-label="Inspection">
          <div className="category-tabs small">
            {(["variables", "watch", "console", "exceptions"] as const).map((name) => (
              <button key={name} className={tab === name ? "selected" : ""} onClick={() => setTab(name)} aria-pressed={tab === name}>
                {name === "variables" ? "Variables" : name === "watch" ? "Watch" : name === "console" ? "Debug console" : "Exceptions"}
              </button>
            ))}
          </div>
          <div hidden={tab !== "variables"} className="debug-tab">
            {paused ? (
              debug.scopes.map((scope) => (
                <VariableTree
                  key={scope.variablesReference}
                  name={scope.name}
                  reference={scope.variablesReference}
                  variables={debug.variables}
                  expand={debug.expand}
                  root
                />
              ))
            ) : (
              <p className="small muted">Locals appear while the program is paused.</p>
            )}
          </div>
          <div hidden={tab !== "watch"} className="debug-tab">
            <form
              className="row"
              onSubmit={(event) => {
                event.preventDefault();
                if (watchDraft.trim()) debug.addWatch(watchDraft.trim());
                setWatchDraft("");
              }}
            >
              <input aria-label="Watch expression" placeholder="Expression to watch" value={watchDraft} onChange={(e) => setWatchDraft(e.target.value)} />
              <button type="submit" className="quiet" aria-label="Add watch">
                <Plus size={14} aria-hidden="true" />
              </button>
            </form>
            <ul className="watch-list">
              {debug.watches.map((expression) => {
                const result = debug.watchResults.find((item) => item.expression === expression);
                return (
                  <li key={expression}>
                    <code>{expression}</code>
                    <span className={result?.error ? "muted" : ""}>
                      {result ? (result.error ? `— ${result.error}` : result.result) : paused ? "…" : "— not paused"}
                    </span>
                    <button className="icon-button" aria-label={`Remove watch ${expression}`} onClick={() => debug.removeWatch(expression)}>
                      <X size={12} aria-hidden="true" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          <div hidden={tab !== "console"} className="debug-tab debug-console">
            <div className="debug-console-lines">
              {debug.console.map((line, index) => (
                <pre key={index} data-category={line.category}>{line.output}</pre>
              ))}
              {replLines.map((line, index) => (
                <pre key={`repl-${index}`} data-category={line.error ? "stderr" : "repl"}>
                  {line.input !== undefined && <span className="muted">› {line.input}\n</span>}
                  {line.output}
                </pre>
              ))}
              <div ref={consoleEnd} />
            </div>
            <form
              className="row"
              onSubmit={(event) => {
                event.preventDefault();
                const expression = replDraft.trim();
                if (!expression) return;
                setReplDraft("");
                void debug
                  .evaluate(expression)
                  .then((body) => setReplLines((lines) => [...lines, { input: expression, output: body.result }]))
                  .catch((error) =>
                    setReplLines((lines) => [...lines, { input: expression, output: error instanceof Error ? error.message : String(error), error: true }]),
                  );
              }}
            >
              <input
                aria-label="Debug console input"
                placeholder={paused ? "Evaluate an expression" : "Pause the program to evaluate"}
                disabled={!paused}
                value={replDraft}
                onChange={(e) => setReplDraft(e.target.value)}
              />
            </form>
          </div>
          <div hidden={tab !== "exceptions"} className="debug-tab">
            {exceptionFilters.length === 0 ? (
              <p className="small muted">{active ? "This adapter offers no exception filters." : "Start a session to choose exception filters."}</p>
            ) : (
              <ul className="watch-list">
                {exceptionFilters.map((item) => (
                  <li key={item.filter}>
                    <label className="small">
                      <input
                        type="checkbox"
                        checked={activeFilters.includes(item.filter)}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...activeFilters, item.filter]
                            : activeFilters.filter((value) => value !== item.filter);
                          setFilters(next);
                          void debug.setExceptionFilters(next);
                        }}
                      />
                      {item.label || item.filter}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
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
    <div className="variable-node" style={{ paddingLeft: depth * 12 }}>
      <button className="variable-row" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        <strong>{name}</strong>
      </button>
      {open && (
        <ul className="variable-list">
          {(children || []).map((item) => (
            <li key={item.name}>
              {item.variablesReference > 0 ? (
                <VariableTree
                  name={`${item.name} = ${item.value}`}
                  reference={item.variablesReference}
                  variables={variables}
                  expand={expand}
                  depth={depth + 1}
                />
              ) : (
                <div className="variable-leaf" style={{ paddingLeft: (depth + 1) * 12 }}>
                  <code>{item.name}</code>
                  <span className="variable-value">{item.value}</span>
                  {item.type && <span className="small muted">{item.type}</span>}
                </div>
              )}
            </li>
          ))}
          {children && children.length === 0 && <li className="small muted">Empty</li>}
          {!children && <li className="small muted">Loading…</li>}
        </ul>
      )}
    </div>
  );
}
