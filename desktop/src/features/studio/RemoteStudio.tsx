import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import * as monaco from "monaco-editor";
import { AlertTriangle, CheckCircle2, CircleSlash, FileCode2, FlaskConical, Hammer, Info, Loader2, MonitorSmartphone, Play, RefreshCw, Save, Square, XCircle } from "lucide-react";
import { call } from "../../services/api";
import type { DevicesState } from "../devices/types";
import type { StudioShare } from "../devices/StudioShares";
import { languageFor } from "./languageClient";
import { TitleBarPortal } from "../../app/TitleBar";
import { ActivityBar } from "./ActivityBar";
import { activityAvailability } from "./studioModel";

type Operation = "workspaces" | "tree" | "read" | "save" | "build" | "test" | "run" | "run_status" | "run_cancel";
type Reply<T> = {result: T | null; error: string | null};
type Target = {device_id: string; name: string; online: boolean};
type Buffer = {path: string; text: string; saved: string; revision: string};
type Job = {diagnostics?: {path: string; line: number; severity: string; message: string}[]; job_id: string; state: string; output?: string; truncated?: boolean; exit_code?: number; error?: string; tests?: {passed: number; failed: number; skipped: number}};
const PERMISSIONS: [string, string][] = [["studio.view", "Read"], ["studio.edit", "Save"], ["studio.build", "Build"], ["studio.test", "Test"], ["studio.run", "Run"]];
const DECISION: Record<string, string> = { deny: "Off", ask: "Ask", allow: "Allow" };

