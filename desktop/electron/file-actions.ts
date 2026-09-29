import { z } from "zod";
const id = z.string().min(1).max(4096);
export const fileActionSchema = z.discriminatedUnion("action", [
  z.object({action:z.literal('connect-file-select'),device_id:z.string().uuid()}).strict(),
  z.object({action:z.literal('connect-file-save'),transfer_id:z.string().uuid()}).strict(),
  z.object({action:z.literal('media-import')}).strict(),
  z.object({action:z.literal('media-export'),artifact_id:id}).strict(),
  z.object({action:z.literal('media-open'),artifact_id:z.string().regex(/^[0-9a-f]{32}$/)}).strict(),
  z.object({action:z.literal("mail-google-client")}).strict(),
  z.object({action:z.literal("mail-import")}).strict(),
  z.object({action:z.literal("mail-export"),record_id:id}).strict(),
  z.object({action:z.literal("mail-attach"),record_id:id,revision:z.number().int().min(1)}).strict(),
  z.object({action:z.literal("mail-save-attachment"),record_id:id,attachment_id:id}).strict(),
  z.object({action:z.literal("personal-import"),kind:z.enum(["contact","event"]),format:z.enum(["csv","vcf","ics"]),calendar_id:id.optional()}).strict(),
  z.object({action:z.literal("personal-export"),kind:z.enum(["contact","event"]),format:z.enum(["csv","vcf","ics"])}).strict(),
  z.object({action:z.literal("profile-avatar")}).strict(),
  z.object({action:z.literal("notes-export"),note_id:z.string().uuid(),format:z.enum(["txt","md"]),name:z.string().max(120).optional()}).strict(),
  z.object({action:z.literal("notes-import")}).strict(),
  z.object({action:z.literal("desktop-launch"),kind:z.enum(["executable","python"])}).strict(),
  z
    .object({
      action: z.literal("attach"),
      chat_id: id,
      permanent: z.boolean().optional(),
    })
    .strict(),
  z
    .object({ action: z.literal("relink"), chat_id: id, document_id: id })
    .strict(),
  z.object({ action: z.literal("backup") }).strict(),
  z.object({ action: z.literal("restore") }).strict(),
  z.object({ action: z.literal("export-memory") }).strict(),
  z.object({ action: z.literal("export-download"), download_id: id }).strict(),
  z
    .object({ action: z.literal("desktop-export-download"), download_id: id })
    .strict(),
  z.object({ action: z.literal("browser-upload"), target_id: id }).strict(),
  z.object({ action: z.literal("export-chat"), chat_id: id }).strict(),
  z
    .object({
      action: z.literal("workspace"),
      title: id,
      project_id: id.optional(),
      trust_level: z.enum(["approved", "trusted", "untrusted"]).optional(),
    })
    .strict(),
  z.object({ action: z.literal("ocr") }).strict(),
  z.object({ action: z.literal("diagnostics"), chat_id: id }).strict(),
]);
export type FileAction = z.infer<typeof fileActionSchema>;
