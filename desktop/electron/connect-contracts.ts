import { z } from "zod";
const id = z.string().uuid();
const empty = z.object({}).strict();
const address = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[0-9a-fA-F:.]+$/);
export const connectSchemas = {
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
        "connect.ping",
        "device.status",
        "chat.metadata.read",
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
  "connect.pair_status": z.object({ session_id: id }).strict(),
  "connect.pair_confirm": z
    .object({ session_id: id, compared_value: z.string().min(1).max(256) })
    .strict(),
  "connect.pair_cancel": z.object({ session_id: id }).strict(),
};
