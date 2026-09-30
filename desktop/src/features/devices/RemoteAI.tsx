import { call } from "../../services/api";
import { useState } from "react";
import { Check, Circle } from "lucide-react";
import type { Device, RemoteChatSummary } from "./types";
import { sentence } from "./ui";

const GROUP_LABELS: Record<string, string> = { chat: "Chat", research: "Research", create: "Create" };
const KIND_LABELS: Record<string, string> = { image: "Images", document: "Documents", note: "Notes" };
const PERMISSION: Record<string, string> = { allow: "Allow", ask: "Ask", deny: "Off" };

/** Duration in the card's words: 3 min, 90 s. */
function limit(seconds?: number | null): string {
  if (!seconds) return "";
  return seconds >= 60 && seconds % 60 === 0 ? `${seconds / 60} min` : `${Math.round(seconds)} s`;
}

/** Extra facts a mode chip carries, only from the computer's own capability data. */
export function modeDetail(id: string, summary: RemoteChatSummary): string {
  if (id !== "video" || !summary.video) return "";
  const parts = [];
  if (summary.video.image_to_video) parts.push("Image → Video");
  if (summary.video.long_form && summary.video.maximum_seconds) parts.push(`up to ${limit(summary.video.maximum_seconds)}`);
  return parts.join(" · ");
}

/** The Remote AI matrix as a paired phone receives it (olive-chat/1), grouped for the card. */
export function RemoteChatMatrix({ summary }: { summary: RemoteChatSummary }) {
  const kinds = summary.attachments.filter((kind) => KIND_LABELS[kind]);
  return <div className="devices-remote-matrix">
    {summary.groups.map((group) => <div className="devices-remote-group" key={group.id}>
      <h4 className="devices-eyebrow">{GROUP_LABELS[group.id] || sentence(group.id)}</h4>
      <ul className="devices-chips" aria-label={`${GROUP_LABELS[group.id] || group.id} modes`}>
        {group.modes.map((mode) => {
          const detail = modeDetail(mode.id, summary);
          return <li key={mode.id} data-available={mode.available} data-tone={mode.available ? undefined : "warning"}
            title={mode.available ? detail || undefined : "Not set up on this computer. Nothing is downloaded automatically."}>
            {mode.available ? <Check size={12} aria-hidden="true" /> : <Circle size={10} aria-hidden="true" />}
            {mode.id.toUpperCase()}
            {mode.available ? detail && <small>{detail}</small> : <small>Needs setup</small>}
            <span className="sr-only">{mode.available ? " · Available" : " · Needs setup"}</span>
          </li>;
        })}
      </ul>
    </div>)}
    <div className="devices-remote-group">
      <h4 className="devices-eyebrow">Content</h4>
      <ul className="devices-chips" aria-label="Content">
        <li data-available={kinds.length > 0} data-tone={kinds.length ? undefined : "warning"}>
          {kinds.length ? <Check size={12} aria-hidden="true" /> : <Circle size={10} aria-hidden="true" />}
          Attachments
          {kinds.length > 0 && <small>{kinds.map((kind) => KIND_LABELS[kind]).join(" · ")}</small>}
          <span className="sr-only">{kinds.length ? " · Available" : " · Unavailable"}</span>
        </li>
      </ul>
    </div>
  </div>;
}

export function RemoteAI({ device, summary, refresh }: {
  device: Device; summary?: RemoteChatSummary | null; refresh: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const info = device.remote_ai;
  if (!info && !summary) return null;
  const decision = device.permissions?.find((p) => p.capability === "models.remote" && p.scope === null)?.decision || "deny";
  return <section className="devices-card" aria-label="Remote AI activity">
    <header className="devices-card-head">
      <div>
        <h3>Remote AI</h3>
        <p>Allows {device.display_name} to use approved Chat modes, research, attachments and local media generation on
          this computer. It never grants terminal, desktop control, file system or app access.</p>
      </div>
      <span className="devices-state" data-permission={decision}>Permission · {PERMISSION[decision] || sentence(decision)}</span>
    </header>
    {summary
      ? <RemoteChatMatrix summary={summary} />
      : <p className="devices-hint">This computer’s Remote AI capabilities are unavailable right now.</p>}
    {error && <p className="devices-inline-error" role="alert">{error}</p>}
    {info?.jobs.map((job) => <div className="devices-job" key={job.job_id}>
      <span className="devices-state" data-tone="computing">OLIVE {job.preset.toUpperCase()} · {sentence(job.state)}</span>
      <button onClick={() => {
        setError("");
        void call("connect.inference_stop", { device_id: device.device_id, job_id: job.job_id }).then(refresh)
          .catch(() => setError("Could not confirm Stop. Check this device’s connection and retry."));
      }}>Stop remote inference</button>
    </div>)}
  </section>;
}
