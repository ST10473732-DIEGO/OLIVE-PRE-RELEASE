import { open, stat } from "node:fs/promises";
import type { Backend } from "./backend";

// Generated Chat media is served same-origin (dmdo://app/__media/<id>) so the
// renderer's CSP stays 'self'. Python resolves and hash-checks the artifact;
// the renderer only ever holds the opaque id, never a filesystem path.
const TYPES = new Set(["image/png", "audio/wav", "video/mp4"]);
const HEADERS = {
  "Accept-Ranges": "bytes",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'none'",
};

export function mediaId(pathname: string): string | null {
  const match = /^\/__media\/([0-9a-f]{32})$/.exec(pathname);
  return match ? match[1] : null;
}

export function byteRange(header: string | null, size: number): [number, number] | null | "invalid" {
  if (!header) return null;
  const match = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!match || (!match[1] && !match[2])) return "invalid";
  let start: number, end: number;
  if (!match[1]) {
    const suffix = Number(match[2]);
    start = Math.max(0, size - suffix);
    end = size - 1;
  } else {
    start = Number(match[1]);
    end = match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
  }
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || start >= size) return "invalid";
  return [start, end];
}

export async function mediaResponse(request: Request, id: string, backend: Backend): Promise<Response> {
  let file: { path: string; mime_type: string };
  try {
    file = (await backend.request("media.artifact_file", { artifact_id: id })) as typeof file;
  } catch {
    return new Response("", { status: 404, headers: HEADERS });
  }
  if (!TYPES.has(file.mime_type)) return new Response("", { status: 404, headers: HEADERS });
  try {
    return await serve(request, file);
  } catch {
    return new Response("", { status: 404, headers: HEADERS }); // Removed after lookup.
  }
}

async function serve(request: Request, file: { path: string; mime_type: string }): Promise<Response> {
  const size = (await stat(file.path)).size;
  const range = byteRange(request.headers.get("range"), size);
  if (range === "invalid")
    return new Response("", { status: 416, headers: { ...HEADERS, "Content-Range": `bytes */${size}` } });
  const [start, end] = range || [0, size - 1];
  const length = end - start + 1;
  const buffer = Buffer.alloc(length);
  const handle = await open(file.path, "r");
  try {
    await handle.read(buffer, 0, length, start);
  } finally {
    await handle.close();
  }
  return new Response(buffer, {
    status: range ? 206 : 200,
    headers: {
      ...HEADERS,
      "Content-Type": file.mime_type,
      "Content-Length": String(length),
      ...(range ? { "Content-Range": `bytes ${start}-${end}/${size}` } : {}),
    },
  });
}
