// Shared by the IPC contract and the renderer; keep dependency-free.
export const PRESET_IDS = ["fast", "normal", "max", "uncensored", "now", "deep", "reimagine", "audio", "video"] as const;
export type PresetId = (typeof PRESET_IDS)[number];
/** Generation modes: This device only, never Remote AI. */
export const MEDIA_PRESETS: readonly string[] = ["reimagine", "audio", "video"];
