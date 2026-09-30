import { describe, expect, it } from "vitest";
import type { Preset, Snapshot } from "../src/services/api";
import { SNAPSHOT_TOPICS, modelStatus, presetLabel, presetReady } from "../src/services/runtimeState";

// Shapes the backend PresetCatalog returns (olive/services/presets.py).
const preset = (id: string, status: string, available: boolean, extra: Partial<Preset> = {}) =>
  ({ id, name: `OLIVE ${id.toUpperCase()}`, status, available, ...extra }) as Preset;
const NOW_SETUP = preset("now", "Needs setup", false, { detail: "Needs setup" });
const NOW_READY = preset("now", "Ready", true, { detail: "Local ready · live retrieval checked on request" });
const snapshot = (presets: Preset[], ollama = "Ollama ready", chatPreset = "now") =>
  ({ home: { status: { ollama }, recent: [], context: {} }, chat: { id: "c", preset: chatPreset }, presets }) as unknown as Snapshot;

describe("preset readiness follows the canonical Snapshot", () => {
  it("re-reads the Snapshot after a model inventory refresh", () => {
    expect(SNAPSHOT_TOPICS).toContain("models");
  });

  it("moves NOW from needs setup to ready when a refreshed Snapshot arrives", () => {
    // What App.tsx does: the stale Snapshot is replaced on the "models" event.
    let current = snapshot([NOW_SETUP], "Checking Ollama");
    expect(modelStatus(current).label).toBe("Checking AI");
    current = snapshot([NOW_SETUP]);
    expect(modelStatus(current)).toMatchObject({ label: "NOW needs setup", tone: "warning" });
    const refreshed = snapshot([NOW_READY]);
    if (SNAPSHOT_TOPICS.includes("models")) current = refreshed;
    expect(modelStatus(current)).toMatchObject({ label: "NOW ready", tone: "ok" });
  });

  it("gives the Chat and Home selectors the same answer as the title bar", () => {
    expect(presetLabel(NOW_SETUP)).toBe("OLIVE NOW · Needs setup");
    expect(presetLabel(NOW_READY)).toBe("OLIVE NOW");
    expect(presetLabel(NOW_READY, true)).toBe("OLIVE NOW · Unavailable remotely");
  });

  it("keeps NOW needing setup when its model is genuinely missing", () => {
    expect(presetReady(NOW_SETUP)).toBe(false);
    expect(modelStatus(snapshot([NOW_SETUP])).label).toBe("NOW needs setup");
  });

  it("never trusts a descriptive status alone, nor availability alone, for Ollama presets", () => {
    expect(presetReady(preset("now", "Local ready · live retrieval checked on request", true))).toBe(false);
    expect(presetReady(preset("normal", "Ready", false))).toBe(false);
    expect(presetReady(preset("normal", "Ready", true))).toBe(true);
  });

  it("reports AI offline before any preset when Ollama is unreachable", () => {
    const offline = snapshot([NOW_READY], "Ollama unavailable. Start Ollama and refresh Models");
    expect(modelStatus(offline)).toMatchObject({ label: "AI offline", tone: "warning" });
  });

  it("treats FAST, NORMAL, MAX and DEEP the same way", () => {
    for (const id of ["fast", "normal", "max", "deep"]) {
      const short = id.toUpperCase();
      expect(modelStatus(snapshot([preset(id, "Ready", true)], "Ollama ready", id)).label).toBe(`${short} ready`);
      expect(modelStatus(snapshot([preset(id, "Needs setup", false)], "Ollama ready", id)).label).toBe(`${short} needs setup`);
    }
  });

  it("leaves media readiness to engine availability", () => {
    const audio = preset("audio", "Ready · speech service starts on request", true);
    expect(presetReady(audio)).toBe(true);
    expect(presetLabel(audio)).toBe("OLIVE AUDIO");
    const video = preset("video", "Needs setup · model or workflow missing", false);
    expect(presetReady(video)).toBe(false);
    expect(presetLabel(video)).toBe("OLIVE VIDEO · Needs setup · model or workflow missing");
    expect(modelStatus(snapshot([audio], "Ollama ready", "audio")).label).toBe("AUDIO ready");
  });
});
