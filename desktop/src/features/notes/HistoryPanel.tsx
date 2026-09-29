import { useEffect, useState } from "react";
import { History, RotateCcw } from "lucide-react";
import { call } from "../../services/api";
import { whenLabel } from "../../services/when";
import { EmptyState, Side } from "../../components/WorkspacePage";
import { reasonLabel } from "./notesModel";

interface Version {
  history_id: string;
  created_at: string;
  reason: string;
  devices: { device_id: string; name: string }[];
  title: string;
  size: number;
  current: boolean;
}

/** Local, private version history. Restoring becomes a new synced edit. */
export function HistoryPanel({ noteId, revision, onClose, onRestored, report }: {
  noteId: string;
  revision: number;
  onClose: () => void;
  onRestored: () => void;
  report: (error: unknown) => void;
}) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [selected, setSelected] = useState<{ id: string; text: string; title: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    setSelected(null);
    void call<{ history: Version[] }>("notes.history", { note_id: noteId })
      .then((result) => live && setVersions(result.history))
      .catch(report);
    return () => { live = false; };
  }, [noteId, revision, report]);
  const open = async (version: Version) => {
    try {
      const entry = await call<{ text: string; title: string }>("notes.history_get", { history_id: version.history_id });
      setSelected({ id: version.history_id, text: entry.text, title: entry.title });
    } catch (error) {
      report(error);
    }
  };
  const restore = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await call("notes.history_restore", { note_id: noteId, history_id: selected.id });
      onRestored();
      setSelected(null);
    } catch (error) {
      report(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Side title="History" label="Note history" always
      actions={<button className="quiet" onClick={onClose} aria-label="Close history">Close</button>}>
      <p className="muted small">Stored only on this device. Restoring saves the old text as a new edit, so your other devices get it too.</p>
      {versions && !versions.length && (
        <EmptyState compact headingLevel={3} icon={<History size={18} />} title="No versions yet">
          OLIVE keeps a version when you pause editing, rename or restore.
        </EmptyState>
      )}
      <ol className="notes-history" aria-label="Versions">
        {(versions || []).map((version) => (
          <li key={version.history_id}>
            <button className={`notes-history-row ${selected?.id === version.history_id ? "selected" : ""}`}
              aria-pressed={selected?.id === version.history_id} onClick={() => void open(version)}>
              <span className="notes-history-when">{whenLabel(version.created_at)}</span>
              <span className="notes-history-meta">
                {version.devices.map((d) => d.name).join(", ") || "This computer"} · {reasonLabel(version.reason)}
                {version.current ? " · Current" : ""}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {selected && (
        <div className="notes-history-preview">
          {selected.title && <strong>{selected.title}</strong>}
          <pre>{selected.text || "(empty note)"}</pre>
          <button className="primary" disabled={busy} onClick={() => void restore()}>
            <RotateCcw size={15} aria-hidden="true" />
            Restore this version
          </button>
        </div>
      )}
    </Side>
  );
}
