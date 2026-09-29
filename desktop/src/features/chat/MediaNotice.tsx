import { useEffect, useState } from "react";
import { Info, AlertTriangle } from "lucide-react";
import { call, type Chat, type Preset } from "../../services/api";

/** Attribution labels for media turns: MODE · KIND · This device. */
export const MEDIA_LABELS: Record<string, string> = {
  reimagine: "REIMAGINE · IMAGE",
  audio: "AUDIO · SPEECH",
  video: "VIDEO · LTX",
};

const GUIDE: Record<string, string> = {
  reimagine: "REIMAGINE creates images on this device. Attach one image to edit it; the original is kept unchanged.",
  audio: "AUDIO speaks your text on this device. Start with “Say:” followed by the words.",
  video: "VIDEO creates a short clip with sound on this device, about two seconds. Text prompts only.",
};

export function mediaPlaceholder(preset?: string): string {
  return ({
    reimagine: "Describe an image to create, or attach one and describe the edit…",
    audio: "Say: the words OLIVE should speak…",
    video: "Describe a short video to generate…",
  } as Record<string, string>)[preset || ""] || "";
}

function VoicePicker({ busy, report }: { busy: boolean; report: (error: unknown) => void }) {
  const [voices, setVoices] = useState<{ selected: string; voices: { id: string; name: string }[] }>();
  useEffect(() => {
    let live = true;
    void call<typeof voices>("media.voices", {}).then((v) => { if (live) setVoices(v); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  // Only voices the local service actually lists; nothing is invented.
  if (!voices?.voices.length) return null;
  return <label className="media-voice">Voice
    <select aria-label="AUDIO voice" value={voices.selected} disabled={busy}
      onChange={(e) => void call<typeof voices>("media.select_voice", { voice: e.target.value }).then(setVoices).catch(report)}>
      {voices.voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
    </select>
  </label>;
}

export function MediaNotice({ chat, preset, busy, openTools, report }: {
  chat: Chat; preset: Preset; busy: boolean; openTools: () => void; report: (error: unknown) => void;
}) {
  if (chat.run_on)
    return <div className="notice chat-notice" data-tone="warning" role="status">
      <AlertTriangle size={14} aria-hidden="true" />
      <span className="grow">{preset.name} runs on This device only. Select This device to generate media; nothing is sent to the paired device.</span>
    </div>;
  const ready = preset.available !== false;
  return <div className="notice chat-notice" data-tone={ready ? undefined : "warning"} role="note">
    {ready ? <Info size={14} aria-hidden="true" /> : <AlertTriangle size={14} aria-hidden="true" />}
    <span className="grow">{ready ? GUIDE[preset.id] : `${preset.name}: ${preset.status}. Nothing is downloaded automatically.`}</span>
    {preset.id === "audio" && ready && <VoicePicker busy={busy} report={report} />}
    {preset.id === "reimagine" && <button className="compact quiet" onClick={openTools} title="Advanced local media tools: raster edits, SDXL workflow and engine setup">Open media tools</button>}
  </div>;
}
