import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  collectItems,
  highlightRange,
  matchScore,
  parseQuery,
  registerPaletteProvider,
  paletteProviders,
  type PaletteProvider,
} from "../src/app/commands";
import { Navigation, navModeFor } from "../src/app/Navigation";
import { PaletteRow } from "../src/app/CommandPalette";
import { TitleBar } from "../src/app/TitleBar";
import { connectSummary, modelStatus, runtimeState } from "../src/services/runtimeState";
import { corePaletteMode } from "../src/components/olive-core/geometry";
import type { Snapshot } from "../src/services/api";

const run = () => undefined;

describe("command registry", () => {
  it("parses palette modes from the first character", () => {
    expect(parseQuery("")).toEqual({ mode: "", text: "" });
    expect(parseQuery(">build")).toEqual({ mode: ">", text: "build" });
    expect(parseQuery(":42")).toEqual({ mode: ":", text: "42" });
    expect(parseQuery("@ Zone")).toEqual({ mode: "@", text: "Zone" });
    expect(parseQuery("#Scheduler")).toEqual({ mode: "#", text: "Scheduler" });
    expect(parseQuery("open studio")).toEqual({ mode: "", text: "open studio" });
  });
  it("matches every word against title and aliases and ranks prefixes first", () => {
    expect(matchScore({ title: "Open Studio" }, "open")).toBe(0);
    expect(matchScore({ title: "Open Studio" }, "studio")).toBeGreaterThan(0);
    expect(matchScore({ title: "Open Studio", aliases: ["ide"] }, "ide")).toBe(5);
    expect(matchScore({ title: "Open Studio" }, "mail")).toBe(-1);
    expect(highlightRange("Run: Run Project", "project")).toEqual([9, 16]);
    expect(highlightRange("Run", "x")).toBeNull();
  });
  it("collects only registered providers, filters, and restricts by prefix", async () => {
    const spaces: PaletteProvider = { id: "t.spaces", prefix: "", items: () => [
      { id: "a", title: "Open Chat", group: "Go to", run },
      { id: "b", title: "Open Studio", group: "Go to", run },
    ] };
    const commands: PaletteProvider = { id: "t.cmd", prefix: ">", items: () => [
      { id: "c", title: "Run: Run Project", group: "Run", keys: "Ctrl+F5", run },
    ] };
    const lines: PaletteProvider = { id: "t.line", prefix: ":", items: (q) => (q ? [{ id: "l", title: `Go to line ${q}`, group: "Line", run }] : []) };
    const list = [spaces, commands, lines];
    expect((await collectItems("", list)).items.map((i) => i.id)).toEqual(["a", "b", "c"]);
    expect((await collectItems("studio", list)).items.map((i) => i.id)).toEqual(["b"]);
    expect((await collectItems(">", list)).items.map((i) => i.id)).toEqual(["c"]);
    expect((await collectItems(">studio", list)).items).toEqual([]);
    expect((await collectItems(":12", list)).items.map((i) => i.title)).toEqual(["Go to line 12"]);
  });
  it("unregisters providers so unavailable commands disappear", async () => {
    const unregister = registerPaletteProvider({ id: "t.studio", prefix: ">", items: () => [{ id: "x", title: "Build: Build Solution", group: "Build", run }] });
    expect(paletteProviders().some((p) => p.id === "t.studio")).toBe(true);
    expect((await collectItems(">build")).items.map((i) => i.id)).toContain("x");
    unregister();
    expect((await collectItems(">build")).items.map((i) => i.id)).not.toContain("x");
  });
  it("keeps a provider's groups contiguous while filtering", async () => {
    const mixed: PaletteProvider = { id: "t.mixed", prefix: "", items: () => [
      { id: "1", title: "New task", group: "Start", run },
      { id: "2", title: "Open Tasks", group: "Go to", run },
      { id: "3", title: "Tasks export", group: "Start", run },
    ] };
    const result = await collectItems("task", [mixed]);
    expect(result.items.map((i) => i.group)).toEqual(["Start", "Start", "Go to"]);
  });
});

describe("command palette rows", () => {
  it("names each row by its command only; detail, keys and reasons are descriptions", () => {
    const html = renderToStaticMarkup(createElement(PaletteRow, {
      item: { id: "s", title: "Open Settings", detail: "Appearance, models and data.", keys: "Ctrl+,", group: "Go to", run },
      index: 0, active: true, query: "set", onHover: run, onRun: run,
    }));
    expect(html).toContain('aria-label="Open Settings"');
    expect(html).toContain('aria-description="Appearance, models and data. · Ctrl+,"');
    expect(html).toContain('aria-current="true"');
    expect(html).toContain("<mark>Set</mark>");
    const disabled = renderToStaticMarkup(createElement(PaletteRow, {
      item: { id: "r", title: "Run: Run Project", unavailable: "A program is already running", group: "Run", run },
      index: 1, active: false, query: "", onHover: run, onRun: run,
    }));
    expect(disabled).toContain('aria-disabled="true"');
    expect(disabled).toContain("A program is already running");
  });
});

