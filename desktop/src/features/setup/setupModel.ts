// First-run setup: wire types and pure helpers. Everything shown about packages,
// runtimes and models comes from the backend's runtime manifest and plan; this
// file never names a model, a file or a download.
import { SETUP_STEPS } from "../../../electron/setup-contracts";

export type SetupStep = (typeof SETUP_STEPS)[number];
export const STEPS: readonly SetupStep[] = SETUP_STEPS;
export const STEP_LABELS: Record<SetupStep, string> = {
  welcome: "Welcome",
  name: "Your name",
  system: "System check",
  package: "Package",
  runtimes: "Runtimes",
  models: "Models",
  verify: "Verify",
  connect: "OLIVE Connect",
  world: "Connect World",
  complete: "Done",
};

export type SetupState = "first_launch" | "incomplete" | "complete" | "skipped" | "existing" | "requires_repair";
export type ProfileId = "core" | "creator" | "complete";

export interface RuntimeRow {
  label: string;
  state: "found" | "needs_setup";
  reason: string | null;
  source: string | null;
  origin: string | null;
  paths: Record<string, string>;
  also_found: { origin: string; paths: Record<string, string> }[];
  validated_on_platform: boolean;
}
export interface Repair { feature: string; label: string; slot: string; action: string; detail: string }
export interface JobItem {
  id: string;
  name: string;
  kind: string;
  state: string;
  done_bytes: number;
  total_bytes: number;
  message: string;
  error: string | null;
}
export interface Job {
  job_id: string | null;
  profile?: string;
  state: "idle" | "running" | "done" | "failed" | "cancelled";
  items: JobItem[];
  done_bytes: number;
  total_bytes: number;
}
export interface SetupStatus {
  state: SetupState;
  reason: string | null;
  step: SetupStep;
  profile: ProfileId | null;
  optional: string[];
  origin: string;
  repairs: Repair[];
  verified_features: string[];
  preferred_name: string;
  target: string | null;
  manifest_source: "release" | "test";
  packaged: boolean;
  runtimes: Record<string, RuntimeRow>;
  installed: string[];
  job: Job;
}
export interface PublicEntry {
  id: string;
  kind: string;
  name: string;
  provides: string;
  version: string | null;
  installable: boolean;
  /** unidentified | license_identified | engineering_reviewed | release_approved (owner gate). */
  release_state?: "unidentified" | "license_identified" | "engineering_reviewed" | "release_approved";
  validated: boolean;
  download_bytes: number;
  installed_bytes: number;
  licence: { spdx: string | null; name: string | null; url: string | null; acceptance_required: boolean };
  publisher: string | null;
  link: string | null;
  reason: string | null;
  /** How far a built artefact has got when it is not downloadable yet (e.g. built_validated_unpublished). */
  artefact_state?: string | null;
  /** Pinned files setup fetches from another source for this item (Creator: wheels from PyPI). */
  direct_downloads?: { package: string; version: string; download_bytes: number; licence: string | null }[];
  direct_download_bytes?: number;
  /** Where they come from (e.g. "PyPI"); attribution stays per package, never one publisher. */
  direct_source?: string | null;
  direct_summary?: string | null;
}
export type ItemAction = "present" | "install" | "different_build" | "choose" | "external" | "unavailable";
export interface PlanItem { slot: string; entry: PublicEntry; action: ItemAction; detail: string; optional: boolean }
export type FeatureState = "ready" | "installable" | "not_in_build" | "external" | "choose";
export interface PlanFeature {
  id: string;
  label: string;
  profile: ProfileId;
  state: FeatureState;
  note: string | null;
  optional_component: boolean;
  missing: string[];
}
export interface Volume { label: string; path: string; required_bytes: number; free_bytes: number | null; enough: boolean }
export interface Plan {
  profile: ProfileId;
  target: string | null;
  source: "release" | "test";
  features: PlanFeature[];
  items: PlanItem[];
  default: string[];
  offered: string[];
  selected: string[];
  some_unavailable: boolean;
  totals: { download_bytes: number; installed_bytes: number; volumes: Volume[]; enough_space: boolean };
}
export interface ManifestProfile { id: ProfileId; label: string; summary: string; includes: ProfileId[] }
export interface ManifestFeature {
  id: string;
  label: string;
  profile: ProfileId;
  requires: string[];
  optional?: string[] | null;
  note?: string | null;
  optional_component?: boolean | null;
}
export interface Manifest {
  target: string | null;
  source: "release" | "test";
  manifest_version: string;
  profiles: ManifestProfile[];
  features: ManifestFeature[];
  entries: PublicEntry[];
}
export interface VerificationRow { id: string; label: string; state: string; detail: string }
export interface Verification {
  ok: boolean;
  profile: ProfileId;
  features: VerificationRow[];
  fast: { state: string; detail: string } | null;
  media: { state: string; detail: string } | null;
  some_unavailable: boolean;
}
export interface Gpu { vendor: string | null; name: string | null; vram_bytes: number | null; shared_memory?: boolean }
export interface SystemCheck {
  os: { name: string; version: string; architecture: string };
  target: string | null;
  cpu: { name: string | null; logical_cores: number | null; physical_cores: number | null };
  memory_bytes: number | null;
  gpus: Gpu[];
  storage: { label: string; path: string; free_bytes: number | null }[];
  application: { name: string; version: string; packaged: boolean };
  assessment: { state: "verified" | "not_verified" | "unsupported"; label: string; detail: string };
}

