import { useState, useRef } from "react";
import { Sheet } from "../components/Sheet";
import { call } from "../services/api";

export function Packages({
  workspaceId,
  report,
  setOutput,
}: {
  workspaceId: string;
  report: (e: unknown) => void;
  setOutput: (text: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [manager, setManager] = useState<"python" | "node">("python");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Packages</button>
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="Project packages"
        description="Install a library into this workspace without changing OLIVE’s own environment."
      >
        <form
          className="project-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (pending.current) return;
            pending.current = true;
            setBusy(true);
            setOutput("Installing the requested project dependency…");
            void call<{ stdout: string; installed?: boolean }>(
              "studio.install_package",
              { workspace_id: workspaceId, manager, package: name },
            )
              .then((result) => {
                setOutput(result.stdout);
                if (result.installed) setOpen(false);
              })
              .catch(report)
              .finally(() => {
                pending.current = false;
                setBusy(false);
              });
          }}
        >
          <label>
            Package ecosystem
            <select
              value={manager}
              disabled={busy}
              onChange={(e) => setManager(e.target.value as typeof manager)}
            >
              <option value="python">Python · project .venv</option>
              <option value="node">JavaScript / TypeScript · npm</option>
            </select>
          </label>
          <label>
            Package name and optional version
            <input
              required
              disabled={busy}
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={
                manager === "python" ? "requests==2.32.5" : "lodash@4.17.21"
              }
            />
          </label>
          <p className="muted">
            Install downloads the package and its dependencies. Python uses
            wheels in a project virtual environment. npm install scripts are
            disabled. Java uses JAR libraries in the project’s lib folder.
          </p>
          <button className="primary" disabled={busy || !name.trim()}>
            {busy ? "Installing…" : "Install in this project"}
          </button>
          {busy && (
            <button
              type="button"
              onClick={() =>
                void call("studio.cancel_install", {
                  workspace_id: workspaceId,
                }).catch(report)
              }
            >
              Cancel installation
            </button>
          )}
        </form>
      </Sheet>
    </>
  );
}
