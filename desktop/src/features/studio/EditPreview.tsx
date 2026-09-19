import { useEffect, useState } from "react";
import * as monaco from "monaco-editor";
import { Sheet } from "../../components/Sheet";
import { call } from "../../services/api";
import { toMonacoRange } from "./languageClient";
import { relativePath, type WorkspaceEdit } from "./tooling";

interface FilePreview {
  path: string;
  relative: string;
  include: boolean;
  lines: { line: number; before: string; after: string }[];
  edits: WorkspaceEdit["files"][number]["edits"];
}
// Every workspace edit a language server proposes (rename, code action,
// server command) is shown per file before it touches an editor buffer.
// Applying changes buffers only; saving stays an explicit, hash-checked step.
export function EditPreview({
  edit,
  root,
  workspaceId,
  openModel,
  close,
  report,
}: {
  edit: WorkspaceEdit | null;
  root: string;
  workspaceId: string;
  openModel: (path: string) => Promise<monaco.editor.ITextModel>;
  close: () => void;
  report: (error: unknown) => void;
}) {
  const [files, setFiles] = useState<FilePreview[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!edit) {
      setFiles([]);
      return;
    }
    let live = true;
    void (async () => {
      const previews: FilePreview[] = [];
      for (const file of edit.files) {
        const relative = relativePath(root, file.path);
        let text = "";
        try {
          const existing = monaco.editor.getModel(
            monaco.Uri.parse(`olive-source://workspace/${workspaceId}/${relative}`),
          );
          text = existing
            ? existing.getValue()
            : (await call<{ text: string }>("studio.open", { workspace_id: workspaceId, path: relative })).text;
        } catch (error) {
          report(error);
        }
        const source = text.split(/\r?\n/);
        const lines = file.edits.map((item) => {
          const line = item.range.start.line;
          const before = source[line] ?? "";
          const replaced = applyToLine(source, item);
          return { line: line + 1, before, after: replaced };
        });
        previews.push({ path: file.path, relative, include: true, lines, edits: file.edits });
      }
      if (live) setFiles(previews);
    })();
    return () => {
      live = false;
    };
  }, [edit, root, workspaceId, report]);
  const apply = async () => {
    if (!edit) return;
    setBusy(true);
    try {
      for (const file of files) {
        if (!file.include) continue;
        const model = await openModel(file.relative);
        model.pushEditOperations(
          [],
          file.edits.map((item) => ({ range: toMonacoRange(item.range), text: item.newText })),
          () => null,
        );
      }
      close();
    } catch (error) {
      report(error);
    } finally {
      setBusy(false);
    }
  };
  const total = files.filter((f) => f.include).reduce((sum, f) => sum + f.edits.length, 0);
  return (
    <Sheet
      open={Boolean(edit)}
      onOpenChange={(open) => {
        if (!open) close();
      }}
      title={edit?.label ? `Review: ${edit.label}` : "Review proposed edits"}
      description="Changes apply to editor buffers only. Save afterwards to write files; nothing is written to disk from here."
    >
      {edit && (
        <>
          <p className="small muted">
            {edit.files.length} {edit.files.length === 1 ? "file" : "files"} · {edit.total} {edit.total === 1 ? "edit" : "edits"}
          </p>
          <div className="edit-preview-files">
            {files.map((file) => (
              <details key={file.path} open className="edit-preview-file">
                <summary>
                  <label onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={file.include}
                      onChange={(e) =>
                        setFiles((all) => all.map((item) => (item.path === file.path ? { ...item, include: e.target.checked } : item)))
                      }
                    />
                    <strong>{file.relative}</strong>
                  </label>
                  <span className="small muted">{file.edits.length} {file.edits.length === 1 ? "edit" : "edits"}</span>
                </summary>
                <ul className="edit-preview-lines">
                  {file.lines.map((item, index) => (
                    <li key={index}>
                      <span className="small muted">line {item.line}</span>
                      <pre data-kind="before">{item.before}</pre>
                      <pre data-kind="after">{item.after}</pre>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={close} disabled={busy}>
              Cancel
            </button>
            <button className="primary" onClick={() => void apply()} disabled={busy || total === 0}>
              Apply {total} {total === 1 ? "edit" : "edits"} to editor
            </button>
          </div>
        </>
      )}
    </Sheet>
  );
}
function applyToLine(source: string[], edit: { range: { start: { line: number; character: number }; end: { line: number; character: number } }; newText: string }) {
  const first = source[edit.range.start.line] ?? "";
  const last = source[edit.range.end.line] ?? "";
  const merged = first.slice(0, edit.range.start.character) + edit.newText + last.slice(edit.range.end.character);
  return merged.split(/\r?\n/)[0];
}
