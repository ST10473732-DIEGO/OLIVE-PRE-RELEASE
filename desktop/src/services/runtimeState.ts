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
