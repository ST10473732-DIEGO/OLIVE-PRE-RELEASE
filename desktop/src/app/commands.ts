// The command registry behind the V2 command palette. Nothing here is a
// static list: each workspace registers a provider for the commands it can
// actually run right now, and unregisters it when it goes away. A provider is
// asked for its items only when the palette opens or the query changes, so
// availability always reflects current state.
import { useEffect, useRef } from "react";

/** Palette modes, chosen by the first character of the query. */
export type PaletteMode = "" | ">" | ":" | "@" | "#";
export const PALETTE_MODES: { prefix: PaletteMode; label: string; hint: string }[] = [
  { prefix: "", label: "Go to", hint: "Spaces, files and commands" },
  { prefix: ">", label: "Commands", hint: "Commands" },
  { prefix: ":", label: "Line", hint: "Go to line" },
  { prefix: "@", label: "Symbols in file", hint: "Symbols in the open file" },
  { prefix: "#", label: "Workspace symbols", hint: "Symbols in the workspace" },
];

export interface PaletteItem {
  id: string;
  /** Visible label; also the accessible name of the row. */
  title: string;
  group: string;
  /** Secondary text on the right (a path, a location). */
  detail?: string;
  /** Keybinding hint, shown only when the binding really exists. */
  keys?: string;
  /** Extra words to match. */
  aliases?: string[];
  /** When set the command is listed but cannot run; the reason is the tooltip. */
  unavailable?: string;
  run: () => void | Promise<void>;
}

export interface PaletteProvider {
  id: string;
  prefix: PaletteMode;
  /** Lower sorts first. */
  order?: number;
  items: (query: string) => PaletteItem[] | Promise<PaletteItem[]>;
}

const providers = new Map<string, PaletteProvider>();
const listeners = new Set<() => void>();

export function registerPaletteProvider(provider: PaletteProvider): () => void {
  providers.set(provider.id, provider);
  listeners.forEach((listener) => listener());
  return () => {
    if (providers.get(provider.id) === provider) {
      providers.delete(provider.id);
      listeners.forEach((listener) => listener());
    }
  };
}
export function onPaletteProvidersChanged(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function paletteProviders(): PaletteProvider[] {
  return [...providers.values()].sort((a, b) => (a.order ?? 50) - (b.order ?? 50));
}

/** Register a provider for the lifetime of a component. The provider may close
 *  over fresh state on every render: the latest version is always used. */
export function usePaletteProvider(
  id: string,
  prefix: PaletteMode,
  items: (query: string) => PaletteItem[] | Promise<PaletteItem[]>,
  enabled = true,
  order?: number,
) {
  const latest = useRef(items);
  latest.current = items;
  useEffect(() => {
    if (!enabled) return;
    return registerPaletteProvider({ id, prefix, order, items: (query) => latest.current(query) });
  }, [id, prefix, enabled, order]);
}

export function parseQuery(raw: string): { mode: PaletteMode; text: string } {
  const first = raw.charAt(0);
  if (first === ">" || first === ":" || first === "@" || first === "#")
    return { mode: first, text: raw.slice(1).trim() };
  return { mode: "", text: raw.trim() };
}

/** Case-insensitive match of every word in the query against the title and
 *  aliases. Returns a score (lower is better) or -1 for no match. */
export function matchScore(item: Pick<PaletteItem, "title" | "aliases" | "detail">, query: string): number {
  const text = query.trim().toLowerCase();
  if (!text) return 0;
  const title = item.title.toLowerCase();
  const haystack = [title, ...(item.aliases || []), item.detail || ""].join(" ").toLowerCase();
  const words = text.split(/\s+/);
  if (!words.every((word) => haystack.includes(word))) return -1;
  const at = title.indexOf(text);
  if (at === 0) return 0;
  if (at > 0) return 1 + at / 100;
  return 5;
}

/** The substring of `title` to emphasise for `query`, as [start, end). */
export function highlightRange(title: string, query: string): [number, number] | null {
  const text = query.trim().toLowerCase();
  if (!text) return null;
  const at = title.toLowerCase().indexOf(text);
  return at < 0 ? null : [at, at + text.length];
}

/** Collect items for a query from the registered providers. With no prefix,
 *  "Go to" providers and commands are both searched; a prefix restricts the
 *  palette to that mode. Results keep provider order, then match quality. */
export async function collectItems(
  raw: string,
  list: PaletteProvider[] = paletteProviders(),
  limit = 80,
): Promise<{ mode: PaletteMode; items: PaletteItem[] }> {
  const { mode, text } = parseQuery(raw);
  const eligible = list.filter((provider) =>
    mode === "" ? provider.prefix === "" || provider.prefix === ">" : provider.prefix === mode,
  );
  const batches = await Promise.all(
    eligible.map(async (provider) => {
      try {
        return await provider.items(text);
      } catch {
        return [];
      }
    }),
  );
  const items: PaletteItem[] = [];
  batches.forEach((batch) => {
    // Line and symbol providers do their own matching; others are filtered here.
    // Groups stay contiguous in the order the provider declared them.
    const groups = [...new Set(batch.map((item) => item.group))];
    const filtered = mode === ":" || mode === "@" || mode === "#"
      ? batch
      : batch
          .map((item) => ({ item, score: matchScore(item, text), group: groups.indexOf(item.group) }))
          .filter((entry) => entry.score >= 0)
          .sort((a, b) => a.group - b.group || a.score - b.score)
          .map((entry) => entry.item);
    items.push(...filtered);
  });
  return { mode, items: items.slice(0, limit) };
}
