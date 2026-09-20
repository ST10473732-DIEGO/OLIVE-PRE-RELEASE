import { call } from "../../services/api";
import { useState } from "react";
import type { Device } from "./types";

export function RemoteAI({ device, refresh }: { device: Device; refresh: () => Promise<void> }) {
  const [error, setError] = useState("");
  const info = device.remote_ai;
  if (!info) return null;
  return <section className="devices-panel" aria-label="Remote AI activity">
    <h3>Remote AI</h3>
    <p>This device lends text inference only. Set Off / Ask / Allow in Permissions.</p>
    <p>{Object.entries(info.presets).map(([preset, available]) =>
      `OLIVE ${preset.toUpperCase()} · ${available ? "Available" : "Unavailable"}`).join(" · ")}</p>
    <p className="muted">DEEP, REIMAGINE, attachments and tools are unavailable remotely.</p>
    {error && <p role="alert">{error}</p>}
    {info.jobs.map((job) => <div key={job.job_id}>
      <p>{device.display_name} · OLIVE {job.preset.toUpperCase()} · {job.state.replaceAll("_", " ")}</p>
      <button onClick={() => {
        setError("");
        void call("connect.inference_stop", { device_id: device.device_id, job_id: job.job_id }).then(refresh)
          .catch(() => setError("Could not confirm Stop. Check this device’s connection and retry."));
      }}>Stop remote inference</button>
    </div>)}
  </section>;
}
