import { z } from "zod";
const id = z.string().uuid();
const empty = z.object({}).strict();
const address = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[0-9a-fA-F:.]+$/);
const studioCapability = z.enum(["studio.view", "studio.edit", "studio.build", "studio.test", "studio.run", "studio.debug"]);
export const connectSchemas = {
  "connect.studio_local_workspaces": empty,
  "connect.studio_share": z.object({device_id: id, workspace_id: id}).strict(),
  "connect.studio_unshare": z.object({device_id: id, workspace_id: id}).strict(),
  "connect.studio_permission": z.object({device_id: id, workspace_id: id, capability: studioCapability, decision: z.enum(["deny", "ask", "allow"])}).strict(),
  "connect.studio_stop": z.object({device_id: id, job_id: id}).strict(),
  "connect.studio_request": z.object({device_id: id, workspace_id: id.optional(), share_revision: z.number().int().min(0),
    operation: z.enum(["workspaces", "tree", "read", "save", "build", "test", "run", "run_status", "run_cancel"]),
    arguments: z.record(z.string(), z.unknown())}).strict(),
  "connect.model_targets": empty,
  "connect.inference_stop": z.object({ device_id: id, job_id: id }).strict(),
  "connect.file_start": z.object({ transfer_id: id }).strict(),
  "connect.file_cancel": z.object({ transfer_id: id }).strict(),
  "connect.file_dismiss": z.object({ transfer_id: id }).strict(),
  "connect.sync_now": z.object({ device_id: id }).strict(),
  "connect.sync_cancel": empty,
  "connect.sync_conflicts": empty,
  "connect.sync_resolve": z
    .object({ conflict_id: id, choice: z.enum(["local", "incoming"]) })
    .strict(),
  "connect.sync_chats": z.object({ device_id: id }).strict(),
  "connect.sync_select": z
    .object({ device_id: id, conversation_id: id, selected: z.boolean() })
    .strict(),
  "connect.snapshot": empty,
  "connect.enable": z.object({ address, discovery: z.boolean() }).strict(),
  "connect.disable": empty,
  "connect.rename": z
    .object({
      name: z
        .string()
        .trim()
        .min(1)
        .max(100)
        .refine((value) =>
          Array.from(value).every((c) => c.charCodeAt(0) >= 32),
        ),
    })
    .strict(),
  "connect.permission": z
    .object({
      device_id: id,
      capability: z.enum([
        "models.remote",
        "files.send",
        "files.receive",
        "connect.ping",
        "device.status",
        "chat.metadata.read",
        "sync.tasks",
        "sync.calendar",
        "sync.reminders",
        "sync.chat",
      ]),
      decision: z.enum(["allow", "ask", "deny"]),
    })
    .strict(),
  "connect.revoke": z.object({ device_id: id }).strict(),
  "connect.open": z
    .object({
      device_id: id,
      address,
      port: z.number().int().min(1).max(65535),
    })
    .strict(),
  "connect.disconnect": z.object({ device_id: id }).strict(),
  "connect.ping": z.object({ device_id: id }).strict(),
  "connect.pair_create": empty,
  "connect.pair_accept": z
    .object({ offer: z.string().min(1).max(12288) })
    .strict(),
  "connect.pair_status": z.object({ session_id: id }).strict(),
  "connect.pair_confirm": z
    .object({ session_id: id, compared_value: z.string().min(1).max(256) })
    .strict(),
  "connect.pair_cancel": z.object({ session_id: id }).strict(),
};
