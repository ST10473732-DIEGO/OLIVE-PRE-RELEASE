import { connectSchemas } from "./connect-contracts";
import { z } from "zod";
import { m2Schemas } from "./m2-contracts";
import { m3Schemas } from "./m3-contracts";
import { m4Schemas } from "./m4-contracts";
import { studioSchemas } from "./studio-contracts";
const short = z
  .string()
  .max(4096)
  .refine((v) => !v.includes("\0"));
const text = z
  .string()
  .max(32000)
  .refine((v) => !v.includes("\0"));
const buffer = z
  .string()
  .max(400000)
  .refine((v) => !v.includes("\0"));
const chat = { chat_id: short };
const workspace = { workspace_id: short };
const file = { ...workspace, path: short };
const empty = z.object({}).strict();
export const schemas = {
  ...connectSchemas,
  ...m2Schemas,
  ...m3Schemas,
  ...m4Schemas,
  ...studioSchemas,
  "runtime.snapshot": empty,
  'media.status': empty,
  'media.configure': z.object({url:short}).strict(),
  'media.disconnect': empty,
  'media.start': z.object({request:z.object({operation:z.enum(['resize','crop','generate','image-to-image']),source_id:short.optional(),width:z.number().int(),height:z.number().int(),left:z.number().int().optional(),top:z.number().int().optional(),prompt:text.optional(),checkpoint:short.optional(),seed:z.number().int().optional(),steps:z.number().int().optional(),cfg:z.number().optional()}).strict()}).strict(),
  'media.cancel': z.object({job_id:short}).strict(),
  'media.preview': z.object({artifact_id:short}).strict(),
  "connections.discord_status": empty,
  'connections.discord_destinations': z.object({guild_id:z.string().regex(/^[0-9]{1,22}$/).optional()}).strict(),
  'connections.discord_select': z.object({guild_id:z.string().regex(/^[0-9]{1,22}$/),channel_id:z.string().regex(/^[0-9]{1,22}$/)}).strict(),
  "connections.discord_configure": z
    .object({
      token: short.min(20).max(2500),
      guild_id: short.regex(/^[0-9]{1,22}$/),
      channel_id: short.regex(/^[0-9]{1,22}$/),
    })
    .strict(),
  "connections.discord_disconnect": z
    .object({ remove_credentials: z.boolean() })
    .strict(),
  "desktop.stop": empty,
  "chat.new": empty,
  "chat.get": z.object(chat).strict(),
  "chat.select": z.object(chat).strict(),
  "chat.draft": z.object({ ...chat, text }).strict(),
  "chat.rename": z.object({ ...chat, title: short }).strict(),
  "chat.model": z.object({ ...chat, model: short }).strict(),
  "chat.preset": z.object({ ...chat, preset: z.enum(["fast", "normal", "max", "deep", "reimagine"]) }).strict(),
  "chat.regenerate": z.object(chat).strict(),
  "chat.branch": z
    .object({
      ...chat,
      user_index: z.number().int().min(0),
      direction: z.union([z.literal(-1), z.literal(1)]),
    })
    .strict(),
  "interaction.submit": z.object({ ...chat, text, research_mode: z.enum(["Quick", "Deep"]).optional() }).strict(),
  "interaction.cancel": z.object(chat).strict(),
  "context.clear": z.object(chat).strict(),
  "studio.tree": z.object(workspace).strict(),
  "studio.install_package": z
    .object({
      ...workspace,
      manager: z.enum(["python", "node"]),
      package: short.min(1).max(200),
    })
    .strict(),
  "studio.cancel_install": z.object(workspace).strict(),
  "studio.create_project": z
    .object({
      name: short.min(1).max(80),
      language: z.enum(["python", "java", "javascript", "csharp", "empty"]),
    })
    .strict(),
  "studio.open": z.object(file).strict(),
  "studio.create": z.object(file).strict(),
  "studio.compare": z.object(file).strict(),
  "studio.rebase": z
    .object({ ...file, expected_hash: short, disk_hash: short })
    .strict(),
  "studio.save": z
    .object({ ...file, text: buffer, expected_hash: short })
    .strict(),
  "studio.buffer": z
    .object({ ...file, text: buffer, expected_hash: short })
    .strict(),
  "studio.run": z.object(workspace).strict(),
  "studio.restart": z
    .object({ ...workspace, session_id: short.optional() })
    .strict(),
  "studio.validate": z
    .object({ ...workspace, review: z.boolean().optional() })
    .strict(),
  "studio.cancel_validation": z.object({ validation_id: short }).strict(),
  "studio.stop": z.object({ session_id: short }).strict(),
  "studio.input": z.object({ workspace_id: short, session_id: short, text: z.string().max(4000), eof: z.boolean() }).strict(),
  "studio.diff": z.object(workspace).strict(),
  "studio.ask": z
    .object({
      ...workspace,
      request: text,
      path: short.optional(),
      selection: text.optional(),
    })
    .strict(),
  "approval.respond": z
    .object({ approval_id: short, fingerprint: short, approved: z.boolean() })
    .strict(),
};
export type Method = keyof typeof schemas;
export type Arguments<M extends Method> = z.infer<(typeof schemas)[M]>;
export const envelope = z
  .object({
    id: z.string().uuid(),
    method: z.enum(Object.keys(schemas) as [Method, ...Method[]]),
    args: z.unknown(),
  })
  .strict();
export function validateCall(input: unknown) {
  const request = envelope.parse(input);
  return { ...request, args: schemas[request.method].parse(request.args) };
}
