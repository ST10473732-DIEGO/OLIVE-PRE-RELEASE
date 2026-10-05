import { z } from "zod";

// First-run setup: the renderer can only name manifest entries, never a URL, a command or a
// download location. Mirrors olive/bridge/setup_routes.py.
const empty = z.object({}).strict();
const entry = z.string().regex(/^[a-z0-9][a-z0-9._-]{0,79}$/);
const entries = z.array(entry).max(64);
const profile = z.enum(["core", "creator", "complete"]);
const job = z.string().regex(/^[0-9a-f]{32}$/);
const runtime = z.enum(["ollama", "comfy", "video_comfy", "voicestudio", "media_models"]);
const location = z.string().min(1).max(4096).refine((v) => !v.includes("\0"));
export const SETUP_STEPS = ["welcome", "name", "system", "package", "runtimes", "models", "verify", "connect", "world", "complete"] as const;

export const setupSchemas = {
  "runtime.setup_status": empty,
  "runtime.setup_update": z
    .object({
      step: z.enum(SETUP_STEPS).optional(),
      profile: profile.optional(),
      preferred_name: z.string().max(120).refine((v) => !v.includes("\0")).optional(),
      action: z.enum(["skip", "reset", "resume"]).optional(),
      optional: entries.optional(),
    })
    .strict(),
  "runtime.system_check": z.object({ refresh: z.boolean().optional() }).strict(),
  "runtime.manifest": empty,
  "runtime.install_plan": z.object({ profile, selected: entries.optional() }).strict(),
  "runtime.install_start": z.object({ profile, entries: entries.min(1) }).strict(),
  "runtime.install_progress": z.object({ job_id: job.optional() }).strict(),
  "runtime.install_cancel": z.object({ job_id: job }).strict(),
  "runtime.install_retry": z.object({ job_id: job }).strict(),
  "runtime.uninstall": z.object({ entry_id: entry }).strict(),
  "runtime.choose": z
    .object({
      name: runtime,
      paths: z
        .object({ executable: location, models: location, root: location, python: location, url: location, path: location })
        .partial()
        .strict()
        .optional(),
      folder: location.optional(),
    })
    .strict()
    .refine((v) => (v.paths === undefined) !== (v.folder === undefined), "Choose either detected paths or a folder"),
  "runtime.forget": z.object({ name: runtime }).strict(),
  "runtime.verify": z.object({ profile, run_fast: z.boolean().optional(), media_smoke: z.boolean().optional() }).strict(),
};
