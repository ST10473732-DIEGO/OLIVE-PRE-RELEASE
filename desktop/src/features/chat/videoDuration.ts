/** OLIVE VIDEO target duration in desktop Chat. The backend (media.video_plan)
 * resolves Auto from the prompt and plans segments; these helpers only
 * present its answer and validate what the person types. */

export const DURATION_PRESETS = [2, 5, 10, 20, 30, 60] as const;

export interface VideoPlan {
  policy: { default_seconds: number; maximum_seconds: number; minimum_seconds: number; long_video_warning_seconds: number; setting: string };
  capability: {
    supports_text_to_video: boolean;
    supports_image_to_video: boolean;
    native_segment_seconds: number;
    max_images: number;
    duration: { configurable: boolean; maximum_seconds: number; minimum_seconds: number; default_seconds: number };
  };
  error: string | null;
  message: string;
  target_seconds?: number;
  source?: "explicit" | "prompt" | "default";
  prompt_seconds?: number | null;
  conflict?: boolean;
  segments?: number;
  long?: boolean;
  estimate_seconds?: [number, number] | null;
}

/** "20 s", "1 min", "1 min 30 s", "2.5 s". */
export function durationLabel(seconds: number): string {
  if (seconds < 60) return `${Number.isInteger(seconds) ? seconds : Number(seconds.toFixed(1))} s`;
  const whole = Math.round(seconds);
  const minutes = Math.floor(whole / 60), rest = whole % 60;
  return `${minutes} min${rest ? ` ${rest} s` : ""}`;
}

/** A custom entry in seconds or minutes; null when it is not a usable positive number. */
export function parseCustomDuration(value: string, unit: "s" | "min"): number | null {
  const text = value.trim().replace(",", ".");
  if (!/^\d{1,5}(\.\d{1,3})?$/.test(text)) return null;
  const seconds = Number(text) * (unit === "min" ? 60 : 1);
  return Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds * 1000) / 1000 : null;
}

/** Minutes range from measured segment times only; never an invented ETA. */
export function estimateLabel(estimate?: [number, number] | null): string {
  if (!estimate) return "";
  const low = Math.max(1, Math.round(estimate[0] / 60)), high = Math.max(low, Math.round(estimate[1] / 60));
  return low === high ? `About ${low} min` : `About ${low}–${high} min`;
}

/** One factual line under the control: what will be generated and how. */
export function planLine(plan?: VideoPlan): string {
  if (!plan) return "";
  if (plan.error) return plan.message;
  if (plan.target_seconds === undefined) return "";
  const parts = [`${durationLabel(plan.target_seconds)} target`];
  if (plan.source === "prompt") parts[0] += " from your prompt";
  if ((plan.segments || 1) > 1) parts.push(`${plan.segments} generation segments`);
  const eta = estimateLabel(plan.estimate_seconds);
  if (eta) parts.push(eta);
  else if (plan.long) parts.push("This may take several minutes on this computer");
  let line = parts.join(" · ");
  if (plan.conflict && plan.prompt_seconds) line += ` (your prompt says ${durationLabel(plan.prompt_seconds)}; the selected length is used)`;
  return line;
}

export type VideoInput = "text" | "image" | "too_many" | "unsupported";

/** What the attached images mean for VIDEO on this computer. */
export function videoInput(images: number, supportsImage: boolean): VideoInput {
  if (!images) return "text";
  if (!supportsImage) return "unsupported";
  return images > 1 ? "too_many" : "image";
}

export const VIDEO_INPUT_NOTICE: Record<VideoInput, string> = {
  text: "",
  image: "Image → Video",
  too_many: "OLIVE VIDEO currently accepts one starting image. Remove the extra images.",
  unsupported: "OLIVE VIDEO on this computer supports text prompts only. Remove the image or switch mode.",
};