/** The wizard opens by itself only for a new profile or one left part-way. */
export function opensAutomatically(status: SetupStatus | null): boolean {
  return Boolean(status && (status.state === "first_launch" || status.state === "incomplete"));
}

export function resumeStep(status: SetupStatus): SetupStep {
  return status.state === "first_launch" ? "welcome" : status.step;
}

export function nextStep(step: SetupStep): SetupStep {
  return STEPS[Math.min(STEPS.indexOf(step) + 1, STEPS.length - 1)];
}
export function previousStep(step: SetupStep): SetupStep {
  return STEPS[Math.max(STEPS.indexOf(step) - 1, 0)];
}

export function bytes(value: number | null | undefined): string {
  if (value == null) return "Not measurable";
  if (value < 1e6) return `${Math.max(1, Math.round(value / 1e3))} KB`;
  if (value < 1e9) return `${Math.round(value / 1e6)} MB`;
  return `${(value / 1e9).toFixed(value < 1e10 ? 1 : 0)} GB`;
}

/** A profile and every profile it includes, innermost first. */
export function profileChain(manifest: Manifest, id: ProfileId): ProfileId[] {
  const seen: ProfileId[] = [];
  const visit = (name: ProfileId) => {
    if (seen.includes(name)) return;
    manifest.profiles.find((p) => p.id === name)?.includes.forEach(visit);
    seen.push(name);
  };
  visit(id);
  return seen;
}

/** What a package adds over the one it includes (Creator lists only its own additions). */
export function profileAdditions(manifest: Manifest, id: ProfileId): ManifestFeature[] {
  return manifest.features.filter((f) => f.profile === id);
}

/** Whether every component a feature needs can be installed by this build here. */
export function featureAvailableInBuild(manifest: Manifest, feature: ManifestFeature): boolean {
  return feature.requires.every((slot) => manifest.entries.some((e) => e.provides === slot && e.installable));
}

export function profileHasUnavailable(manifest: Manifest, id: ProfileId): boolean {
  const chain = profileChain(manifest, id);
  return manifest.features.some((f) => chain.includes(f.profile) && !f.optional_component && !featureAvailableInBuild(manifest, f));
}

const RUNTIME_SLOTS = new Set(["ollama-runtime", "image-engine", "video-engine", "audio-engine", "video-gguf-loader", "ffmpeg"]);
/** Runtimes step: engines. Models step: models and optional components. */
export function isRuntimeSlot(slot: string) {
  return RUNTIME_SLOTS.has(slot);
}

export function selectedTotals(plan: Plan, selected: Set<string>) {
  let download = 0;
  for (const item of plan.items)
    if (item.action === "install" && selected.has(item.entry.id)) download += item.entry.download_bytes;
  return download;
}

export function jobRunning(job: Job | null | undefined) {
  return job?.state === "running";
}

export function itemLabel(item: PlanItem): string {
  switch (item.action) {
    case "present":
      return "Already on this computer";
    case "different_build":
      return "Installed (a different build, kept as it is)";
    case "install":
      return item.optional ? "Optional" : "Will be installed";
    case "choose":
      return "Choose which one to use";
    case "external":
      return "Install it yourself";
    default:
      return "Not yet available in this build";
  }
}

/** One plain line for an item that also downloads pinned dependencies from another source; null otherwise. */
export function directDownloadNote(entry: PublicEntry): string | null {
  if (!entry.direct_downloads?.length || !entry.direct_source) return null;
  const summary = entry.direct_summary ? `, ${entry.direct_summary},` : "";
  return `Includes ${bytes(entry.direct_download_bytes ?? 0)} of pinned dependencies downloaded directly from ${entry.direct_source}${summary} under their respective licences`;
}

export function jobItemLabel(item: JobItem): string {
  const labels: Record<string, string> = {
    queued: "Waiting",
    downloading: "Downloading",
    verifying: "Verifying",
    extracting: "Unpacking",
    installing: "Installing",
    pulling: "Downloading",
    done: "Installed",
    present: "Already installed",
    different_build: "Kept your existing build",
    failed: "Failed",
    cancelled: "Cancelled",
  };
  return labels[item.state] ?? item.state;
}

export function verdictLabel(state: string): string {
  return (
    {
      ready: "Works",
      built_in: "Built in",
      not_in_build: "Not yet available in this build",
      needs_you: "Needs something you install",
      missing: "Missing",
      failed: "Failed",
      optional: "Optional, not installed",
    }[state] ?? state
  );
}

export function hardwareLines(system: SystemCheck) {
  const gpu = system.gpus.length
    ? system.gpus.map((g) => [g.name || "Unknown GPU", g.vendor ? `(${g.vendor.toUpperCase()})` : ""].join(" ").trim()).join(", ")
    : "No dedicated GPU found";
  const vram = system.gpus.find((g) => g.vram_bytes)?.vram_bytes;
  const shared = system.gpus.some((g) => g.shared_memory);
  return [
    { label: "System", value: `${system.os.name} ${system.os.version}`.trim() + ` · ${system.os.architecture}` },
    { label: "Processor", value: system.cpu.name ? `${system.cpu.name} · ${system.cpu.logical_cores ?? "?"} threads` : "Not measurable" },
    { label: "Memory", value: bytes(system.memory_bytes) },
    { label: "Graphics", value: gpu },
    { label: "Video memory", value: vram ? bytes(vram) : shared ? "Shared with system memory" : "Not measurable" },
    ...system.storage.map((s) => ({ label: `Free space (${s.label})`, value: bytes(s.free_bytes) })),
    { label: "OLIVE", value: `${system.application.version}${system.application.packaged ? "" : " (source)"}` },
  ];
}
