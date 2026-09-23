import { lazy, Suspense, useEffect, useState } from "react";
import { CheckCircle2, CircleSlash, Loader2, XCircle } from "lucide-react";
import type { OutputChannel } from "../../services/studioOutput";
import { TaskResult } from "../../components/TaskResult";
import { ProgramInput } from "./ProgramInput";
import { elapsed, jobTitle } from "./studioModel";
import type { Job, TestsReport } from "./tooling";
const Output = lazy(() => import("../Output"));

// Output panel tab: a channel select, then — for build and test jobs — a job
// header built from the job record (state, exit code, timing, counts), then
// the raw read-only output. Success or failure is the recorded exit state,
// never inferred from stderr.
export function OutputView({
  channels,
  selected,
  select,
  text,
  jobs,
  tests,
  workspaceId,
  report,
  showProblems,
  rebuild,
}: {
  channels: OutputChannel[];
  selected: string;
  select: (id: string) => void;
  text: string;
  jobs: Record<string, Job>;
  tests: TestsReport | null;
  workspaceId: string;
  report: (error: unknown) => void;
  showProblems: () => void;
  rebuild?: () => void;
}) {
  const channel = channels.find((c) => c.id === selected);
  const job = channel?.id.startsWith("job:") ? jobs[channel.id.slice(4)] : undefined;
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (job?.state !== "running") return;
    const timer = setInterval(() => setNow(Date.now() / 1000), 500);
    return () => clearInterval(timer);
  }, [job?.state]);
  const heading = job ? jobTitle(job) : null;
  const testSummary = job && (job.kind === "test" || job.kind === "test-list") && tests?.job_id === job.id ? tests.summary : job?.summary;
  const diagnostics = Array.isArray(job?.diagnostics) ? (job!.diagnostics as { severity?: string }[]) : [];
  const errors = diagnostics.filter((d) => d.severity === "error").length;
  const warnings = diagnostics.filter((d) => d.severity === "warning").length;
  return (
    <div className="dock-panel output-panel">
      <div className="dock-toolbar output-header">
        <label className="output-channel">
          <span className="sr-only">Output channel</span>
          <select aria-label="Output channel" value={selected} onChange={(e) => select(e.target.value)}>
            {!channels.length && <option value="">No output yet</option>}
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <span className="small muted" title="Output is read-only and shows authorised runs, builds and tests">
          Read-only
        </span>
      </div>
      {job && heading && (
        <div className="job-header" data-tone={heading.tone} role="status">
          {heading.tone === "running" ? (
            <Loader2 size={15} className="spin" aria-hidden="true" />
          ) : heading.tone === "success" ? (
            <CheckCircle2 size={15} aria-hidden="true" />
          ) : heading.tone === "error" ? (
            <XCircle size={15} aria-hidden="true" />
          ) : (
            <CircleSlash size={15} aria-hidden="true" />
          )}
          <strong>{heading.title}</strong>
          {testSummary ? (
            <span className="ws-pill" data-tone={testSummary.failed ? "error" : "success"}>
              {testSummary.passed} passed · {testSummary.failed} failed · {testSummary.skipped} skipped
            </span>
          ) : diagnostics.length ? (
            <span className="ws-pill" data-tone={errors ? "error" : "warning"}>
              {errors} {errors === 1 ? "error" : "errors"} · {warnings} {warnings === 1 ? "warning" : "warnings"}
            </span>
          ) : null}
          <span className="job-facts">
            {job.label && <span>{job.label}</span>}
            {job.started_at ? <span>Elapsed {elapsed(job.started_at, job.ended_at, now)}</span> : null}
            {job.exit_code !== null && job.exit_code !== undefined && <span>Exit code {job.exit_code}</span>}
          </span>
          <span className="job-actions">
            {diagnostics.length > 0 && (
              <button className="compact quiet" onClick={showProblems}>
                Show in Problems
              </button>
            )}
            {rebuild && job.kind === "build" && job.state !== "running" && (
              <button className="compact quiet" onClick={rebuild}>
                Rebuild
              </button>
            )}
          </span>
          {job.state === "running" && <span className="progress-line" aria-hidden="true" />}
        </div>
      )}
      {channel?.validation && <TaskResult value={channel.validation} />}
      <Suspense fallback={<p className="dock-empty-line">Loading output…</p>}>
        <Output text={text} />
      </Suspense>
      {channel && channel.runState === "running" && channel.acceptsInput && (
        <ProgramInput key={selected} workspaceId={workspaceId} sessionId={selected} report={report} />
      )}
    </div>
  );
}
