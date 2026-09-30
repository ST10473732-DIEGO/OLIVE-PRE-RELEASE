import { MEDIA_PRESETS } from "../../electron/presets";
import type { Preset, Snapshot } from "./api";

export type RuntimeTone = "idle" | "working" | "attention" | "error";
export interface RuntimeState {
  /** What the application itself is doing. */
  label: string;
  /** Model/connection availability, stated separately from the activity. */
  detail: string;
  tone: RuntimeTone;
  /** Long form for tooltips and the activity centre. */
  full: string;
}

// Activity and model availability are different facts. "Ready" on its own read
// as a promise that the AI was available even when Ollama was unreachable, so
// the two are always reported as a pair: "Idle · AI offline".
export function describeModel(ollama: string | undefined): {
  detail: string;
  available: boolean;
  full: string;
} {
  const text = (ollama || "").trim();
  if (!text || text === "Checking Ollama")
    return { detail: "checking AI", available: false, full: "Checking the local model service." };
  if (text.startsWith("Ollama unavailable"))
    return {
      detail: "AI offline",
      available: false,
      // Unreachable is not the same fact as "no model installed": an
      // unreachable server cannot tell us what it has.
      full: "The local model service is not reachable, so model availability is unknown. Start Ollama and refresh Models.",
    };
  if (text.includes("No models installed"))
    return {
      detail: "no model installed",
      available: false,
      full: "The local model service is running but no model is installed yet.",
    };
  if (text.startsWith("Ollama ready"))
    return { detail: "AI ready", available: true, full: "A local model is available." };
  return { detail: text.toLowerCase(), available: false, full: text };
}

const ACTIVITY: Record<string, { label: string; tone: RuntimeTone }> = {
  "Approval required": { label: "Approval required", tone: "attention" },
  Paused: { label: "Paused", tone: "attention" },
  Pausing: { label: "Pausing", tone: "attention" },
  Degraded: { label: "Degraded", tone: "attention" },
  Error: { label: "Error", tone: "error" },
  Disconnected: { label: "Disconnected", tone: "error" },
  Thinking: { label: "Working", tone: "working" },
  Working: { label: "Working", tone: "working" },
  Starting: { label: "Starting", tone: "working" },
};

export function runtimeState(
  activity: string,
  snapshot: Snapshot | null,
  approvals: number,
  busy: boolean,
): RuntimeState {
  const model = describeModel(snapshot?.home.status.ollama);
  if (approvals > 0)
    return {
      label: "Approval required",
      detail: approvals === 1 ? "1 action waiting" : `${approvals} actions waiting`,
      tone: "attention",
      full: "OLIVE is waiting for you to review an action.",
    };
  const known = ACTIVITY[activity];
  if (known && known.tone !== "idle")
    return { label: known.label, detail: model.detail, tone: known.tone, full: model.full };
  if (busy) return { label: "Working", detail: model.detail, tone: "working", full: model.full };
  if (!snapshot)
    return { label: "Starting", detail: "", tone: "working", full: "OLIVE is starting." };
  return { label: "Idle", detail: model.detail, tone: "idle", full: model.full };
}

export type StatusTone = "ok" | "warning" | "error" | "neutral" | "computing";
export interface StatusSummary {
  /** Short title-bar text, always a word, never colour alone. */
  label: string;
  tone: StatusTone;
  /** Tooltip / accessible description. */
  full: string;
}

/** Backend events after which the renderer re-reads its one canonical
 *  Snapshot. "models" follows every model-inventory refresh (startup and
 *  Settings › Models), so preset readiness is never left stale. */
export const SNAPSHOT_TOPICS: readonly string[] = ["runtime.ready", "runtime.initialized", "chats", "models"];

/** Whether a preset can run on this device, as the backend preset catalogue
 *  reports it. Ollama presets say exactly "Ready" or "Needs setup"; media
 *  presets describe their engine, so only `available` decides for them. Every
 *  surface (title bar, Home, Chat, Settings) uses this one rule. */
export function presetReady(preset: Pick<Preset, "id" | "status" | "available">): boolean {
  return preset.available !== false && (MEDIA_PRESETS.includes(preset.id) || preset.status === "Ready");
}

/** A preset's name in the Chat and Home selectors, with its setup state when
 *  it cannot run here. Remote conversations only flag presets a paired device
 *  never serves. */
