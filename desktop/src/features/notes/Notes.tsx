import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArchiveRestore,
  ChevronLeft,
  Copy,
  Download,
  History,
  NotebookPen,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { call, type WireEvent } from "../../services/api";
import type { RecordTarget } from "../../services/handoff";
import { whenLabel } from "../../services/when";
import { EmptyState, Main, Rail, Seg, WorkspacePage } from "../../components/WorkspacePage";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { NoteEditor } from "./NoteEditor";
import { HistoryPanel } from "./HistoryPanel";
import { NoteSession, type NotesBridge, type NoteSummary, type SaveState } from "./session";
import { stableOrder, syncLine, type NotesStatus } from "./notesModel";
import "./notes.css";

const SELECTED_KEY = "olive.notes.selected";
const VIEW = `desktop-${Math.random().toString(36).slice(2, 10)}`;

const bridge: NotesBridge = {
  open: (note_id) => call("notes.open", { note_id }),
  chunk: (token, index) => call("notes.state_chunk", { token, index }),
  since: (note_id, state_vector) => call("notes.state_since", { note_id, state_vector }),
  apply: (note_id, update, view, upload) => call("notes.apply", { note_id, update, view, ...(upload ? { upload } : {}) }),
};

function remembered(): string | null {
  try { return localStorage.getItem(SELECTED_KEY); } catch { return null; }
}
function remember(id: string | null) {
  try { if (id) localStorage.setItem(SELECTED_KEY, id); else localStorage.removeItem(SELECTED_KEY); } catch { /* per-device convenience only */ }
}

