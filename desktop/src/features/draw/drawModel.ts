// Small, testable UI rules for the Draw toolbar and status bar.
import { LIMITS } from "./model";
import type { SaveState } from "./session";

export const SIZE_PRESETS = [1, 2, 4, 8, 16, 32, 64, 128];

/** A quick palette; any colour is available from the colour picker. */
export const SWATCHES = [
  { name: "Black", color: "#000000" },
  { name: "Dark grey", color: "#5f6368" },
  { name: "White", color: "#ffffff" },
  { name: "Red", color: "#e53935" },
  { name: "Orange", color: "#fb8c00" },
  { name: "Yellow", color: "#fdd835" },
  { name: "Green", color: "#43a047" },
  { name: "Blue", color: "#1e63e9" },
  { name: "Purple", color: "#8e24aa" },
];

/** Pen size in document pixels: whole pixels from 1, half a pixel at the bottom. */
export function brushSize(value: number): number {
  if (!Number.isFinite(value)) return 8;
  const clamped = Math.min(LIMITS.max_width, Math.max(LIMITS.min_width, value));
  return clamped < 1 ? 0.5 : Math.round(clamped);
}

// The size slider is logarithmic so 1–8 px get as much travel as 32–256 px.
const LOG_MIN = Math.log(LIMITS.min_width), LOG_MAX = Math.log(LIMITS.max_width);
export const sizeFromSlider = (position: number) =>
  brushSize(Math.exp(LOG_MIN + ((LOG_MAX - LOG_MIN) * Math.min(1000, Math.max(0, position))) / 1000));
export const sliderFromSize = (size: number) =>
  Math.round(((Math.log(brushSize(size)) - LOG_MIN) / (LOG_MAX - LOG_MIN)) * 1000);

export function saveLine(state: SaveState, error: string, open: boolean): { label: string; tone: "success" | "idle" | "error" | "live" } {
  if (!open) return { label: "", tone: "idle" };
  if (state === "saving") return { label: "Saving…", tone: "live" };
  if (state === "error") return { label: error && /^Could not save drawing/.test(error) ? error.split(":")[0] : "Could not save drawing", tone: "error" };
  return { label: "Saved locally", tone: "success" };
}
