// Pure presentation rules for OLIVE Notes (unit-tested).
import type { NoteSummary, SaveState } from "./session";

export interface PeerStatus {
  device_id: string;
  name: string;
  platform?: string;
  state: "synced" | "syncing" | "offline" | "off" | "error" | "idle" | string;
  pending: number | null;
  last_sync?: string | null;
  refused?: number;
  error?: string;
}
export interface NotesStatus {
  available: boolean;
  message?: string;
  peers: PeerStatus[];
  connect?: boolean;
}

/** Pinned first, then most recently edited. Stable for equal keys. */
export function sortNotes(notes: NoteSummary[]): NoteSummary[] {
  return [...notes].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || b.edited_at.localeCompare(a.edited_at) || a.note_id.localeCompare(b.note_id),
  );
}

/** While a note is being typed in, it keeps its place instead of jumping to the
 *  top on every keystroke; the list re-sorts once typing pauses. */
export function stableOrder(previous: string[], notes: NoteSummary[], holdId: string | null): NoteSummary[] {
  const sorted = sortNotes(notes);
  if (!holdId) return sorted;
  const from = sorted.findIndex((n) => n.note_id === holdId);
  const was = previous.indexOf(holdId);
  if (from < 0 || was < 0) return sorted;
  const held = sorted[from];
  if (held.pinned !== notes.find((n) => n.note_id === holdId)?.pinned) return sorted;
  const rest = sorted.filter((n) => n.note_id !== holdId);
  rest.splice(Math.min(was, rest.length), 0, held);
  return rest;
}

export type Tone = "success" | "live" | "warning" | "error" | "idle";

/** One quiet status line. "Saved" only after the backend committed to disk. */
export function syncLine(status: NotesStatus | null, save: SaveState, saveError = ""): { label: string; tone: Tone } {
  if (status && !status.available) return { label: status.message || "Notes unavailable", tone: "error" };
  if (save === "error") return { label: saveError || "Could not save locally", tone: "error" };
  if (save === "retrying") return { label: "Could not save locally · retrying", tone: "error" };
  if (save === "saving") return { label: "Saving…", tone: "live" };
  const peers = (status?.peers || []).filter((p) => p.state !== "off");
  if (!peers.length) return { label: "Saved locally", tone: "idle" };
  const failing = peers.find((p) => p.state === "error");
  if (failing) return { label: `Sync issue with ${failing.name}`, tone: "warning" };
  const waiting = peers.filter((p) => (p.pending || 0) > 0);
  const offline = waiting.filter((p) => p.state === "offline");
  if (offline.length) return { label: `Offline — changes will sync to ${offline[0].name} later`, tone: "idle" };
  if (waiting.length) return { label: "Syncing…", tone: "live" };
  const online = peers.filter((p) => p.state !== "offline");
  if (!online.length) return { label: `Saved locally · ${peers[0].name} unavailable`, tone: "idle" };
  return { label: `Synced with ${online.map((p) => p.name).join(", ")}`, tone: "success" };
}

export function countLabel(length: number): string {
  return length === 1 ? "1 character" : `${length.toLocaleString()} characters`;
}

const REASONS: Record<string, string> = {
  edit: "Edited",
  rename: "Renamed",
  trash: "Before deleting",
  "before-restore": "Before restoring a version",
  restored: "Restored version",
  created: "Created",
  imported: "Imported",
  duplicated: "Duplicated",
};
export const reasonLabel = (reason: string) => REASONS[reason] || "Checkpoint";