// Remote Studio is Connect C8 and deliberately bounded: shared workspaces,
// tree, read, revision-checked save, build, test, run, run status and run
// cancel. It has no terminal, interactive input, debugger, code intelligence,
// search, Git, packages or project creation, so the same IDE frame shows
// those surfaces disabled with the reason. Everything is attributed to the
// device that owns the files.
export function RemoteStudio({theme, visible, location, openSettings}: {theme: string; visible: boolean; location: ReactNode; openSettings: () => void}) {
  const [targets, setTargets] = useState<Target[]>([]), [peer, setPeer] = useState("");
  const [shares, setShares] = useState<StudioShare[]>([]), [reference, setReference] = useState("");
  const [tree, setTree] = useState<{path: string; directory: boolean}[]>([]);
  const [active, setActive] = useState("");
  const [buffers, setBuffers] = useState<Record<string, Buffer>>({});
  const [message, setMessage] = useState("Select a paired device and load its shared workspaces.");
  const [busy, setBusy] = useState(false), [job, setJob] = useState<Job | null>(null);
  const [lastOperation, setLastOperation] = useState("");
  const element = useRef<HTMLDivElement>(null), editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const current = useRef("");
  const target = targets.find(t => t.device_id === peer);
  const share = shares.find(s => s.workspace_id === reference);
  const bufferKey = `${peer}/${reference}/${active}`;
  const buffer = buffers[bufferKey];
  const dirty = buffer && buffer.text !== buffer.saved;
  const exchange = useCallback(async <T,>(operation: Operation, args: Record<string, unknown> = {}, scope: StudioShare | null | undefined = share): Promise<T> => {
    const reply = await call<Reply<T>>("connect.studio_request", {device_id: peer, operation,
      ...(scope ? {workspace_id: scope.workspace_id} : {}), share_revision: scope?.share_revision || 0, arguments: args});
    if (reply.error || !reply.result) throw new Error(reply.error || "connection_lost");
    return reply.result;
  }, [peer, share]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const d = await call<DevicesState>("connect.snapshot", {});
        if (!stopped) setTargets(d.devices.map(t => ({device_id: t.device_id, name: t.display_name,
          online: t.trust_state === "paired" && t.live?.state === "online"})));
      } catch { if (!stopped) setTargets(previous => previous.map(t => ({...t, online: false}))); }
      if (!stopped) timer = setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);
  useEffect(() => {
    if (!element.current) return;
    const instance = monaco.editor.create(element.current, {ariaLabel: "Remote source editor", automaticLayout: true, minimap: {enabled: false}, readOnly: true,
      fontSize: 13, lineHeight: 20, renderLineHighlight: "all", padding: {top: 8},
      fontFamily: '"Cascadia Code", "Cascadia Mono", "JetBrains Mono", "Fira Code", Consolas, "DejaVu Sans Mono", monospace'});
    editor.current = instance;
    const change = instance.onDidChangeModelContent(() => {
      const key = current.current;
      setBuffers(previous => previous[key] ? {...previous, [key]: {...previous[key], text: instance.getValue()}} : previous);
    });
    return () => { change.dispose(); instance.dispose(); };
  }, []);
  useEffect(() => {
    current.current = bufferKey;
    const instance = editor.current;
    if (!instance) return;
    const model = monaco.editor.createModel(buffer?.text || "", languageFor(active) || "plaintext");
    instance.setModel(model);
    instance.updateOptions({readOnly: !buffer});
    return () => { instance.setModel(null); model.dispose(); };
    // Buffer keystrokes must not recreate the editor model.
  }, [bufferKey, !!buffer]);
  // Local Studio defines the shared "olive" theme; fall back to Monaco's own.
  useEffect(() => { try { monaco.editor.setTheme("olive"); } catch { monaco.editor.setTheme(theme === "light" ? "vs" : "vs-dark"); } editor.current?.layout(); }, [theme, visible]);
  useEffect(() => {
    const prevent = (event: BeforeUnloadEvent) => {
      if (Object.values(buffers).some(b => b.text !== b.saved)) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [buffers]);
  useEffect(() => {
    if (!job || !["starting", "running", "cancelling"].includes(job.state)) return;
    let stopped = false;
    const timer = setTimeout(() => {
      void exchange<Job>("run_status", {job_id: job.job_id}).then(value => { if (!stopped) setJob(value); })
        .catch(error => { if (!stopped) { setMessage(String(error)); setJob({...job, state: "connection_lost"}); } });
    }, 750);
    return () => { stopped = true; clearTimeout(timer); };
  }, [job, exchange]);
  const act = async (action: () => Promise<void>) => {
    setBusy(true); setMessage("Waiting for target · Ask requests need approval on that device.");
    try { await action(); } catch (error) { setMessage(`${String(error)} · Unsaved drafts remain on this device.`); }
    finally { setBusy(false); }
  };
  const load = async () => {
    const value = await exchange<{workspaces: StudioShare[]}>("workspaces", {}, null);
    setShares(value.workspaces); setMessage("Shared workspaces loaded. Select one explicitly.");
  };
  const open = async (path: string) => {
    const key = `${peer}/${reference}/${path}`;
    if (!buffers[key]) {
      if (Object.keys(buffers).length >= 32) throw new Error("Remote buffer limit reached");
      const value = await exchange<{path: string; text: string; revision: string}>("read", {path});
      setBuffers(previous => ({...previous, [key]: {...value, saved: value.text}}));
    }
    setActive(path); setMessage("Remote file · Editing a local draft; Save writes to the target.");
  };
  const save = async () => {
    if (!buffer) return;
    const text = buffer.text;
    setMessage(share?.permissions["studio.edit"] === "ask" ? `Waiting for ${target?.name} to approve save.` : "Saving on the target…");
    const value = await exchange<{revision: string}>("save", {path: active, expected_hash: buffer.revision, text});
    setBuffers(previous => ({...previous, [bufferKey]: {...previous[bufferKey], saved: text, revision: value.revision}}));
    setMessage("Saved remotely.");
  };
  const reload = async () => {
    if (dirty && !window.confirm("Discard this local remote draft and reload the target file?")) return;
    const value = await exchange<Buffer>("read", {path: active});
    setBuffers(previous => ({...previous, [bufferKey]: {...value, saved: value.text}}));
    editor.current?.setValue(value.text); setMessage("Reloaded remote revision.");
  };
  const running = job && ["starting", "running", "cancelling"].includes(job.state);
  const online = Boolean(target?.online);
  const files = tree.filter(f => !f.directory);
  const jobTone = !job ? "" : running ? "running" : job.state === "completed" && (job.exit_code ?? 0) === 0 ? "success" : ["failed", "connection_lost", "error"].includes(job.state) || (job.exit_code ?? 0) !== 0 ? "error" : "neutral";
  return <div className="studio studio-v2 remote-studio" aria-label="Remote Studio workspace" data-online={online || undefined}>
    {visible && <TitleBarPortal slot="context">
      {location}
      {target && <span className="tb-remote" title={`Files live on ${target.name}`}>
        <MonitorSmartphone size={13} aria-hidden="true" />{share ? `${share.display_name} · ${target.name}` : target.name}
      </span>}
    </TitleBarPortal>}
    <div className="studio-body">
      <ActivityBar view="explorer" sidebarOpen select={() => undefined} availability={activityAvailability(true)} badges={{}} openSettings={openSettings} />
      <aside className="studio-sidebar remote-sidebar" aria-label="Shared workspace explorer" style={{width: 260}}>
        <div className="sidebar-view">
          <div className="side-head"><h2>Remote workspace</h2></div>
          <div className="side-scroll side-pad remote-connection">
            <p className="remote-target"><strong>Remote · {target?.name || "Select device"} · {target?.online ? "Online" : "Offline"}</strong></p>
            <label className="side-field"><span>Paired device</span>
              <select aria-label="Remote Studio device" disabled={busy || !!running} value={peer} onChange={e => {setPeer(e.target.value); setShares([]); setReference(""); setTree([]); setActive(""); setJob(null);}}>
                <option value="">Select paired device</option>{targets.map(t => <option key={t.device_id} value={t.device_id}>{t.name} · {t.online ? "Online" : "Offline"}</option>)}
              </select>
            </label>
            <button className="compact" disabled={!target?.online || busy || !!running} onClick={() => void act(load)}>Load shared workspaces</button>
            <label className="side-field"><span>Shared workspace</span>
              <select aria-label="Remote workspace" disabled={busy || !!running} value={reference} onChange={e => {setReference(e.target.value); setTree([]); setActive(""); setJob(null);}}>
                <option value="">Select shared workspace</option>{shares.map(s => <option key={s.workspace_id} value={s.workspace_id}>{s.display_name} · {target?.name}</option>)}
              </select>
            </label>
            {share && <div className="remote-permissions" aria-label={`Permissions ${target?.name} granted`}>
              {PERMISSIONS.map(([capability, label]) => {
                const decision = share.permissions[capability] || "deny";
                return <span key={capability} className="ws-pill" data-tone={decision === "allow" ? "success" : decision === "ask" ? "warning" : undefined}>{label} · {DECISION[decision] || decision}</span>;
              })}
            </div>}
            <div className="side-section-head remote-files-head">
              <span className="side-section-title">Files</span>
              <button aria-label="Files" title="Load the shared file tree" className="icon-button" disabled={!share || busy || !target?.online} onClick={() => void act(async () => {const value = await exchange<{entries: typeof tree; truncated: boolean}>("tree"); setTree(value.entries); setMessage(value.truncated ? "Showing bounded file tree." : "Remote files loaded.");})}>
                <RefreshCw size={13} aria-hidden="true" />
              </button>
            </div>
            <nav aria-label="Remote files" className="remote-tree">
              {files.length === 0 && <p className="side-note">{share ? "Load the file tree to browse this shared workspace." : "Select a shared workspace first."}</p>}
              {files.map(f => <button className={f.path === active ? "selected" : ""} key={f.path} disabled={busy || !target?.online} onClick={() => void act(() => open(f.path))} title={f.path}>
                <FileCode2 size={13} aria-hidden="true" />{f.path}
              </button>)}
            </nav>
          </div>
        </div>
      </aside>
      <section className="editor-stack">
        <div className="editor-tabs-row">
          <div className="file-tabs">
            {active && <div className="file-tab active" data-dirty={dirty || undefined}><button title={active}><FileCode2 size={13} aria-hidden="true" />{active.split("/").pop()}{dirty && <span className="dirty" aria-label="unsaved changes">●</span>}</button></div>}
          </div>
          <div className="editor-actions remote-actions" role="group" aria-label="Remote operations">
            <button className="compact quiet" disabled={!dirty || busy || !target?.online} onClick={() => void act(save)}><Save size={13} aria-hidden="true" />Save remotely</button>
            <button className="compact quiet" disabled={!buffer || busy || !target?.online} onClick={() => void act(reload)}><RefreshCw size={13} aria-hidden="true" />Reload</button>
            <span className="tb-sep" aria-hidden="true" />
            {(["build", "test", "run"] as const).map(op => <button key={op} className="compact quiet" disabled={!share || busy || !!running || !target?.online || share.permissions[`studio.${op}`] === "deny"}
              title={share?.permissions[`studio.${op}`] === "deny" ? `${op[0].toUpperCase() + op.slice(1)} is Off for this share` : `${op[0].toUpperCase() + op.slice(1)} on ${target?.name || "the target"}`}
              onClick={() => void act(async () => {setLastOperation(op); setJob(await exchange<Job>(op)); setMessage(`${op} on ${target?.name}`);})}>
              {op === "build" ? <Hammer size={13} aria-hidden="true" /> : op === "test" ? <FlaskConical size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
              {op[0].toUpperCase() + op.slice(1)} remotely
            </button>)}
            <button className="compact quiet danger-action" disabled={!running} onClick={() => void act(async () => {setJob(await exchange<Job>("run_cancel", {job_id: job?.job_id}));})}><Square size={11} aria-hidden="true" />Stop</button>
          </div>
        </div>
        <div className="notice editor-notice" data-tone={online || !peer ? "accent" : "error"} role="note">
          {online || !peer ? <Info size={14} aria-hidden="true" /> : <AlertTriangle size={14} aria-hidden="true" />}
          <span className="grow">
            {!peer ? "Remote Studio opens a workspace another paired device has shared with this PC." :
              online ? `Files live on ${target?.name}. Build, test and run happen there. Code intelligence, debugging, Git and terminals are local-only.` :
              `${target?.name || "The device"} is offline. Your edits stay in this buffer; nothing was saved or retried elsewhere.`}
          </span>
        </div>
        <div className="editor-area">
          <div className="editor-host" ref={element} />
          {!active && <div className="editor-empty" role="note"><FileCode2 size={20} aria-hidden="true" /><strong>No remote file open</strong><p className="muted">Choose a device, load its shared workspaces, then open a file from the tree.</p></div>}
        </div>
        {job && <section className="studio-dock studio-panel remote-output" aria-label="Output · Remote" style={{height: 200}}>
          <div className="panel-head"><div className="panel-tabs"><span className="panel-tab" aria-selected="true">Output · Remote</span></div></div>
          <div className="panel-body">
            <div className="job-header" data-tone={jobTone}>
              {jobTone === "running" ? <Loader2 size={15} className="spin" aria-hidden="true" /> : jobTone === "success" ? <CheckCircle2 size={15} aria-hidden="true" /> : jobTone === "error" ? <XCircle size={15} aria-hidden="true" /> : <CircleSlash size={15} aria-hidden="true" />}
              <strong>{job.state} · exit {job.exit_code ?? "pending"}</strong>
              {lastOperation && <span className="ws-pill">{lastOperation} on {target?.name}</span>}
              {job.tests && <span className="ws-pill" data-tone={job.tests.failed ? "error" : "success"}>{job.tests.passed} passed · {job.tests.failed} failed · {job.tests.skipped} skipped</span>}
              {running && <span className="progress-line" aria-hidden="true" />}
            </div>
            {job.diagnostics?.map((d, i) => <p className="remote-diagnostic" key={i} data-severity={d.severity}>{d.path}{d.line ? `:${d.line}` : ""} · {d.severity} · {d.message}</p>)}
            <pre className="remote-log">{job.output}</pre>
            {job.truncated && <small>Recent output only; earlier output truncated.</small>}
            <p className="side-note">Remote runs are not interactive: there is no terminal or input on the target.</p>
          </div>
        </section>}
      </section>
    </div>
    <footer className="studio-status" aria-label="Remote Studio status">
      <div className="status-left">
        <span className="status-item status-remote" data-online={online || undefined}>
          <MonitorSmartphone size={12} aria-hidden="true" />{target ? `${target.name}${online ? "" : " · offline"}` : "Remote"}
        </span>
        <span className="status-item remote-message" role="status">{message}</span>
      </div>
      <div className="status-right">
        <span className="status-item">{active}{dirty ? " · Unsaved local draft" : buffer ? " · Saved remote revision" : ""}</span>
      </div>
    </footer>
  </div>;
}
