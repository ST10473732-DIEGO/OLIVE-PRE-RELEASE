import { useState } from "react";
import { ExternalLink, Download, ImagePlus, Info, Loader2 } from "lucide-react";
import { call, type Chat, type MediaArtifact } from "../../services/api";
import { Sheet } from "../../components/Sheet";
import { Details } from "../../components/WorkspacePage";
import "./media.css";

/** Same-origin URL for a generated file; the path stays in the main process. */
export function mediaUrl(id: string): string {
  return /^[0-9a-f]{32}$/.test(id) ? `/__media/${id}` : "";
}

const NOUN: Record<MediaArtifact["kind"], string> = { image: "image", audio: "audio clip", video: "video" };

/** One short, user-facing line: size/length and model family, never filenames or paths. */
export function artifactSummary(artifact: MediaArtifact): string {
  const parts: string[] = [];
  if (artifact.width && artifact.height) parts.push(`${artifact.width} × ${artifact.height}`);
  if (artifact.duration_seconds) parts.push(`${artifact.duration_seconds.toFixed(1)} s`);
  if (artifact.kind === "video" && artifact.has_audio) parts.push("with sound");
  if (artifact.parameters?.operation === "edit") parts.push("edited from your attachment");
  if (artifact.generation_mode === "image_to_video") parts.push("from your image");
  if (artifact.generator?.family) parts.push(artifact.generator.family);
  return parts.join(" · ");
}

/** Details shown only on request: generation parameters, still no filesystem paths. */
export function artifactDetails(artifact: MediaArtifact) {
  return {
    kind: artifact.kind, file: artifact.filename, type: artifact.mime_type, created: artifact.created_at,
    mode: artifact.mode, generator: artifact.generator, parameters: artifact.parameters,
    references: artifact.source_ids?.length || 0, bytes: artifact.size_bytes,
    ...(artifact.kind === "video" && artifact.target_duration_seconds !== undefined ? {
      target_seconds: artifact.target_duration_seconds, measured_seconds: artifact.duration_seconds,
      segments: artifact.segment_count, generation: artifact.generation_mode, continuation: artifact.continuation,
    } : {}),
  };
}

function Player({ artifact, missing }: { artifact: MediaArtifact; missing: () => void }) {
  const src = mediaUrl(artifact.id);
  const prompt = String(artifact.parameters?.prompt || artifact.parameters?.text || "").slice(0, 160);
  if (artifact.kind === "image")
    return <img className="media-image" src={src} alt={prompt ? `Generated image: ${prompt}` : "Generated image"}
      width={artifact.width} height={artifact.height} onError={missing} />;
  if (artifact.kind === "audio")
    return <audio className="media-audio" controls preload="metadata" src={src} aria-label="Generated speech" onError={missing} />;
  return <video className="media-video" controls preload="metadata" playsInline src={src} aria-label="Generated video"
    width={artifact.width} height={artifact.height} onError={missing} />;
}

export function MediaArtifacts({ chat, artifacts, busy, changed, report }: {
  chat: Chat; artifacts: MediaArtifact[]; busy: boolean; changed: (chat: Chat) => void; report: (error: unknown) => void;
}) {
  const [missing, setMissing] = useState<Record<string, boolean>>({});
  const [details, setDetails] = useState<MediaArtifact>();
  return <div className="media-artifacts">
    {artifacts.map((artifact) => {
      const gone = artifact.available === false || missing[artifact.id];
      return <figure className="media-artifact" data-kind={artifact.kind} key={artifact.id}>
        {gone
          ? <p className="media-missing" role="status">This {NOUN[artifact.kind]} is no longer available on this device.</p>
          : <Player artifact={artifact} missing={() => setMissing((m) => ({ ...m, [artifact.id]: true }))} />}
        <figcaption>
          <span className="media-meta">{artifactSummary(artifact)}</span>
          <span className="media-actions">
            {!gone && <button className="icon-button" title="Open in the system viewer" aria-label={`Open generated ${NOUN[artifact.kind]}`}
              onClick={() => void window.olive.fileAction({ action: "media-open", artifact_id: artifact.id }).catch(report)}>
              <ExternalLink size={14} aria-hidden="true" /></button>}
            {!gone && <button className="icon-button" title="Save a copy" aria-label={`Save a copy of the generated ${NOUN[artifact.kind]}`}
              onClick={() => void window.olive.fileAction({ action: "media-export", artifact_id: artifact.id }).catch(report)}>
              <Download size={14} aria-hidden="true" /></button>}
            {!gone && artifact.kind === "image" && <button className="icon-button" disabled={busy} title="Use as the reference for the next edit"
              aria-label="Use generated image as reference"
              onClick={() => void call<Chat>("media.reuse", { chat_id: chat.id, artifact_id: artifact.id }).then(changed).catch(report)}>
              <ImagePlus size={14} aria-hidden="true" /></button>}
            <button className="icon-button" title="Generation details" aria-label={`Generation details for this ${NOUN[artifact.kind]}`}
              onClick={() => setDetails(artifact)}><Info size={14} aria-hidden="true" /></button>
          </span>
        </figcaption>
      </figure>;
    })}
    <Sheet open={details !== undefined} onOpenChange={(open) => { if (!open) setDetails(undefined); }}
      title="Generation details" description="Recorded when this media was created on this device.">
      {details && <Details value={artifactDetails(details)} title="Artifact" />}
    </Sheet>
  </div>;
}

/** Placeholder turn while a media request runs: stage text only, no invented progress. */
export function MediaProgress({ label, stage }: { label: string; stage: string }) {
  return <p className="media-progress" role="status" aria-live="polite">
    <Loader2 size={14} className="media-spin" aria-hidden="true" />
    <span>{stage}</span><span className="sr-only"> · {label}</span>
  </p>;
}
