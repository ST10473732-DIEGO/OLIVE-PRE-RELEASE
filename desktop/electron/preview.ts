import { z } from "zod";
const rect = z
  .object({
    x: z.number().int().min(0).max(20000),
    y: z.number().int().min(0).max(20000),
    width: z.number().int().min(1).max(20000),
    height: z.number().int().min(1).max(20000),
  })
  .strict();
export const previewSchema = z.discriminatedUnion("action", [
  z
    .object({
      action: z.literal("open"),
      session_id: z.string().min(1).max(80),
      bounds: rect,
    })
    .strict(),
  z.object({ action: z.literal("bounds"), bounds: rect }).strict(),
  z.object({ action: z.literal("close") }).strict(),
]);
export type PreviewAction = z.infer<typeof previewSchema>;
