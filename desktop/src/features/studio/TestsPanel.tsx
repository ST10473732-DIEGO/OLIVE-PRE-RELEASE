import { useMemo, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  MinusCircle,
  Play,
  RotateCcw,
  ListTree,
  Square,
} from "lucide-react";
import { call } from "../../services/api";
import { useTooling, type Job, type TestResult } from "./tooling";

// Structured test results only: TRX from the .NET runner, JSON from the
// Python runner. Nothing here is inferred from console text.
export function TestsPanel({
  workspaceId,
  structured,
  openFile,
  report,
  legacyRun,
}: {
  workspaceId: string;
  structured: boolean;
  openFile: (path: string, line?: number) => void;
  report: (error: unknown) => void;
  legacyRun: () => void;
}) {
  const slice = useTooling(workspaceId);
  const jobs = Object.values(slice.jobs);
  const running = jobs.find((job) => job.state === "running" && (job.kind === "test" || job.kind === "test-list"));
  const latest = [...jobs].filter((job) => job.kind === "test").sort((a, b) => a.started_at - b.started_at).at(-1);
  const results = slice.tests?.job_id === latest?.id ? slice.tests : slice.tests;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string>("");
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const rows = useMemo(() => {
    const list = results?.results || [];
    const order = { failed: 0, passed: 1, skipped: 2 } as Record<string, number>;
    return [...list]
      .filter((item) => filter === "all" || item.state === "failed")
      .sort((a, b) => (order[a.state] ?? 3) - (order[b.state] ?? 3) || a.full_name.localeCompare(b.full_name));
  }, [results, filter]);
  const run = async (filters: string[] = [], listOnly = false) => {
    try {
      await call<Job>("project.test", {
        workspace_id: workspaceId,
        filters,
        list_only: listOnly,
      });
    } catch (error) {
      report(error);
    }
  };
  const cancel = async () => {
    if (!running) return;
    try {
      await call("project.cancel", { job_id: running.id });
    } catch (error) {
      report(error);
    }
  };
  const toggle = (name: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  const summary = results?.summary;
  return (
    <div className="dock-panel tests-panel">
      <div className="dock-toolbar">
        <div className="row wrap">
          {structured ? (
            <>
              <button className="quiet" disabled={Boolean(running)} onClick={() => void run()} title="Run every test in the workspace">
                <Play size={14} aria-hidden="true" />
                Run all
              </button>
              <button
                className="quiet"
                disabled={Boolean(running) || !results?.results.some((item) => item.state === "failed")}
                onClick={() => void run(results!.results.filter((item) => item.state === "failed").map((item) => item.full_name))}
                title="Re-run only the tests that failed last time"
              >
                <RotateCcw size={14} aria-hidden="true" />
                Run failed
              </button>
              <button
                className="quiet"
                disabled={Boolean(running) || selected.size === 0}
                onClick={() => void run([...selected])}
                title="Run the ticked tests"
              >
                <Play size={14} aria-hidden="true" />
                Run selected ({selected.size})
              </button>
              <button className="quiet" disabled={Boolean(running)} onClick={() => void run([], true)} title="List tests without running them">
                <ListTree size={14} aria-hidden="true" />
                Discover
              </button>
            </>
          ) : (
            <button className="quiet" onClick={legacyRun} title="Run the detected test command">
              <Play size={14} aria-hidden="true" />
              Run tests
            </button>
          )}
          {running && (
            <button className="danger-action quiet" onClick={() => void cancel()}>
              <Square size={14} aria-hidden="true" />
              Stop {running.label.toLowerCase()}
            </button>
          )}
        </div>
        <div className="row">
          {summary && (
            <span className="small test-summary" role="status">
              <span data-state="passed">{summary.passed} passed</span>
              <span data-state="failed">{summary.failed} failed</span>
              <span data-state="skipped">{summary.skipped} skipped</span>
              <span className="muted">{summary.duration_seconds.toFixed(2)} s</span>
            </span>
          )}
          {results && results.results.some((item) => item.state === "failed") && (
            <label className="small">
              <input type="checkbox" checked={filter === "failed"} onChange={(e) => setFilter(e.target.checked ? "failed" : "all")} />
              Failed only
            </label>
          )}
        </div>
      </div>
      {running && (
        <p className="small muted dock-note" role="status">
          {running.label}… <code>{running.command.join(" ")}</code>
        </p>
      )}
      {latest?.error && !running && (
        <p className="small dock-note" role="alert">
          {latest.error}
        </p>
      )}
      {!results && !running && (
        <div className="dock-empty">
          {slice.discovered ? (
            <ul className="test-list" aria-label="Discovered tests">
              {slice.discovered.map((test) => (
                <li key={test.full_name}>
                  <label className="test-row">
                    <input type="checkbox" checked={selected.has(test.full_name)} onChange={() => toggle(test.full_name)} />
                    <MinusCircle size={14} aria-hidden="true" />
                    <span className="test-name" title={test.full_name}>{test.full_name}</span>
                    <button className="quiet small" onClick={() => void run([test.full_name])}>Run</button>
                  </label>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              {structured
                ? "No test run yet. Run all, or discover the tests first and run a selection."
                : "Test output and results from the detected test command appear in Output; use Run tests to start one."}
            </p>
          )}
        </div>
      )}
      {results && !running && (
        <ul className="test-list" aria-label="Test results">
          {rows.map((item) => (
            <TestRow
              key={item.full_name}
              item={item}
              checked={selected.has(item.full_name)}
              toggle={() => toggle(item.full_name)}
              expanded={expanded === item.full_name}
              expand={() => setExpanded(expanded === item.full_name ? "" : item.full_name)}
              openFile={openFile}
              run={() => void run([item.full_name])}
            />
          ))}
          {rows.length === 0 && <li className="muted small dock-note">No tests match.</li>}
        </ul>
      )}
    </div>
  );
}
function TestRow({
  item,
  checked,
  toggle,
  expanded,
  expand,
  openFile,
  run,
}: {
  item: TestResult;
  checked: boolean;
  toggle: () => void;
  expanded: boolean;
  expand: () => void;
  openFile: (path: string, line?: number) => void;
  run: () => void;
}) {
  const location = item.relative_file || item.file;
  return (
    <li data-state={item.state} className="test-item">
      <div className="test-row">
        <input type="checkbox" aria-label={`Select ${item.name}`} checked={checked} onChange={toggle} />
        {item.state === "passed" ? (
          <CheckCircle2 size={14} aria-hidden="true" />
        ) : item.state === "failed" ? (
          <XCircle size={14} aria-hidden="true" />
        ) : (
          <MinusCircle size={14} aria-hidden="true" />
        )}
        <button className="test-name" onClick={expand} title={item.full_name} aria-expanded={expanded}>
          {item.full_name}
        </button>
        <span className="small muted test-duration">{(item.duration_seconds * 1000).toFixed(0)} ms</span>
        {location && (
          <button
            className="quiet small"
            onClick={() => openFile(location, item.line || undefined)}
            title={`Open ${location}${item.line ? ":" + item.line : ""}`}
          >
            Source
          </button>
        )}
        <button className="quiet small" onClick={run}>Run</button>
      </div>
      {(expanded || item.state === "failed") && (item.message || item.stack_trace) && (
        <div className="test-detail">
          {item.message && <pre className="test-message">{item.message}</pre>}
          {expanded && item.stack_trace && <pre className="test-stack small">{item.stack_trace}</pre>}
          {!expanded && item.stack_trace && (
            <button className="text-button small" onClick={expand}>
              Show stack trace
            </button>
          )}
        </div>
      )}
    </li>
  );
}
