import { useEffect, useState } from "react";
import { call, type Workspace } from "../../services/api";
import type { Device } from "./types";
import { sentence } from "./ui";
export type StudioCapability = `studio.${"view" | "edit" | "build" | "test" | "run" | "debug"}`;
export interface StudioShare {
  workspace_id: string; display_name: string; share_revision: number;
  permissions: Record<string, "deny" | "ask" | "allow">;
}
export function StudioShares({device, refresh}: {device: Device; refresh: () => Promise<void>}) {
  const [workspaces, setWorkspaces] = useState<Pick<Workspace, "id" | "title">[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { void call<Pick<Workspace, "id" | "title">[]>("connect.studio_local_workspaces", {}).then(setWorkspaces).catch(() => setError("Local workspace list unavailable.")); }, []);
  const act = async (action: () => Promise<unknown>) => {
    try { setError(""); await action(); await refresh(); }
    catch { setError("The workspace sharing change could not complete."); }
  };
  const shares = device.studio_shares || [];
  const available = workspaces.filter(w => !shares.some(s => s.workspace_id === w.id));
  return <section className="devices-card" aria-label="Remote Studio sharing">
    <header className="devices-card-head">
      <div>
        <h3>Remote Studio</h3>
        <p>Share a local workspace with {device.display_name}. Each permission starts Off.</p>
      </div>
    </header>
    {shares.map(share => <div key={share.workspace_id} className="devices-share">
      <div className="devices-share-head">
        <strong>{share.display_name}</strong>
        <button className="quiet" onClick={() => void act(() => call("connect.studio_unshare", {device_id: device.device_id, workspace_id: share.workspace_id}))}>Stop sharing</button>
      </div>
      <div className="devices-share-grid">
        {Object.entries(share.permissions).map(([cap, decision]) => <label className="devices-share-cap" key={cap}>
          <span>{sentence(cap.slice(7))}</span>
          {cap === "studio.debug" ? <small>Local only</small> : <select aria-label={`${share.display_name} ${cap}`} value={decision} data-value={decision}
            onChange={e => void act(() => call("connect.studio_permission", {device_id: device.device_id, workspace_id: share.workspace_id, capability: cap as StudioCapability, decision: e.target.value as "deny" | "ask" | "allow"}))}>
            <option value="deny">Off</option><option value="ask">Ask</option><option value="allow">Allow</option>
          </select>}
        </label>)}
      </div>
    </div>)}
    {device.studio_jobs?.map(job => <div className="devices-job" key={job.job_id}>
      <span className="devices-state" data-tone="computing">{shares.find(s => s.workspace_id === job.workspace_id)?.display_name || "Shared workspace"} · {sentence(job.operation)} · {sentence(job.state)}</span>
      <button onClick={() => void act(() => call("connect.studio_stop", {device_id: device.device_id, job_id: job.job_id}))}>Stop</button>
    </div>)}
    <div className="devices-share-add">
      <select aria-label="Local workspace to share" value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">{available.length ? "Choose a workspace…" : "No other workspaces"}</option>
        {available.map(w => <option value={w.id} key={w.id}>{w.title}</option>)}
      </select>
      <button disabled={!selected} onClick={() => void act(async () => { await call("connect.studio_share", {device_id: device.device_id, workspace_id: selected}); setSelected(""); })}>Share workspace</button>
    </div>
    {error && <p className="devices-inline-error" role="alert">{error}</p>}
  </section>;
}