export default function Notes({ report, target, visible }: { report: (error: unknown) => void; target?: RecordTarget; visible: boolean }) {
  const [view, setView] = useState<"notes" | "trash">("notes");
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [counts, setCounts] = useState({ notes: 0, trash: 0 });
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NoteSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(remembered);
  const [session, setSession] = useState<NoteSession | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [saveError, setSaveError] = useState("");
  const [status, setStatus] = useState<NotesStatus | null>(null);
  const [history, setHistory] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [purge, setPurge] = useState<NoteSummary | null>(null);
  const [holdId, setHoldId] = useState<string | null>(null);
  const [findRequest, setFindRequest] = useState(0);
  const [narrowList, setNarrowList] = useState(true);
  const [notice, setNotice] = useState("");
  const [focusId, setFocusId] = useState<string | null>(null);
  const order = useRef<string[]>([]);
  const holdTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const searchField = useRef<HTMLInputElement>(null);
  const sessionRef = useRef<NoteSession | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await call<{ notes: NoteSummary[]; counts: { notes: number; trash: number } }>("notes.list", { view });
      setNotes(list.notes);
      setCounts(list.counts);
      setLoaded(true);
    } catch (error) {
      setLoaded(true);
      report(error);
    }
  }, [view, report]);

  const refreshStatus = useCallback(async () => {
    try { setStatus(await call<NotesStatus>("notes.status", {})); } catch { /* status is advisory */ }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    void refreshStatus();
    const timer = setInterval(() => { if (visible) void refreshStatus(); }, 15000);
    return () => clearInterval(timer);
  }, [refreshStatus, visible]);

  // Search is local only: the query never leaves this device.
  useEffect(() => {
    if (!query.trim()) { setResults(null); return; }
    let live = true;
    const timer = setTimeout(() => {
      void call<{ results: NoteSummary[] }>("notes.search", { query, include_trash: view === "trash" })
        .then((found) => live && setResults(found.results.filter((n) => n.trashed === (view === "trash"))))
        .catch(report);
    }, 150);
    return () => { live = false; clearTimeout(timer); };
  }, [query, view, report, counts]);

  // Open the selected note as a live CRDT session; flush the previous one first.
  useEffect(() => {
    let live = true;
    const previous = sessionRef.current;
    sessionRef.current = null;
    setSession(null);
    setHistory(false);
    void (async () => {
      if (previous) await previous.close();
      if (!selectedId) return;
      const next = new NoteSession(selectedId, bridge, VIEW);
      next.subscribe(() => { setSaveState(next.saveState); setSaveError(next.error); });
      try {
        await next.load();
      } catch (error) {
        await next.close();
        if (live) {
          report(error);
          setSelectedId(null);
          remember(null);
        }
        return;
      }
      if (!live) { await next.close(); return; }
      sessionRef.current = next;
      setSession(next);
      setSaveState("saved");
    })();
    return () => { live = false; };
  }, [selectedId, report]);

  useEffect(() => () => { void sessionRef.current?.close(); }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let statusTimer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = window.olive.subscribe((event: WireEvent) => {
      const data = event.data as Record<string, string>;
      const current = sessionRef.current;
      if (event.topic === "notes.update" && current && data.note_id === current.noteId) {
        current.remote(data.update, data.view);
      } else if (event.topic === "notes.resync" && current && data.note_id === current.noteId) {
        void current.resync().catch(report);
      } else if (event.topic === "notes.purged" && data.note_id === sessionRef.current?.noteId) {
        setSelectedId(null);
        remember(null);
        setNotice("This note was permanently deleted on another device.");
      }
      if (event.topic === "notes.changed" || event.topic === "notes.purged") {
        clearTimeout(timer);
        timer = setTimeout(() => void refresh(), 120);
      }
      if (event.topic === "notes.sync" || event.topic === "notes.changed") {
        clearTimeout(statusTimer);
        statusTimer = setTimeout(() => void refreshStatus(), 300);
      }
    });
    return () => { unsubscribe(); clearTimeout(timer); clearTimeout(statusTimer); };
  }, [refresh, refreshStatus, report]);

  // Chat or another page asked to open a note.
  useEffect(() => {
    if (!target) return;
    if (target.id) {
      setView("notes");
      setQuery("");
      setSelectedId(target.id);
      remember(target.id);
      setNarrowList(false);
    }
  }, [target]);

  const ordered = useMemo(() => {
    const list = results ?? stableOrder(order.current, notes, holdId);
    order.current = list.map((n) => n.note_id);
    return list;
  }, [notes, results, holdId]);

  const selected = notes.find((n) => n.note_id === selectedId) || (session?.note && session.note.note_id === selectedId ? session.note : null);

  const select = (id: string) => {
    setSelectedId(id);
    remember(id);
    setNarrowList(false);
  };

  const create = useCallback(async () => {
    try {
      const note = await call<NoteSummary>("notes.create", {});
      setView("notes");
      setQuery("");
      await refresh();
      setFocusId(note.note_id);
      select(note.note_id);
    } catch (error) {
      report(error);
    }
  }, [refresh, report]);

  const act = async (action: () => Promise<unknown>, after?: () => void) => {
    try {
      await sessionRef.current?.flush();
      await action();
      after?.();
      await refresh();
    } catch (error) {
      report(error);
    }
  };

  // Ctrl/Cmd+N (new note) and Ctrl/Cmd+Shift+F (search notes) while Notes is showing.
  useEffect(() => {
    if (!visible) return;
    const listener = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (!mod || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "n" && !event.shiftKey) { event.preventDefault(); void create(); }
      if (key === "f" && event.shiftKey) { event.preventDefault(); searchField.current?.focus(); }
      if (key === "f" && !event.shiftKey && !(event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        if (sessionRef.current) setFindRequest((n) => n + 1);
        else searchField.current?.focus();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [visible, create]);

  const typing = () => {
    if (!selectedId) return;
    setHoldId(selectedId);
    clearTimeout(holdTimer.current);
    holdTimer.current = setTimeout(() => setHoldId(null), 1500);
  };

  const line = syncLine(status, saveState, saveError);
  const unavailable = status && !status.available;

  const list = (
    <Rail className="notes-rail" label="Notes list" wide
      title={view === "trash" ? "Recently Deleted" : "Notes"}
      actions={view === "notes" ? (
        <button className="icon-button quiet" aria-label="New note" title="New note (Ctrl+N)" onClick={() => void create()}>
          <Plus size={16} aria-hidden="true" />
        </button>
      ) : undefined}
      foot={
        <Seg label="Notes view" value={view} onChange={(value) => { setView(value); setQuery(""); }}
          options={[
            { value: "notes", label: "Notes", count: counts.notes },
            { value: "trash", label: "Recently Deleted", count: counts.trash, icon: <Trash2 size={14} aria-hidden="true" /> },
          ]} />
      }>
      <label className="search notes-search">
        <Search size={15} aria-hidden="true" />
        <input ref={searchField} aria-label="Search notes" placeholder={view === "trash" ? "Search deleted notes" : "Search notes"}
          value={query} onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Escape") setQuery(""); }} />
        {query && (
          <button className="icon-button quiet" aria-label="Clear search" onClick={() => setQuery("")}>
            <X size={14} aria-hidden="true" />
          </button>
        )}
      </label>
      {results && !results.length && <p className="muted small notes-empty-line">No notes match “{query}”.</p>}
      <ul className="notes-list" aria-label={view === "trash" ? "Recently deleted notes" : "Notes"}>
        {ordered.map((note) => (
          <li key={note.note_id}>
            <button className={`notes-row ${note.note_id === selectedId ? "selected" : ""}`}
              aria-current={note.note_id === selectedId ? "true" : undefined} onClick={() => select(note.note_id)}>
              <span className="notes-row-title">
                {note.pinned && <Pin size={12} aria-label="Pinned" />}
                <span>{note.display_title}</span>
              </span>
              <span className="notes-row-preview">{note.snippet || note.preview || (note.status !== "ok" ? "Note data corrupted" : "No additional text")}</span>
              <span className="notes-row-time">
                {view === "trash" ? `Deleted ${whenLabel(note.trashed_at)}` : whenLabel(note.edited_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {loaded && !notes.length && !query && view === "trash" && <p className="muted small notes-empty-line">Nothing recently deleted.</p>}
    </Rail>
  );

  const editor = selected && session ? (
    <>
      <div className="notes-toolbar" role="toolbar" aria-label="Note actions">
        <button className="icon-button quiet notes-back" aria-label="Back to notes list" onClick={() => setNarrowList(true)}>
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <span className="notes-toolbar-when">{selected.trashed ? `Deleted ${whenLabel(selected.trashed_at)}` : `Edited ${whenLabel(selected.edited_at)}`}</span>
        <span className="notes-toolbar-spacer" />
        {selected.trashed ? (
          <>
            <button onClick={() => void act(() => call("notes.restore", { note_id: selected.note_id }))}>
              <ArchiveRestore size={15} aria-hidden="true" /> Restore
            </button>
            <button className="danger" onClick={() => setPurge(selected)}>
              <Trash2 size={15} aria-hidden="true" /> Delete permanently
            </button>
          </>
        ) : (
          <>
            <button className="icon-button quiet" aria-label={selected.pinned ? "Unpin note" : "Pin note"} title={selected.pinned ? "Unpin" : "Pin"}
              aria-pressed={selected.pinned}
              onClick={() => void act(() => call("notes.pin", { note_id: selected.note_id, pinned: !selected.pinned }))}>
              {selected.pinned ? <PinOff size={16} aria-hidden="true" /> : <Pin size={16} aria-hidden="true" />}
            </button>
            <button className="icon-button quiet" aria-label="Version history" title="History" aria-pressed={history}
              onClick={() => setHistory((value) => !value)}>
              <History size={16} aria-hidden="true" />
            </button>
            <button className="icon-button quiet" aria-label="Duplicate note" title="Duplicate"
              onClick={() => void act(async () => { const copy = await call<NoteSummary>("notes.duplicate", { note_id: selected.note_id }); select(copy.note_id); })}>
              <Copy size={16} aria-hidden="true" />
            </button>
            <button className="icon-button quiet" aria-label="Export note as text" title="Export as .txt"
              onClick={() => void act(() => window.olive.fileAction({ action: "notes-export", note_id: selected.note_id, format: "txt", name: selected.display_title }))}>
              <Download size={16} aria-hidden="true" />
            </button>
            <button className="icon-button quiet" aria-label="Move note to Recently Deleted" title="Delete"
              onClick={() => void act(() => call("notes.trash", { note_id: selected.note_id }), () => { setSelectedId(null); remember(null); })}>
              <Trash2 size={16} aria-hidden="true" />
            </button>
          </>
        )}
      </div>
      <NoteEditor key={session.noteId} session={session} note={selected}
        autoFocus={focusId === session.noteId}
        onFocused={() => setFocusId(null)}
        readOnly={selected.trashed || selected.status !== "ok"}
        findRequest={findRequest}
        onTyping={typing}
        onLimit={() => setNotice("Note too large. Notes can hold up to about 1.5 MB of text.")}
        onRename={(title) => void call("notes.rename", { note_id: selected.note_id, title }).then(() => refresh()).catch(report)} />
    </>
  ) : null;

  return (
    <WorkspacePage
      layout="fill"
      className={`notes-page ${unavailable ? "" : narrowList ? "narrow-list" : "narrow-editor"}`}
      icon={<NotebookPen size={18} />}
      title="OLIVE Notes"
      description="Plain-text notes on this device. They sync with paired devices you allow."
      status={line.label}
      statusTone={line.tone}
      actions={
        <>
          <button onClick={() => void window.olive.fileAction({ action: "notes-import" })
            .then((note) => { if (note && typeof note === "object" && "note_id" in note) { void refresh(); select((note as NoteSummary).note_id); } })
            .catch(report)}>
            <Upload size={15} aria-hidden="true" /> Import
          </button>
          <button className="primary" onClick={() => void create()} disabled={Boolean(unavailable)}>
            <Plus size={16} aria-hidden="true" /> New note
          </button>
        </>
      }
      rail={unavailable ? undefined : list}
      side={history && selected && !selected.trashed ? (
        <HistoryPanel noteId={selected.note_id} revision={historyRevision} report={report}
          onClose={() => setHistory(false)}
          onRestored={() => { setHistoryRevision((n) => n + 1); void refresh(); }} />
      ) : undefined}
    >
      <Main pad={false} scroll={false} className="notes-main" label="Note editor">
        {notice && (
          <p className="notes-notice" role="status">
            {notice}
            <button className="icon-button quiet" aria-label="Dismiss" onClick={() => setNotice("")}><X size={14} aria-hidden="true" /></button>
          </p>
        )}
        {unavailable ? (
          <EmptyState icon={<NotebookPen size={20} />} title="Notes storage unavailable">
            {status?.message} Nothing was changed or replaced.
          </EmptyState>
        ) : editor ? editor : loaded && !counts.notes && view === "notes" ? (
          <EmptyState icon={<NotebookPen size={20} />} title="No notes yet"
            actions={<button className="primary" onClick={() => void create()}><Plus size={16} aria-hidden="true" /> New note</button>}>
            Notes save as you type. They stay on this device and sync with paired devices you allow.
          </EmptyState>
        ) : (
          <EmptyState compact icon={<NotebookPen size={20} />} title={view === "trash" ? "Select a deleted note" : "Select a note"}>
            {view === "trash" ? "Restore it, or delete it permanently." : "Or press Ctrl+N for a new one."}
          </EmptyState>
        )}
      </Main>
      <ConfirmDialog open={Boolean(purge)} onOpenChange={(open) => { if (!open) setPurge(null); }}
        title="Delete permanently?" confirmLabel="Delete permanently"
        onConfirm={async () => {
          if (!purge) return;
          await call("notes.purge", { note_id: purge.note_id, confirmed: true });
          if (selectedId === purge.note_id) { setSelectedId(null); remember(null); }
          await refresh();
        }}>
        “{purge?.display_title}” will be removed from this device and from paired devices when they sync. This cannot be undone.
      </ConfirmDialog>
    </WorkspacePage>
  );
}
