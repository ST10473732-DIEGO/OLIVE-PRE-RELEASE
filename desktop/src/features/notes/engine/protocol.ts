// olive-notes/1 validation for the TypeScript replica (the phone engine).
// Mirrors olive/notes/protocol.py; limits come from the shared protocol_v1.json.
// Strict JSON (duplicate keys, number forms) is checked by the host's decoder
// before strings reach this module.
import spec from "./protocol_v1.json";
import { fromBase64 } from "./doc";

export const PROTOCOL = spec.protocol;
export const LIMITS = spec.limits;
const OPERATIONS = spec.operations as Record<string, { required: string[]; optional: string[] }>;
const STATUSES = new Set(spec.statuses);
export const ERRORS = new Set(spec.errors);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;

export class ProtocolError extends Error {}

type Json = Record<string, unknown>;

function fields(value: unknown, required: string[], optional: string[] = []): asserts value is Json {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ProtocolError("malformed_message");
  const keys = Object.keys(value);
  if (!required.every((k) => keys.includes(k)) || keys.some((k) => !required.includes(k) && !optional.includes(k)))
    throw new ProtocolError("malformed_message");
}

export function uuid(value: unknown): string {
  if (typeof value !== "string" || !UUID.test(value)) throw new ProtocolError("malformed_message");
  return value;
}

function integer(value: unknown, low = 0, high = 2 ** 53): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < low || value > high) throw new ProtocolError("malformed_message");
  return value;
}

export function bytes(value: unknown, limit: number, allowEmpty = false): Uint8Array {
  if (typeof value !== "string") throw new ProtocolError("malformed_message");
  if (value.length > Math.floor((limit * 4) / 3) + 4) throw new ProtocolError("payload_too_large");
  let decoded: Uint8Array;
  try { decoded = fromBase64(value); } catch { throw new ProtocolError("malformed_message"); }
  if (decoded.length > limit) throw new ProtocolError("payload_too_large");
  if (!decoded.length && !allowEmpty) throw new ProtocolError("malformed_message");
  return decoded;
}

/** Yjs state vector: varuint count, then (client, clock) varuint pairs. */
export function decodeStateVector(data: Uint8Array): Map<number, number> {
  if (data.length > LIMITS.max_state_vector_bytes) throw new ProtocolError("malformed_message");
  let offset = 0;
  const read = () => {
    let value = 0, factor = 1;
    for (let i = 0; i < 8; i++) {
      if (offset >= data.length) throw new ProtocolError("malformed_message");
      const byte = data[offset++];
      value += (byte & 0x7f) * factor;
      if (byte < 0x80) return value;
      factor *= 128;
    }
    throw new ProtocolError("malformed_message");
  };
  const result = new Map<number, number>();
  if (!data.length) return result;
  const count = read();
  if (count > 512) throw new ProtocolError("malformed_message");
  for (let i = 0; i < count; i++) {
    const client = read(), clock = read();
    if (result.has(client)) throw new ProtocolError("malformed_message");
    result.set(client, clock);
  }
  if (offset !== data.length) throw new ProtocolError("malformed_message");
  return result;
}

export function covers(remote: Map<number, number>, local: Map<number, number>): boolean {
  for (const [client, clock] of local) if ((remote.get(client) || 0) < clock) return false;
  return true;
}

export function stateVector(value: unknown): Uint8Array {
  const data = bytes(value, LIMITS.max_state_vector_bytes);
  decodeStateVector(data);
  return data;
}

export interface Entry { note_id: string; seq: number; sv: Uint8Array; purged: boolean; update?: Uint8Array }
export interface Request {
  request_id: string;
  source_device_id: string;
  target_device_id: string;
  operation: "hello" | "sync" | "chunk";
  arguments: Json;
  timestamp: number;
  expires_at: number;
}

