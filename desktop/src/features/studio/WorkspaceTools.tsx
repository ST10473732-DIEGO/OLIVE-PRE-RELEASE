import { useState } from "react";
import { call } from "../../services/api";
import { Sheet } from "../../components/Sheet";
import { Details } from "../../components/WorkspacePage";
import { ReviewedCommand } from "./ReviewedCommand";
import { GitPanel } from "./GitPanel";
interface Results {
  session_id: string;
  state: string;
  exit_code: number | null;
  local_url?: string;
  problems: {
    file?: string;
    line?: number;
    message: string;
    severity: string;
  }[];
  tests: { name: string; state: string; message: string }[];
  artifacts: unknown[];
}
export function WorkspaceTools({
  workspaceId,
  path,
  openFile,
  report,
  beforeMutation,
}: {
  workspaceId: string;
  path: string;
  openFile: (path: string, line?: number) => Promise<void>;
  report: (e: unknown) => void;
  beforeMutation: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("Git");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<[string, number, string][]>();
  const [results, setResults] = useState<Results[]>();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [rollback, setRollback] = useState<unknown>();
  const show = (section: string) => {
    setTab(section);
    setOpen(true);
    if (section === "Problems" || section === "Tests") {
      setBusy(true);
      void call<Results[]>("studio.diagnostics", { workspace_id: workspaceId })
        .then(setResults).catch(report).finally(() => setBusy(false));
    }
  };
  const operation = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try {
      await fn();
      setNotice(message);
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button onClick={() => setOpen(true)}>Workspace tools</button>
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="Workspace tools"
        description="Inspect changes, find code, and review real results."
      >
        <div className="category-tabs">
          {["Git", "Find in files", "Results", "Problems", "Tests", "Command", "Checkpoints"].map(
            (name) => (
              <button
                key={name}
                className={tab === name ? "selected" : ""}
                onClick={() => show(name)}
              >
                {name}
              </button>
            ),
          )}
        </div>
        <p role="status">{notice}</p>
        <div hidden={tab !== "Git"}>
          <GitPanel
            workspaceId={workspaceId}
            path={path}
            report={report}
            beforeMutation={beforeMutation}
          />
        </div>
        <div hidden={tab !== "Find in files"}>
          <label className="field">
            Find in workspace
            <input
              aria-label="Find in workspace"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <button
            disabled={busy || !query.trim()}
            onClick={() =>
              void operation(
                async () =>
                  setMatches(
                    (
                      await call<{ matches: [string, number, string][] }>(
                        "studio.search",
                        { workspace_id: workspaceId, query },
                      )
                    ).matches,
                  ),
                "Workspace search finished.",
              )
            }
          >
            Search files
          </button>
          {matches?.map(([file, line, text], index) => (
            <button
              className="record-card"
              key={index}
              onClick={() => {
                setOpen(false);
                void openFile(file, line).catch(report);
              }}
            >
              <strong>
                {file}:{line}
              </strong>
              <pre className="source-text">{text}</pre>
            </button>
          ))}
          {matches?.length === 0 && <p>No matching lines.</p>}
          {matches?.length === 200 && (
            <p>
              Showing the first 200 matches; narrow the query for more detail.
            </p>
          )}
        </div>
        <div hidden={!["Results", "Problems", "Tests"].includes(tab)}>
          <h3>{tab}</h3>
          <button
            disabled={busy}
            onClick={() =>
              void operation(
                async () =>
                  setResults(
                    await call("studio.diagnostics", {
                      workspace_id: workspaceId,
                    }),
                  ),
                "Run and validation results loaded.",
              )
            }
          >
            Refresh results
          </button>
          {results?.map((result) => (
            <article className="record-card" key={result.session_id}>
              <h3>
                {result.state} · Exit {result.exit_code ?? "pending"}
              </h3>
              {tab !== "Tests" && result.problems.map((problem, index) => (
                <div key={index}>
                  <p>
                    {problem.severity}: {problem.message}
                  </p>
                  {problem.file && (
                    <button
                      onClick={() => {
                        setOpen(false);
                        void openFile(problem.file!, problem.line).catch(
                          report,
                        );
                      }}
                    >
                      {problem.file}:{problem.line || 1}
                    </button>
                  )}
                </div>
              ))}
              {tab !== "Problems" && result.tests.map((test, index) => (
                <p key={index}>
                  {test.name} · {test.state} {test.message}
                </p>
              ))}
              <Details value={result.artifacts} title="Artifacts" />
            </article>
          ))}
          {results?.length === 0 && (
            <p>No runs or validation results in this runtime yet.</p>
          )}
        </div>
        <div hidden={tab !== "Command"}>
          <ReviewedCommand workspaceId={workspaceId} report={report} />
        </div>
        <div hidden={tab !== "Checkpoints"}>
          <h3>Undo the latest OLIVE task</h3>
          <p>
            This restores the existing workspace checkpoint through the editing
            service. Save or discard unsaved buffers first, then review the
            action before authorising it.
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void operation(async () => {
                await beforeMutation();
                setRollback(
                  await call("studio.rollback_latest", {
                    workspace_id: workspaceId,
                  }),
                );
              }, "Checkpoint restore finished. Compare open files with disk.")
            }
          >
            Review latest task rollback
          </button>
          {rollback !== undefined && (
            <Details value={rollback} title="Restored files" />
          )}
          <button
            disabled={busy}
            onClick={() =>
              void operation(
                () => call("studio.open_ide", { workspace_id: workspaceId }),
                "Workspace handed to the installed IDE.",
              )
            }
          >
            Review opening installed IDE
          </button>
        </div>
      </Sheet>
    </>
  );
}
