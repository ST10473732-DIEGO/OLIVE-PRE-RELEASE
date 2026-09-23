import type { Snapshot } from "./api";

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
  if (preset && preset.status !== "Ready" && preset.id !== "reimagine")
    return { label: `${short} needs setup`, tone: "warning", full: `${preset.name}: ${preset.status}. Open Settings › Models.` };
  return { label: short ? `${short} ready` : "AI ready", tone: "ok", full: preset ? `${preset.name} is available on this device.` : model.full };
}

export interface ConnectSnapshotLike {
  network?: { state?: string };
  devices?: { device_id?: string; display_name?: string; device_class?: string; trust_state?: string; live?: { state?: string } | null }[];
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
