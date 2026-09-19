import { useState } from "react";
import { call } from "../../services/api";
import { Details } from "../../components/WorkspacePage";
export function GitPanel({
  workspaceId,
  path,
  report,
  beforeMutation,
}: {
  workspaceId: string;
  path: string;
  report: (e: unknown) => void;
  beforeMutation: () => Promise<void>;
}) {
  const [status, setStatus] = useState<{
    branch: string;
    entries: { path: string; index: string; worktree: string }[];
  }>();
  const [details, setDetails] = useState<{
    commits?: {
      hash: string;
      short_hash: string;
      subject: string;
      author: string;
      date: string;
    }[];
    branches?: { name: string; current: boolean }[];
  }>();
  const [diff, setDiff] = useState("");
  const [message, setMessage] = useState("");
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const operation = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setNotice("Working. Review any requested approval before continuing.");
    try {
      await fn();
      setNotice(message);
    } catch (e) {
      setNotice(
        e instanceof Error
          ? e.message
          : "The Git operation could not complete.",
      );
      report(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <h3>Repository changes</h3>
      <p role="status">{notice}</p>
      <div className="row">
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () =>
                setStatus(
                  await call("studio.git", {
                    workspace_id: workspaceId,
                    action: "status",
                  }),
                ),
              "Status loaded.",
            )
          }
        >
          Refresh Git status
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () =>
                setDiff(
                  (
                    await call<{ diff: string }>("studio.git", {
                      workspace_id: workspaceId,
                      action: "diff",
                    })
                  ).diff,
                ),
              "Working tree diff loaded.",
            )
          }
        >
          Working changes
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () =>
                setDiff(
                  (
                    await call<{ diff: string }>("studio.git", {
                      workspace_id: workspaceId,
                      action: "diff",
                      staged: true,
                    })
                  ).diff,
                ),
              "Staged diff loaded.",
            )
          }
        >
          Staged changes
        </button>
      </div>
      {status && (
        <>
          <p>Branch: {status.branch}</p>
          {status.entries.length ? (
            status.entries.map((entry) => (
              <article className="record-card" key={entry.path}>
                <strong>{entry.path}</strong>
                <p>
                  Index: {entry.index.trim() || "unchanged"} · Working tree:{" "}
                  {entry.worktree.trim() || "unchanged"}
                </p>
              </article>
            ))
          ) : (
            <p>No working tree changes.</p>
          )}
        </>
      )}
      {diff && <pre className="source-text">{diff}</pre>}
      <div className="row">
        <button
          disabled={busy || !path}
          onClick={() =>
            void operation(
              () =>
                call("studio.git", {
                  workspace_id: workspaceId,
                  action: "add",
                  files: [path],
                }),
              "Selected file staged.",
            )
          }
        >
          Review staging selected file
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () =>
                setDetails(
                  await call("studio.git", {
                    workspace_id: workspaceId,
                    action: "log",
                    limit: 30,
                  }),
                ),
              "Recent commits loaded.",
            )
          }
        >
          Recent commits
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () =>
                setDetails(
                  await call("studio.git", {
                    workspace_id: workspaceId,
                    action: "branch_list",
                  }),
                ),
              "Branches loaded.",
            )
          }
        >
          List branches
        </button>
      </div>
      <details>
        <summary>Commit staged changes</summary>
        <label className="field">
          Commit message
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={2000}
          />
        </label>
        <button
          disabled={busy || !message.trim()}
          onClick={() =>
            void operation(
              () =>
                call("studio.git", {
                  workspace_id: workspaceId,
                  action: "commit",
                  message,
                }),
              "Staged changes committed.",
            )
          }
        >
          Review commit
        </button>
      </details>
      <details>
        <summary>Create or switch branch</summary>
        <p>
          Save or discard unsaved buffers first. Existing Git conflict checks
          remain in effect.
        </p>
        <label className="field">
          Branch name
          <input
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            maxLength={128}
          />
        </label>
        <div className="row">
          <button
            disabled={busy || !branch.trim()}
            onClick={() =>
              void operation(async () => {
                await beforeMutation();
                return call("studio.git", {
                  workspace_id: workspaceId,
                  action: "create_branch",
                  name: branch,
                });
              }, "Branch created. Compare open files with disk before editing further.")
            }
          >
            Review new branch
          </button>
          <button
            disabled={busy || !branch.trim()}
            onClick={() =>
              void operation(async () => {
                await beforeMutation();
                return call("studio.git", {
                  workspace_id: workspaceId,
                  action: "checkout",
                  name: branch,
                });
              }, "Branch switched. Compare open files with disk before editing further.")
            }
          >
            Review branch switch
          </button>
        </div>
      </details>
      {details?.commits?.map((commit) => (
        <article className="record-card" key={commit.hash}>
          <strong>{commit.subject}</strong>
          <p>
            {commit.short_hash} · {commit.author} · {commit.date}
          </p>
        </article>
      ))}
      {details?.branches?.map((branch) => (
        <p key={branch.name}>
          {branch.name}
          {branch.current ? " · current" : ""}
        </p>
      ))}
      {details !== undefined && (
        <Details value={details} title="Repository records" />
      )}
    </>
  );
}
