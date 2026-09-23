import { useEffect, useRef, useState } from "react";
import { FilePlus } from "lucide-react";
import { Sheet } from "../components/Sheet";
import { call } from "../services/api";
export function NewFile({
  workspaceId,
  created,
  report,
  openSignal = 0,
}: {
  workspaceId: string;
  created: (path: string) => Promise<void>;
  report: (e: unknown) => void;
  /** Bumped by the command palette to open the dialog. */
  openSignal?: number;
}) {
  const [open, setOpen] = useState(false),
    [path, setPath] = useState(""),
    [busy, setBusy] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    if (openSignal) setOpen(true);
  }, [openSignal]);
  return (
    <>
      <button className="icon-button" aria-label="New File" title="New file" onClick={() => setOpen(true)}>
        <FilePlus size={13} aria-hidden="true" />
      </button>
      <Sheet
        centered
        open={open}
        onOpenChange={setOpen}
        title="New source file"
        description="Choose a path inside this project. Nested folders are created as needed."
      >
        <form
          className="project-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (pending.current) return;
            pending.current = true;
            setBusy(true);
            void call("studio.create", { workspace_id: workspaceId, path })
              .then(() => created(path))
              .then(() => {
                setOpen(false);
                setPath("");
              })
              .catch(report)
              .finally(() => {
                pending.current = false;
                setBusy(false);
              });
          }}
        >
          <label>
            File path
            <input
              required
              value={path}
              onChange={(e) => setPath(e.target.value)}
              maxLength={500}
              placeholder="Helper.java"
            />
          </label>
          <button className="primary" disabled={busy || !path.trim()}>
            Create File
          </button>
        </form>
      </Sheet>
    </>
  );
}
