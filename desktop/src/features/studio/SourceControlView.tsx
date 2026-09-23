import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ChevronRight, FileDiff, GitBranch, History, Plus, RefreshCw, X } from "lucide-react";
import { call } from "../../services/api";
import { fileDiff, gitGroups, type GitEntry } from "./studioModel";

export interface GitStatus {
  branch: string;
  entries: GitEntry[];
}

/** Git status for a workspace, re-read on open, after Git actions and when
 *  the window regains focus. Status is a read: no approval. Folders that were
 *  not Git repositories when approved are not polled; the Source Control view
 *  can still check again on request. */
export function useGitStatus(workspaceId: string, enabled: boolean, repository: boolean) {
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);
  const read = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      setStatus(await call<GitStatus>("studio.git", { workspace_id: workspaceId, action: "status" }));
      setError("");
    } catch (e) {
      setStatus(null);
      setError(e instanceof Error ? e.message : "Git status is unavailable.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);
  const automatic = enabled && (repository || checked);
  const refresh = useCallback(async () => {
    setChecked(true);
    await read();
  }, [read]);
  useEffect(() => {
    setStatus(null);
    setError("");
    setChecked(false);
  }, [workspaceId]);
  useEffect(() => {
    if (!automatic) return;
    void read();
    const focus = () => void read();
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [automatic, read]);
  return { status, error, loading, refresh, repository: repository || checked };
}

// Studio V2 §6.3 on the existing Git operations. Stage and Commit go through
// the approval dialog outside the model; nothing here runs Git silently.
// Unstage, discard, stash, push, pull and hosted Git do not exist, so they
// are not offered.
export function SourceControlView({
  workspaceId,
  activePath,
  git,
  report,
  beforeMutation,
  openFile,
}: {
  workspaceId: string;
  activePath: string;
  git: ReturnType<typeof useGitStatus>;
  report: (error: unknown) => void;
  beforeMutation: () => Promise<void>;
  openFile: (path: string) => void;
}) {
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [diff, setDiff] = useState<{ path: string; text: string; staged: boolean } | null>(null);
  const [commits, setCommits] = useState<{ hash: string; short_hash: string; subject: string; author: string; date: string }[] | null>(null);
  const [branches, setBranches] = useState<{ name: string; current: boolean }[] | null>(null);
  const [branchName, setBranchName] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const groups = useMemo(() => gitGroups(git.status?.entries || []), [git.status]);
  const operation = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setNotice("Waiting for your approval before Git runs.");
    try {
      await fn();
      setNotice(done);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "The Git operation could not complete.");
      report(e);
    } finally {
      setBusy(false);
      await git.refresh();
    }
  };
  const stage = (files: string[]) =>
    operation(() => call("studio.git", { workspace_id: workspaceId, action: "add", files }), files.length === 1 ? `${files[0]} staged.` : "Changes staged.");
  const showDiff = async (path: string, staged: boolean) => {
    try {
      const value = await call<{ diff: string }>("studio.git", { workspace_id: workspaceId, action: "diff", ...(staged ? { staged: true } : {}) });
      setDiff({ path, staged, text: fileDiff(value.diff, path) || "No textual difference is available for this file (it may be new, binary or untracked)." });
    } catch (e) {
      report(e);
    }
  };
  useEffect(() => {
    setDiff(null);
    setCommits(null);
    setBranches(null);
    setNotice("");
  }, [workspaceId]);
  const section = (id: string, title: string, count: number, body: React.ReactNode, action?: React.ReactNode) => (
    <div className="side-section" key={id}>
      <div className="side-section-head">
        <button
          className="side-section-toggle"
          aria-expanded={!collapsed[id]}
          onClick={() => setCollapsed((c) => ({ ...c, [id]: !c[id] }))}
        >
          {collapsed[id] ? <ChevronRight size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
          <span>{title}</span>
          {count > 0 && <span className="count" data-tone="neutral" aria-hidden="true">{count}</span>}
        </button>
        {action}
      </div>
      {!collapsed[id] && body}
    </div>
  );
  const row = (change: { path: string; letter: string; label: string }, staged: boolean) => {
    const name = change.path.split("/").pop();
    const folder = change.path.split("/").slice(0, -1).join("/");
    return (
      <li className="scm-row" key={`${staged}:${change.path}`} data-letter={change.letter}>
        <button className="scm-file" title={change.path} onClick={() => void showDiff(change.path, staged)} aria-label={`${name}, ${change.label}${staged ? ", staged" : ""}. Open changes`}>
          <span className="scm-name">{name}</span>
          {folder && <span className="scm-folder">{folder}</span>}
        </button>
        <span className="scm-actions">
          {change.letter !== "D" && (
            <button className="icon-button" aria-label={`Open ${name}`} title="Open file" onClick={() => openFile(change.path)}>
              <FileDiff size={13} aria-hidden="true" />
            </button>
          )}
          {!staged && (
            <button className="icon-button" aria-label={`Stage ${change.path}`} title="Stage (asks for approval)" disabled={busy} onClick={() => void stage([change.path])}>
              <Plus size={14} aria-hidden="true" />
            </button>
          )}
        </span>
        <span className="scm-letter" title={change.label} aria-hidden="true">{change.letter}</span>
      </li>
    );
  };
  return (
    <div className="sidebar-view scm-view">
      <div className="side-head">
        <h2>Source Control</h2>
        <button className="icon-button" aria-label="Refresh Git status" title="Refresh" disabled={git.loading} onClick={() => void git.refresh()}>
          <RefreshCw size={14} aria-hidden="true" className={git.loading ? "spin" : undefined} />
        </button>
        <button
          className="icon-button"
          aria-label="Recent commits"
          title="Show recent commits"
          onClick={() =>
            void call<{ commits: typeof commits }>("studio.git", { workspace_id: workspaceId, action: "log", limit: 30 })
              .then((value) => setCommits(value.commits || []))
              .catch(report)
          }
        >
          <History size={14} aria-hidden="true" />
        </button>
      </div>
      {!git.repository && !git.status && !git.error ? (
        <div className="empty-state">
          <GitBranch size={20} aria-hidden="true" />
          <strong>No Git repository</strong>
          <p>This folder was not a Git repository when it was approved. Studio does not initialise repositories.</p>
          <div className="row">
            <button className="compact" onClick={() => void git.refresh()}>Check again</button>
          </div>
        </div>
      ) : git.error ? (
        <div className="empty-state">
          <GitBranch size={20} aria-hidden="true" />
          <strong>Source control is unavailable</strong>
          <p>{git.error}</p>
          <div className="row">
            <button className="compact" onClick={() => void git.refresh()}>Try again</button>
          </div>
        </div>
      ) : !git.status ? (
        <p className="side-note" role="status">Reading Git status…</p>
      ) : (
        <div className="side-scroll">
          <div className="scm-branch">
            <GitBranch size={14} aria-hidden="true" />
            <strong>{git.status.branch || "detached"}</strong>
            <button
              className="text-button compact"
              aria-expanded={branches !== null}
              onClick={() =>
                branches
                  ? setBranches(null)
                  : void call<{ branches: { name: string; current: boolean }[] }>("studio.git", { workspace_id: workspaceId, action: "branch_list" })
                      .then((value) => setBranches(value.branches || []))
                      .catch(report)
              }
            >
              Branches
            </button>
          </div>
          {branches && (
            <div className="scm-branches">
              <ul aria-label="Branches">
                {branches.map((b) => (
                  <li key={b.name}>
                    <button className="scm-branch-row" aria-current={b.current || undefined} onClick={() => setBranchName(b.name)}>
                      {b.current ? <Check size={12} aria-hidden="true" /> : <span className="scm-branch-pad" />}
                      {b.name}
                    </button>
                  </li>
                ))}
              </ul>
              <label className="side-field">
                <span>Branch name</span>
                <input aria-label="Branch name" value={branchName} maxLength={128} onChange={(e) => setBranchName(e.target.value)} />
              </label>
              <div className="row">
                <button
                  className="compact"
                  disabled={busy || !branchName.trim()}
                  onClick={() =>
                    void operation(async () => {
                      await beforeMutation();
                      return call("studio.git", { workspace_id: workspaceId, action: "create_branch", name: branchName });
                    }, "Branch created. Compare open files with disk before editing further.")
                  }
                >
                  Review new branch
                </button>
                <button
                  className="compact"
                  disabled={busy || !branchName.trim()}
                  onClick={() =>
                    void operation(async () => {
                      await beforeMutation();
                      return call("studio.git", { workspace_id: workspaceId, action: "checkout", name: branchName });
                    }, "Branch switched. Compare open files with disk before editing further.")
                  }
                >
                  Review branch switch
                </button>
              </div>
            </div>
          )}
          <textarea
            className="scm-message"
            aria-label="Commit message"
            placeholder={`Message (Ctrl+Enter to commit on ${git.status.branch || "this branch"})`}
            value={message}
            maxLength={2000}
            rows={2}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.ctrlKey && message.trim() && groups.staged.length && !busy) {
                e.preventDefault();
                (e.currentTarget.parentElement?.querySelector(".scm-commit") as HTMLButtonElement | null)?.click();
              }
            }}
          />
          <button
            className="primary scm-commit"
            disabled={busy || !message.trim() || !groups.staged.length}
            title={groups.staged.length ? `Commit ${groups.staged.length} staged ${groups.staged.length === 1 ? "file" : "files"}` : "Stage changes before committing"}
            onClick={() =>
              void operation(
                () => call("studio.git", { workspace_id: workspaceId, action: "commit", message }),
                "Staged changes committed.",
              ).then(() => setMessage(""))
            }
          >
            <Check size={14} aria-hidden="true" />
            Review commit
          </button>
          <p className="side-note">
            {groups.staged.length
              ? `${groups.staged.length} staged ${groups.staged.length === 1 ? "file" : "files"}. `
              : ""}
            Stage and Commit ask for your approval before Git runs.
          </p>
          <p className="side-note" role="status">{notice}</p>
          {activePath && (
            <button className="compact quiet scm-stage-current" disabled={busy} onClick={() => void stage([activePath])}>
              Review staging selected file
            </button>
          )}
          {section("staged", "Staged changes", groups.staged.length, (
            groups.staged.length ? <ul className="scm-list" aria-label="Staged changes">{groups.staged.map((c) => row(c, true))}</ul> : <p className="side-note">Nothing staged.</p>
          ))}
          {section(
            "changes",
            "Changes",
            groups.changes.length,
            groups.changes.length ? (
              <ul className="scm-list" aria-label="Changes">{groups.changes.map((c) => row(c, false))}</ul>
            ) : (
              <p className="side-note">No working tree changes.</p>
            ),
            groups.changes.length > 0 ? (
              <button className="icon-button" aria-label="Stage all changes" title="Stage all (asks for approval)" disabled={busy} onClick={() => void stage(groups.changes.map((c) => c.path))}>
                <Plus size={14} aria-hidden="true" />
              </button>
            ) : undefined,
          )}
          {diff && (
            <div className="scm-diff" aria-label={`Changes in ${diff.path}`} role="region">
              <div className="side-section-head">
                <span className="scm-diff-title">{diff.path} · {diff.staged ? "Staged" : "Working tree"} · read-only</span>
                <button className="icon-button" aria-label="Close diff" onClick={() => setDiff(null)}>
                  <X size={13} aria-hidden="true" />
                </button>
              </div>
              <pre className="diff-text">
                {diff.text.split("\n").map((line, index) => (
                  <span key={index} data-diff={line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : line.startsWith("@@") ? "hunk" : undefined}>
                    {line}
                    {"\n"}
                  </span>
                ))}
              </pre>
            </div>
          )}
          {commits &&
            section(
              "commits",
              "Commits",
              commits.length,
              <ul className="scm-list scm-commits" aria-label="Recent commits">
                {commits.map((c) => (
                  <li key={c.hash} title={`${c.author} · ${c.date}`}>
                    <span className="scm-name">{c.subject}</span>
                    <span className="scm-folder">{c.short_hash}</span>
                  </li>
                ))}
                {!commits.length && <li className="side-note">No commits yet.</li>}
              </ul>,
            )}
        </div>
      )}
    </div>
  );
}