export function presetLabel(preset: Pick<Preset, "id" | "name" | "status" | "available">, remote = false): string {
  if (remote)
    return ["uncensored", "now", "deep", ...MEDIA_PRESETS].includes(preset.id) ? `${preset.name} · Unavailable remotely` : preset.name;
  return presetReady(preset) ? preset.name : `${preset.name} · ${preset.status}`;
}

/** Title-bar model status. It names the current conversation's preset and
 *  says whether it can run here, from the real preset catalogue and the real
 *  Ollama reachability. A conversation set to run on a paired device says so. */
export function modelStatus(snapshot: Snapshot | null, runOnName = ""): StatusSummary {
  if (!snapshot) return { label: "Starting", tone: "neutral", full: "OLIVE is starting." };
  const model = describeModel(snapshot.home.status.ollama);
  const preset = snapshot.presets?.find((p) => p.id === snapshot.chat?.preset);
  const short = preset ? preset.name.replace(/^OLIVE\s+/, "") : "";
  if (snapshot.chat?.run_on)
    return {
      label: short ? `${short} · ${runOnName || "paired device"}` : `Runs on ${runOnName || "a paired device"}`,
      tone: "neutral",
      full: `This conversation runs on ${runOnName || "a paired device"}; answers are attributed to that device.`,
    };
  if (!model.available)
    return {
      label: model.detail === "checking AI" ? "Checking AI" : model.detail === "AI offline" ? "AI offline" : "No model",
      tone: model.detail === "checking AI" ? "neutral" : "warning",
      full: model.full,
    };
  if (preset && !presetReady(preset))
    return { label: `${short} needs setup`, tone: "warning", full: `${preset.name}: ${preset.status}. Open Settings › Models.` };
  return { label: short ? `${short} ready` : "AI ready", tone: "ok", full: preset ? `${preset.name} is available on this device.` : model.full };
}

export interface ConnectSnapshotLike {
  network?: { state?: string };
  devices?: { device_id?: string; display_name?: string; device_class?: string; trust_state?: string; live?: { state?: string } | null }[];
}
/** Welcome consumes the same live snapshot as the shell; never cache startup Off. */
export function welcomeDevices(value: ConnectSnapshotLike | null): { detail: string; done: boolean; waiting: boolean } {
  const state = value?.network?.state;
  if (!state) return { detail: "Checking OLIVE Connect…", done: false, waiting: true };
  const paired = (value?.devices || []).filter((device) => device.trust_state === "paired");
  const names = paired.slice(0, 2).map((device) => device.display_name || "Paired device").join(", ") +
    (paired.length > 2 ? ` and ${paired.length - 2} more` : "");
  const prefix = paired.length ? `${names} paired · ` : "";
  if (state === "off") return { detail: `${prefix}Connect is off`, done: false, waiting: false };
  if (state === "starting") return { detail: `${prefix}Connect is starting…`, done: false, waiting: true };
  if (state !== "on") return { detail: `${prefix}Connect status unavailable · check Devices`, done: false, waiting: false };
  if (!paired.length) return { detail: "None paired yet · pair a phone from Devices", done: false, waiting: false };
  const online = paired.filter((device) => device.live?.state === "online").length;
  return {
    detail: online === paired.length ? `${names} connected` : `${prefix}${online ? `${online} connected` : "Connect is on"}`,
    done: online > 0,
    waiting: false,
  };
}
/** Title-bar Connect status from the real Connect snapshot. Paired is not the
 *  same as online, and neither implies any permission. */
export function connectSummary(value: ConnectSnapshotLike | null): StatusSummary {
  if (!value || !value.network) return { label: "Connect", tone: "neutral", full: "Connect status is not available yet." };
  if (value.network.state !== "on") return { label: "Connect off", tone: "neutral", full: "OLIVE Connect is off. Open Devices to turn it on." };
  const paired = (value.devices || []).filter((d) => d.trust_state === "paired");
  const online = paired.filter((d) => d.live?.state === "online").length;
  if (!paired.length) return { label: "No devices", tone: "neutral", full: "Connect is on. No device is paired." };
  return {
    label: online === 1 ? "1 device online" : `${online} devices online`,
    tone: online ? "ok" : "neutral",
    full: `${paired.length} paired ${paired.length === 1 ? "device" : "devices"}, ${online} online. Pairing grants no access by itself.`,
  };
}