export function validateArguments(operation: string, args: unknown): Json {
  const op = OPERATIONS[operation];
  if (!op) throw new ProtocolError("malformed_message");
  fields(args, op.required, op.optional);
  if (operation === "hello") {
    const versions = args.versions;
    if (!Array.isArray(versions) || versions.length < 1 || versions.length > 4 || versions.some((v) => typeof v !== "string" || v.length > 32))
      throw new ProtocolError("malformed_message");
    return { versions };
  }
  uuid(args.epoch);
  if (operation === "sync") {
    const entries = args.entries;
    if (!Array.isArray(entries)) throw new ProtocolError("malformed_message");
    if (entries.length > LIMITS.max_entries) throw new ProtocolError("payload_too_large");
    const seen = new Set<string>();
    let total = 0;
    const decoded: Entry[] = entries.map((entry) => {
      fields(entry, spec.entry.required, spec.entry.optional);
      const id = uuid(entry.note_id);
      if (seen.has(id) || typeof entry.purged !== "boolean") throw new ProtocolError("malformed_message");
      seen.add(id);
      const item: Entry = { note_id: id, seq: integer(entry.seq), sv: stateVector(entry.sv), purged: entry.purged };
      if ("update" in entry) {
        if (entry.purged) throw new ProtocolError("malformed_message");
        item.update = bytes(entry.update, LIMITS.max_inline_update_bytes);
        total += item.update.length;
      }
      return item;
    });
    if (total > LIMITS.max_request_update_bytes) throw new ProtocolError("payload_too_large");
    return { epoch: args.epoch, entries: decoded };
  }
  const countLimit = Math.ceil(LIMITS.max_transfer_bytes / LIMITS.max_chunk_bytes);
  const result = {
    epoch: args.epoch, transfer_id: uuid(args.transfer_id), note_id: uuid(args.note_id), seq: integer(args.seq),
    sv: stateVector(args.sv), index: integer(args.index, 0, countLimit - 1), count: integer(args.count, 1, countLimit),
    total_bytes: integer(args.total_bytes, 1, LIMITS.max_transfer_bytes), data: bytes(args.data, LIMITS.max_chunk_bytes),
    sha256: args.sha256,
  };
  if (typeof args.sha256 !== "string" || !SHA256.test(args.sha256) || result.index >= result.count) throw new ProtocolError("malformed_message");
  return result;
}

export function decodeRequest(value: unknown): Request {
  fields(value, ["protocol_version", "request_id", "source_device_id", "target_device_id", "operation", "arguments", "timestamp", "expires_at"]);
  if (value.protocol_version !== PROTOCOL) throw new ProtocolError("unsupported_protocol");
  const request = {
    request_id: uuid(value.request_id), source_device_id: uuid(value.source_device_id), target_device_id: uuid(value.target_device_id),
    operation: value.operation as Request["operation"], timestamp: integer(value.timestamp, 0, 253402300799),
    expires_at: integer(value.expires_at, 0, 253402300799), arguments: {} as Json,
  };
  if (typeof value.operation !== "string" || !OPERATIONS[value.operation]) throw new ProtocolError("malformed_message");
  const lifetime = request.expires_at - request.timestamp;
  if (lifetime <= 0 || lifetime > LIMITS.max_request_lifetime_seconds) throw new ProtocolError("malformed_message");
  request.arguments = validateArguments(value.operation, value.arguments);
  return request;
}

export interface SyncRow { note_id: string; status: string; sv: Uint8Array | null; error?: string }

export function validateResult(operation: string, result: unknown, entries?: { note_id: string }[]) {
  if (operation === "hello") {
    fields(result, ["versions", "epoch"]);
    if (!Array.isArray(result.versions) || result.versions.length < 1 || result.versions.length > 4) throw new ProtocolError("malformed_message");
    uuid(result.epoch);
    return { versions: result.versions as string[], epoch: result.epoch as string };
  }
  if (operation === "sync") {
    fields(result, ["epoch", "results"]);
    uuid(result.epoch);
    const rows = result.results;
    if (!Array.isArray(rows) || !entries || rows.length !== entries.length) throw new ProtocolError("malformed_message");
    return {
      epoch: result.epoch as string,
      results: rows.map((row, index): SyncRow => {
        fields(row, ["note_id", "status", "sv"], ["error"]);
        if (row.note_id !== entries[index].note_id || typeof row.status !== "string" || !STATUSES.has(row.status) || row.status === "partial")
          throw new ProtocolError("malformed_message");
        if ("error" in row && (typeof row.error !== "string" || !ERRORS.has(row.error))) throw new ProtocolError("malformed_message");
        const sv = ["applied", "current", "needs"].includes(row.status) ? stateVector(row.sv) : null;
        return { note_id: row.note_id, status: row.status, sv, error: row.error as string | undefined };
      }),
    };
  }
  fields(result, ["epoch", "status", "sv"], ["error"]);
  uuid(result.epoch);
  if (typeof result.status !== "string" || !STATUSES.has(result.status)) throw new ProtocolError("malformed_message");
  const sv = ["applied", "current", "needs"].includes(result.status) ? stateVector(result.sv) : null;
  return { epoch: result.epoch as string, status: result.status, sv, error: result.error as string | undefined };
}
