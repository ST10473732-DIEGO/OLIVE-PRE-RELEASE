import { useCallback, useEffect, useRef, useState } from "react";
import * as monaco from "monaco-editor";
import { call } from "../../services/api";
import type { DevicesState } from "../devices/types";
import type { StudioShare } from "../devices/StudioShares";
import { languageFor } from "./languageClient";

type Operation = "workspaces" | "tree" | "read" | "save" | "build" | "test" | "run" | "run_status" | "run_cancel";
type Reply<T> = {result: T | null; error: string | null};
type Target = {device_id: string; name: string; online: boolean};
type Buffer = {path: string; text: string; saved: string; revision: string};
type Job = {diagnostics?: {path: string; line: number; severity: string; message: string}[]; job_id: string; state: string; output?: string; truncated?: boolean; exit_code?: number; error?: string; tests?: {passed: number; failed: number; skipped: number}};
export function RemoteStudio({theme, visible}: {theme: string; visible: boolean}) {
  const [targets, setTargets] = useState<Target[]>([]), [peer, setPeer] = useState("");
  const [shares, setShares] = useState<StudioShare[]>([]), [reference, setReference] = useState("");
  const [tree, setTree] = useState<{path: string; directory: boolean}[]>([]);
  const [active, setActive] = useState("");
  const [buffers, setBuffers] = useState<Record<string, Buffer>>({});
  const [message, setMessage] = useState("Select a paired device and load its shared workspaces.");
  const [busy, setBusy] = useState(false), [job, setJob] = useState<Job | null>(null);
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
    const instance = monaco.editor.create(element.current, {ariaLabel: "Remote source editor", automaticLayout: true, minimap: {enabled: false}, readOnly: true});
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
  useEffect(() => { monaco.editor.setTheme(theme === "light" ? "vs" : "vs-dark"); editor.current?.layout(); }, [theme, visible]);
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
  return <div className="studio" style={{height: "100%", display: "flex", flexDirection: "column"}} aria-label="Remote Studio workspace">
    <header className="studio-bar">
      <strong>Remote · {target?.name || "Select device"} · {target?.online ? "Online" : "Offline"}</strong>
      <select aria-label="Remote Studio device" disabled={busy || !!running} value={peer} onChange={e => {setPeer(e.target.value); setShares([]); setReference(""); setTree([]); setActive(""); setJob(null);}}>
        <option value="">Select paired device</option>{targets.map(t => <option key={t.device_id} value={t.device_id}>{t.name} · {t.online ? "Online" : "Offline"}</option>)}
      </select>
      <button disabled={!target?.online || busy || !!running} onClick={() => void act(load)}>Load shared workspaces</button>
      <select aria-label="Remote workspace" disabled={busy || !!running} value={reference} onChange={e => {setReference(e.target.value); setTree([]); setActive(""); setJob(null);}}>
        <option value="">Select shared workspace</option>{shares.map(s => <option key={s.workspace_id} value={s.workspace_id}>{s.display_name} · {target?.name}</option>)}
      </select>
    </header>
    <div className="studio-bar">
      <button disabled={!share || busy || !target?.online} onClick={() => void act(async () => {const value = await exchange<{entries: typeof tree; truncated: boolean}>("tree"); setTree(value.entries); setMessage(value.truncated ? "Showing bounded file tree." : "Remote files loaded.");})}>Files</button>
      <button disabled={!dirty || busy || !target?.online} onClick={() => void act(save)}>Save remotely</button>
      <button disabled={!buffer || busy || !target?.online} onClick={() => void act(reload)}>Reload</button>
      {(["build", "test", "run"] as const).map(op => <button key={op} disabled={!share || busy || !!running || !target?.online || share.permissions[`studio.${op}`] === "deny"} onClick={() => void act(async () => {setJob(await exchange<Job>(op)); setMessage(`${op} on ${target?.name}`);})}>{op[0].toUpperCase() + op.slice(1)} remotely</button>)}
      <button disabled={!running} onClick={() => void act(async () => {setJob(await exchange<Job>("run_cancel", {job_id: job?.job_id}));})}>Stop</button>
      <span>{active}{dirty ? " · Unsaved local draft" : buffer ? " · Saved remote revision" : ""}</span>
    </div>
    <p role="status">{message}</p>
    <div style={{display: "flex", flex: 1, minHeight: 220}}>
      <nav style={{width: 220, overflow: "auto"}} aria-label="Remote files">{tree.filter(f => !f.directory).map(f => <button style={{display: "block"}} key={f.path} disabled={busy || !target?.online} onClick={() => void act(() => open(f.path))}>{f.path}</button>)}</nav>
      <div ref={element} style={{flex: 1, minWidth: 0}} />
    </div>
    {job && <div className="ws-panel"><strong>{job.state} · exit {job.exit_code ?? "pending"}</strong>
      {job.tests && <p>{job.tests.passed} passed · {job.tests.failed} failed · {job.tests.skipped} skipped</p>}
      {job.diagnostics?.map((d, i) => <p key={i}>{d.path}{d.line ? `:${d.line}` : ""} · {d.severity} · {d.message}</p>)}
      <pre style={{maxHeight: 180, overflow: "auto"}}>{job.output}</pre>{job.truncated && <small>Recent output only; earlier output truncated.</small>}</div>}
    <small>Remote terminal, interactive input, debug, LSP, package installation and project creation are unavailable.</small>
  </div>;
}
