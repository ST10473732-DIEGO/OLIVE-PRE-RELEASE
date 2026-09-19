import { useEffect, useRef } from "react";
import * as monaco from "monaco-editor";
export function Compare({
  disk,
  model,
  close,
  reconcile,
}: {
  disk: string;
  model: monaco.editor.ITextModel;
  close: () => void;
  reconcile: () => void;
}) {
  const target = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const original = monaco.editor.createModel(disk, model.getLanguageId());
    const editor = monaco.editor.createDiffEditor(target.current!, {
      automaticLayout: true,
      originalEditable: false,
      readOnly: false,
      renderSideBySide: true,
      accessibilitySupport: "on",
    });
    editor.setModel({ original, modified: model });
    return () => {
      editor.dispose();
      original.dispose();
    };
  }, [disk, model]);
  return (
    <section
      className="compare-panel"
      aria-label="Compare disk and unsaved editor"
    >
      <header className="workspace-header">
        <div>
          <h2>Disk version ↔ your editor</h2>
          <p className="small muted">
            Review and merge on the right. Neither version is overwritten here.
          </p>
        </div>
        <div className="row">
          <button onClick={close}>Close comparison</button>
          <button className="primary" onClick={reconcile}>
            Use reviewed disk version as base
          </button>
        </div>
      </header>
      <div className="compare-editor" ref={target} />
    </section>
  );
}
