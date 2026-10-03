import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { validateCall } from "../electron/contracts";
import {
  bytes,
  featureAvailableInBuild,
  hardwareLines,
  isRuntimeSlot,
  itemLabel,
  nextStep,
  opensAutomatically,
  previousStep,
  profileAdditions,
  profileChain,
  profileHasUnavailable,
  resumeStep,
  STEPS,
  type Manifest,
  type PlanItem,
  type SetupStatus,
  type SystemCheck,
} from "../src/features/setup/setupModel";

const entry = (id: string, provides: string, installable: boolean) => ({
  id, kind: "ollama-model", name: id, provides, version: null, installable, validated: false,
  download_bytes: 1e9, installed_bytes: 1e9,
  licence: { spdx: "Apache-2.0", name: null, url: null, acceptance_required: false },
  publisher: null, link: null, reason: installable ? null : "Not cleared",
});
const manifest: Manifest = {
  target: "linux-x86_64", source: "release", manifest_version: "1.0.0",
  profiles: [
    { id: "core", label: "OLIVE Core", summary: "", includes: [] },
    { id: "creator", label: "OLIVE Creator", summary: "", includes: ["core"] },
    { id: "complete", label: "OLIVE Complete", summary: "", includes: ["creator"] },
  ],
  features: [
    { id: "fast", label: "FAST", profile: "core", requires: ["ollama-runtime", "model-fast"] },
    { id: "notes", label: "Notes", profile: "core", requires: [] },
    { id: "reimagine", label: "REIMAGINE", profile: "creator", requires: ["image-engine"] },
    { id: "browser_automation", label: "Browser automation", profile: "complete", requires: ["playwright"], optional_component: true },
  ],
  entries: [
    entry("runtime", "ollama-runtime", true), entry("fast", "model-fast", true),
    entry("comfy", "image-engine", false), entry("pw", "playwright", false),
  ],
};
const status = (state: SetupStatus["state"], step: SetupStatus["step"] = "models") =>
  ({ state, step } as SetupStatus);

describe("first-run setup model", () => {
  it("opens by itself only for a new or unfinished profile", () => {
    expect(opensAutomatically(status("first_launch"))).toBe(true);
    expect(opensAutomatically(status("incomplete"))).toBe(true);
    for (const state of ["complete", "skipped", "existing", "requires_repair"] as const)
      expect(opensAutomatically(status(state))).toBe(false);
    expect(opensAutomatically(null)).toBe(false);
  });
  it("resumes where the person left off", () => {
    expect(resumeStep(status("incomplete", "models"))).toBe("models");
    expect(resumeStep(status("first_launch", "models"))).toBe("welcome");
    expect(STEPS).toEqual(["welcome", "name", "system", "package", "runtimes", "models", "verify", "connect", "world", "complete"]);
    expect(nextStep("verify")).toBe("connect");
    expect(previousStep("welcome")).toBe("welcome");
    expect(nextStep("complete")).toBe("complete");
  });
  it("derives packages from the manifest and flags unavailable components", () => {
    expect(profileChain(manifest, "complete")).toEqual(["core", "creator", "complete"]);
    expect(profileAdditions(manifest, "creator").map((f) => f.id)).toEqual(["reimagine"]);
    expect(profileHasUnavailable(manifest, "core")).toBe(false);
    expect(profileHasUnavailable(manifest, "creator")).toBe(true);
    // An optional component that is missing does not make a package "incomplete".
    expect(featureAvailableInBuild(manifest, manifest.features[3])).toBe(false);
  });
  it("labels plan items truthfully", () => {
    const item = (action: PlanItem["action"], optional = false) =>
      ({ slot: "model-fast", entry: manifest.entries[1], action, detail: "", optional } as PlanItem);
    expect(itemLabel(item("unavailable"))).toBe("Not yet available in this build");
    expect(itemLabel(item("present"))).toBe("Already on this computer");
    expect(itemLabel(item("install", true))).toBe("Optional");
    expect(isRuntimeSlot("ollama-runtime")).toBe(true);
    expect(isRuntimeSlot("model-fast")).toBe(false);
    expect(bytes(5_225_388_164)).toBe("5.2 GB");
    expect(bytes(null)).toBe("Not measurable");
  });
  it("never claims unmeasured hardware", () => {
    const system = {
      os: { name: "Linux", version: "6", architecture: "x86_64" }, target: "linux-x86_64",
      cpu: { name: null, logical_cores: null, physical_cores: null }, memory_bytes: null,
      gpus: [{ vendor: "apple", name: "Apple M3", vram_bytes: null, shared_memory: true }],
      storage: [{ label: "OLIVE data", path: "/x", free_bytes: null }],
      application: { name: "OLIVE", version: "1.0.0", packaged: true },
      assessment: { state: "not_verified", label: "Not yet verified", detail: "" },
    } as SystemCheck;
    const lines = Object.fromEntries(hardwareLines(system).map((l) => [l.label, l.value]));
    expect(lines.Processor).toBe("Not measurable");
    expect(lines.Memory).toBe("Not measurable");
    expect(lines["Video memory"]).toBe("Shared with system memory");
  });
});

describe("setup contracts", () => {
  const call = (method: string, args: unknown) => validateCall({ id: crypto.randomUUID(), method, args });
  it("accepts manifest entry ids only", () => {
    expect(() => call("runtime.install_start", { profile: "core", entries: ["qwen3-8b"] })).not.toThrow();
    for (const args of [
      { profile: "core", entries: ["https://evil.example/x"] },
      { profile: "core", entries: [] },
      { profile: "pro", entries: ["qwen3-8b"] },
      { profile: "core", entries: ["qwen3-8b"], url: "https://x" },
    ])
      expect(() => call("runtime.install_start", args)).toThrow();
  });
  it("keeps runtime choices to known fields", () => {
    expect(() => call("runtime.choose", { name: "ollama", folder: "/opt/ollama" })).not.toThrow();
    expect(() => call("runtime.choose", { name: "ollama", paths: { executable: "/x" }, folder: "/y" })).toThrow();
    expect(() => call("runtime.choose", { name: "ollama", paths: { command: "rm -rf /" } })).toThrow();
    expect(() => call("runtime.choose", { name: "bash", folder: "/y" })).toThrow();
    expect(() => call("runtime.setup_update", { preferred_name: "x".repeat(121) })).toThrow();
    expect(() => call("runtime.install_progress", { job_id: "../../etc" })).toThrow();
  });
});

describe("renderer stays manifest-driven", () => {
  it("names no model, file or download URL in setup code", () => {
    const folder = path.join(__dirname, "../src/features/setup");
    const source = readdirSync(folder).map((name) => readFileSync(path.join(folder, name), "utf8")).join("\n");
    for (const forbidden of [/qwen/i, /gpt-oss/i, /\.safetensors/, /\.gguf/, /https:\/\//, /ollama-linux/, /\.tar\./])
      expect(source).not.toMatch(forbidden);
  });
});