describe("shell navigation", () => {
  it("chooses expanded, rail or hidden navigation from width and space (V2 §15)", () => {
    expect(navModeFor(1920, "home", false)).toBe("expanded");
    expect(navModeFor(1440, "home", true)).toBe("rail");
    expect(navModeFor(1200, "home", false)).toBe("rail");
    expect(navModeFor(1000, "home", false)).toBe("hidden");
    expect(navModeFor(1920, "studio", false)).toBe("rail");
    expect(navModeFor(1440, "studio", false)).toBe("hidden");
    expect(navModeFor(1366, "studio", false)).toBe("hidden");
  });
  it("marks the active space, names every row and shows attention badges", () => {
    const html = renderToStaticMarkup(createElement(Navigation, {
      route: "tasks", navigate: run, badges: { reminders: 2 }, compact: false, setCompact: run,
      canExpand: true, developer: false, overlay: false, closeOverlay: run,
    }));
    expect(html).toContain('aria-label="Main navigation"');
    expect(html).toMatch(/aria-current="page"[^>]*aria-label="Tasks"|aria-label="Tasks"[^>]*aria-current="page"/);
    expect(html).toContain('aria-description="2 need attention"');
    expect(html).toContain("Collapse navigation");
    // Desktop tasks use Chat; unrelated workspaces stay reachable.
    expect(html).not.toContain('aria-label="Desktop Control"');
    for (const label of ["Chat", "OLIVE GO", "Agent", "Studio", "Projects", "Knowledge", "Memory", "Mail", "Calendar", "Tasks", "Reminders", "Devices", "Connections", "Settings"])
      expect(html).toContain(`aria-label="${label}"`);
    // Find anything lives in the title bar only, so there is exactly one.
    expect(html).not.toContain("Find anything");
  });
});

describe("title bar", () => {
  const snapshot = {
    home: { status: { ollama: "Ollama ready · 3 models" }, recent: [], context: {} },
    chat: { id: "c", preset: "normal" },
    presets: [{ id: "normal", name: "OLIVE NORMAL", status: "Ready" }, { id: "max", name: "OLIVE MAX", status: "Needs setup" }],
  } as unknown as Snapshot;
  const bar = (overrides: Record<string, unknown> = {}) =>
    renderToStaticMarkup(createElement(TitleBar, {
      route: "home", navigate: run, navHidden: false, openNavigation: run, openPalette: run,
      activity: "Ready", runtime: runtimeState("Ready", snapshot, 0, false), openActivity: run,
      model: modelStatus(snapshot), connect: connectSummary({ network: { state: "off" } }), attention: 0,
      developer: false, compactStatus: false, setContextSlot: run, setActionsSlot: run, ...overrides,
    }));
  it("keeps the stable accessible names the suites rely on", () => {
    const html = bar();
    expect(html).toContain('aria-label="Find anything"');
    expect(html).toContain('aria-label="OLIVE activity"');
    expect(html).toContain('aria-label="Model: NORMAL ready"');
    expect(html).toContain('aria-label="Connect: Connect off"');
    expect(html).toContain("Notifications: nothing needs you");
    // With navigation visible there is no competing space selector.
    expect(html).not.toContain("Switch space");
    expect(html).not.toContain("Open navigation");
  });
  it("offers the space switcher and navigation only when the pane is hidden", () => {
    const html = bar({ navHidden: true, route: "studio", compactStatus: true });
    expect(html).toContain("Space: Studio. Switch space");
    expect(html).toContain('aria-label="Open navigation"');
    expect(html).not.toContain("Model:");
  });
  it("speaks the attention total instead of a colour-only badge", () => {
    expect(bar({ attention: 3 })).toContain("Notifications: 3 need your attention");
  });
});

describe("truthful status summaries", () => {
  const base = { home: { status: { ollama: "Ollama unavailable: connection refused" }, recent: [], context: {} }, chat: { id: "c", preset: "normal" }, presets: [{ id: "normal", name: "OLIVE NORMAL", status: "Ready" }] } as unknown as Snapshot;
  it("never reports a model as ready while Ollama is unreachable", () => {
    expect(modelStatus(base)).toMatchObject({ label: "AI offline", tone: "warning" });
    expect(modelStatus(null).label).toBe("Starting");
  });
  it("reports a preset that is not installed as needing setup", () => {
    const value = { ...base, home: { ...base.home, status: { ollama: "Ollama ready" } }, presets: [{ id: "normal", name: "OLIVE NORMAL", status: "Needs setup" }] } as unknown as Snapshot;
    expect(modelStatus(value)).toMatchObject({ label: "NORMAL needs setup", tone: "warning" });
  });
  it("attributes a remote conversation to its device, not to this PC", () => {
    const value = { ...base, chat: { id: "c", preset: "max", run_on: "peer" }, presets: [{ id: "max", name: "OLIVE MAX", status: "Ready" }] } as unknown as Snapshot;
    expect(modelStatus(value, "Gaming PC").label).toBe("MAX · Gaming PC");
  });
  it("separates Connect on, paired and online", () => {
    expect(connectSummary(null).label).toBe("Connect");
    expect(connectSummary({ network: { state: "off" } }).label).toBe("Connect off");
    expect(connectSummary({ network: { state: "on" }, devices: [] }).label).toBe("No devices");
    const devices = [
      { trust_state: "paired", live: { state: "online" } },
      { trust_state: "paired", live: { state: "offline" } },
      { trust_state: "revoked", live: { state: "online" } },
    ];
    expect(connectSummary({ network: { state: "on" }, devices })).toMatchObject({ label: "1 device online", tone: "ok" });
  });
  it("lights the compact Core cyan only for real work and amber for approvals", () => {
    expect(corePaletteMode("Ready")).toBe("rest");
    expect(corePaletteMode("Idle")).toBe("rest");
    expect(corePaletteMode("Thinking")).toBe("compute");
    expect(corePaletteMode("Working")).toBe("compute");
    expect(corePaletteMode("Approval required")).toBe("attention");
  });
});

describe("motion primitives", () => {
  it("never transitions a button that becomes unavailable or is not rendered", () => {
    // Chromium never settles a transition started inside a closed <details>;
    // the Mail composer disables its overflow actions there during review.
    const css = readFileSync(new URL("../src/design/tokens.css", import.meta.url), "utf8");
    expect(css).toMatch(/button:disabled,\s*details:not\(\[open\]\) button \{\s*transition: none;/);
  });
});
