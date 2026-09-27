import { call } from "../../services/api";
import { useState } from "react";
import { Check, Minus } from "lucide-react";
import type { Device } from "./types";
import { sentence } from "./ui";

export function RemoteAI({ device, refresh }: { device: Device; refresh: () => Promise<void> }) {
  const [error, setError] = useState("");
  const info = device.remote_ai;
  if (!info) return null;
  return <section className="devices-card" aria-label="Remote AI activity">
    <header className="devices-card-head">
      <div>
        <h3>Remote AI</h3>
        <p>Lets {device.display_name} run text-only chats on this computer’s models. Turn it on in Permissions.</p>
      </div>
    </header>
    <ul className="devices-chips" aria-label="Presets offered">
      {Object.entries(info.presets).map(([preset, available]) =>
        <li key={preset} data-available={available}>
          {available ? <Check size={12} aria-hidden="true" /> : <Minus size={12} aria-hidden="true" />}
          OLIVE {preset.toUpperCase()}
          <span className="sr-only">{available ? " · Available" : " · Unavailable"}</span>
        </li>)}
    </ul>
    <p className="devices-hint">DEEP, REIMAGINE, attachments and tools are unavailable remotely.</p>
    {error && <p className="devices-inline-error" role="alert">{error}</p>}
    {info.jobs.map((job) => <div className="devices-job" key={job.job_id}>
      <span className="devices-state" data-tone="computing">OLIVE {job.preset.toUpperCase()} · {sentence(job.state)}</span>
      <button onClick={() => {
        setError("");
        void call("connect.inference_stop", { device_id: device.device_id, job_id: job.job_id }).then(refresh)
          .catch(() => setError("Could not confirm Stop. Check this device’s connection and retry."));
      }}>Stop remote inference</button>
    </div>)}
  </section>;
}
