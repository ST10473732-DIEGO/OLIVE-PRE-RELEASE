import { useEffect, useState } from "react";
import { call, type Workspace } from "../../services/api";
import type { Device } from "./types";
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
  return <section className="devices-panel" aria-label="Remote Studio sharing">
    <h3 className="devices-eyebrow">Remote Studio</h3>
    <p>Share an existing local workspace with this device. Each permission starts Off.</p>
    {device.studio_shares?.map(share => <div key={share.workspace_id} className="devices-permission-group">
      <strong>{share.display_name}</strong>
      {Object.entries(share.permissions).map(([cap, decision]) => <label className="devices-permission" key={cap}>
        {cap.slice(7)} {cap === "studio.debug" ? <small>Unavailable remotely</small> : <select aria-label={`${share.display_name} ${cap}`} value={decision}
          onChange={e => void act(() => call("connect.studio_permission", {device_id: device.device_id, workspace_id: share.workspace_id, capability: cap as StudioCapability, decision: e.target.value as "deny" | "ask" | "allow"}))}>
          <option value="deny">Off</option><option value="ask">Ask</option><option value="allow">Allow</option>
        </select>}
      </label>)}
      <button onClick={() => void act(() => call("connect.studio_unshare", {device_id: device.device_id, workspace_id: share.workspace_id}))}>Stop sharing</button>
    </div>)}
    <select aria-label="Local workspace to share" value={selected} onChange={e => setSelected(e.target.value)}>
      <option value="">Select local workspace</option>
      {workspaces.map(w => <option value={w.id} key={w.id}>{w.title}</option>)}
    </select>
    <button disabled={!selected} onClick={() => void act(() => call("connect.studio_share", {device_id: device.device_id, workspace_id: selected}))}>Share workspace</button>
    {device.studio_jobs?.map(job => <p key={job.job_id}>Remote Studio · {device.studio_shares?.find(s => s.workspace_id === job.workspace_id)?.display_name || "Shared workspace"} · {job.operation} · {job.state} <button onClick={() => void act(() => call("connect.studio_stop", {device_id: device.device_id, job_id: job.job_id}))}>Stop</button></p>)}
    {error && <p role="alert">{error}</p>}
  </section>;
}
