import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  activityAvailability,
  assistantDocks,
  available,
  clampPanelHeight,
  cursorLabel,
  elapsed,
  fileDiff,
  gitDecorations,
  gitGroups,
  groupProblems,
  jobTitle,
  languageServerLabel,
  normaliseSymbols,
  panelTabs,
  problemsByFile,
  REMOTE_CAPABILITIES,
  runtimeLabel,
  studioLayout,
  symbolPath,
} from "../src/features/studio/studioModel";
import { ActivityBar } from "../src/features/studio/ActivityBar";
import { StudioPanel } from "../src/features/studio/StudioPanel";
import { StatusBar } from "../src/features/studio/StatusBar";
import { Explorer } from "../src/components/Explorer";
import { threadAfter, withStudioContext } from "../src/services/conversation";
import type { Chat } from "../src/services/api";

const noop = () => undefined;

describe("local and Remote Studio are separate capability domains (C8)", () => {
  it("allows remotely exactly the C8 operations and nothing else", () => {
    expect([...REMOTE_CAPABILITIES].sort()).toEqual(["build", "cancel", "read", "run", "save", "test", "tree"]);
    for (const local of ["terminal", "interactiveInput", "debug", "codeIntelligence", "search", "sourceControl", "packages", "newProject", "reviewedCommand"] as const) {
      expect(available(local, false)).toBe(true);
      expect(available(local, true)).toBe(false);
    }
  });
  it("disables Search, Source Control, Run and Debug and Testing views remotely", () => {
    expect(activityAvailability(false)).toEqual({ explorer: true, search: true, scm: true, debug: true, testing: true });
    expect(activityAvailability(true)).toEqual({ explorer: true, search: false, scm: false, debug: false, testing: false });
  });
  it("offers no terminal or debug console panel remotely", () => {
    expect(panelTabs(true)).toEqual(["output"]);
    expect(panelTabs(false)).toEqual(["problems", "output", "terminal", "console"]);
    expect(panelTabs(false, { web: true, references: true })).toContain("references");
  });
  it("renders disabled remote views with the reason, never as working", () => {
    const html = renderToStaticMarkup(createElement(ActivityBar, {
      view: "explorer", sidebarOpen: true, select: noop, availability: activityAvailability(true), badges: {}, openSettings: noop,
    }));
    expect(html).toContain('role="toolbar"');
    expect(html).toContain('aria-orientation="vertical"');
    expect(html.match(/aria-disabled="true"/g)?.length).toBe(4);
    expect(html).toContain("Source Control · Not available for remote workspaces");
    expect(html).toContain("Run and Debug · Not available for remote workspaces");
    // Explorer is the single roving tab stop and is marked current.
    expect(html.match(/tabindex="0"/g)?.length).toBe(1);
    expect(html).toMatch(/aria-label="Explorer"[^>]*aria-pressed="true"/);
  });
});

describe("Studio responsive collapse order", () => {
  it("sizes regions per window and keeps the editor at least 560 px", () => {
    expect(studioLayout(1920)).toMatchObject({ sidebarDefault: 280, panelDefault: 280, assistantDefault: 380, iconOnlyRun: false, minimap: true });
    expect(studioLayout(1440)).toMatchObject({ sidebarDefault: 256, iconOnlyRun: false, minimap: false, sidebarOverlay: false });
    expect(studioLayout(1366)).toMatchObject({ sidebarDefault: 240, iconOnlyRun: true, sidebarOverlay: false });
    expect(studioLayout(1100).sidebarOverlay).toBe(true);
    expect(assistantDocks(1920, 280, 380)).toBe(true);
    expect(assistantDocks(1440, 256, 340)).toBe(true);
    // 1366 with sidebar and OLIVE open leaves < 560 for code: OLIVE overlays instead.
    expect(assistantDocks(1366, 480, 340)).toBe(false);
  });
  it("caps the panel at 40% of the editor column", () => {
    expect(clampPanelHeight(600, 800)).toBe(320);
    expect(clampPanelHeight(20, 800)).toBe(100);
    expect(clampPanelHeight(236, 800)).toBe(236);
  });
});

describe("Studio presentation from real records", () => {
  it("groups Git porcelain into staged and working changes without inventing states", () => {
    const entries = [
      { path: "src/a.py", index: "M", worktree: " " },
      { path: "src/b.py", index: " ", worktree: "M" },
      { path: "new.py", index: "?", worktree: "?" },
      { path: "gone.py", index: "D", worktree: " " },
    ];
    const groups = gitGroups(entries);
    expect(groups.staged.map((c) => `${c.letter}:${c.path}`)).toEqual(["M:src/a.py", "D:gone.py"]);
    expect(groups.changes.map((c) => `${c.letter}:${c.path}`)).toEqual(["M:src/b.py", "U:new.py"]);
    const decorations = gitDecorations(entries);
    expect(decorations.get("src/b.py")).toBe("M");
    expect(decorations.get("src")).toBe("•");
    expect(decorations.get("new.py")).toBe("U");
    expect(gitGroups([])).toEqual({ staged: [], changes: [] });
  });
  it("cuts one file's hunk out of the repository diff", () => {
    const diff = "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+y\ndiff --git a/b.py b/b.py\n@@ -2 +2 @@\n-p\n+q\n";
    expect(fileDiff(diff, "b.py")).toBe("diff --git a/b.py b/b.py\n@@ -2 +2 @@\n-p\n+q\n");
    expect(fileDiff(diff, "c.py")).toBe("");
  });
  it("groups diagnostics by file with real counts for Problems and the Explorer", () => {
    const problems = [
      { file: "a.py", line: 5, column: 3, severity: "warning" as const, message: "unused", source: "pyflakes(F401)" },
      { file: "a.py", line: 9, column: 1, severity: "error" as const, message: "bad", source: "pylsp" },
      { file: "b.cs", line: 1, column: 1, severity: "error" as const, message: "CS0103", source: "build output" },
    ];
    const groups = groupProblems(problems);
    expect(groups.map((g) => [g.file, g.errors, g.warnings])).toEqual([["a.py", 1, 1], ["b.cs", 1, 0]]);
    expect(problemsByFile(problems).get("a.py")).toEqual({ errors: 1, warnings: 1 });
  });
  it("derives job results from state and exit code, never from stderr", () => {
    const base = { label: "Build", kind: "build", started_at: 100, ended_at: 104.5, exit_code: 0, command: ["dotnet", "build"] };
    expect(jobTitle({ ...base, state: "completed" })).toEqual({ title: "Build succeeded", tone: "success" });
    expect(jobTitle({ ...base, state: "failed", exit_code: 1 })).toEqual({ title: "Build failed", tone: "error" });
    expect(jobTitle({ ...base, state: "running", exit_code: null, ended_at: null }).tone).toBe("running");
    expect(jobTitle({ ...base, state: "cancelled", exit_code: null }).tone).toBe("neutral");
    expect(jobTitle({ ...base, kind: "test", state: "completed" }).title).toBe("Tests succeeded");
    expect(elapsed(100, 104.5)).toBe("4.5 s");
  });
  it("names interpreters and language servers without absolute paths", () => {
    expect(runtimeLabel("python", "3.14.7", undefined, "/home/user/project/.venv/bin/python")).toBe("Python 3.14.7 (.venv)");
    expect(runtimeLabel("dotnet", undefined, "9.0.100")).toBe(".NET 9.0.100");
    const label = languageServerLabel([
      { language: "python", provider: "/home/user/Projects/OLIVE/.venv/bin/python", state: "ready" },
      { language: "csharp", provider: "C:\\tools\\OmniSharp.exe", state: "failed" },
    ]);
    expect(label.text).toBe("pylsp · OmniSharp failed");
    expect(label.text).not.toMatch(/[\\/]/);
    expect(label.failed).toBe(true);
  });
  it("normalises LSP symbols for the outline and breadcrumbs", () => {
    const symbols = normaliseSymbols([
      { name: "Scheduler", kind: 5, range: { start: { line: 20 }, end: { line: 60 } }, children: [
        { name: "plan", kind: 6, range: { start: { line: 27 }, end: { line: 40 } } },
      ] },
      { name: "legacy", kind: 12, location: { range: { start: { line: 70 }, end: { line: 75 } } } },
      { nope: true },
    ]);
    expect(symbols.map((s) => s.name)).toEqual(["Scheduler", "legacy"]);
    expect(symbolPath(symbols, 30).map((s) => s.name)).toEqual(["Scheduler", "plan"]);
    expect(symbolPath(symbols, 5)).toEqual([]);
    expect(cursorLabel(36, 17, 6, 1)).toBe("Ln 36, Col 17 (6 lines selected)");
    expect(cursorLabel(3, 2, 0, 0)).toBe("Ln 3, Col 2");
  });
});

describe("Studio V2 components", () => {
  it("renders the panel as a keyboard tablist that is collapsible and resizable", () => {
    const html = renderToStaticMarkup(createElement(StudioPanel, {
      tabs: ["problems", "output", "terminal", "console"], active: "output", select: noop, open: true, close: noop,
      height: 236, setHeight: noop, maximised: false, setMaximised: noop,
      counts: { problems: { count: 2, tone: "warning", spoken: "0 errors, 2 warnings" } },
      children: createElement("p", null, "body"),
    }));
    expect(html).toContain('role="tablist"');
    expect(html).toMatch(/role="tab"[^>]*aria-selected="true"[^>]*aria-label="Output"/);
    expect(html).toContain('aria-label="Problems, 0 errors, 2 warnings"');
    expect(html).toContain('role="separator"');
    expect(html).toContain('aria-label="Close panel"');
    expect(html).toContain('aria-label="Workspace tools"');
  });
  it("reports status without colour alone and never an interpreter path", () => {
    const html = renderToStaticMarkup(createElement(StatusBar, {
      branch: "main", branchDirty: true, errors: 1, warnings: 2, openProblems: noop, saveStatus: "",
      cursor: "Ln 1, Col 1", runtime: runtimeLabel("python", "3.14.7", undefined, "/abs/.venv/bin/python"),
      codeIntelligence: languageServerLabel([{ language: "python", provider: "/abs/python", state: "ready" }]),
    }));
    expect(html).toContain("main*");
    expect(html).toContain('aria-label="Problems: 1 error, 2 warnings"');
    expect(html).toContain("Local");
    expect(html).not.toContain("/abs");
  });
  it("shows remote attribution in the status bar when remote", () => {
    const html = renderToStaticMarkup(createElement(StatusBar, {
      remote: { device: "Gaming PC", online: false }, errors: 0, warnings: 0, openProblems: noop, saveStatus: "",
    }));
    expect(html).toContain("Gaming PC");
    expect(html).toContain(" · offline");
    expect(html).not.toContain(">Local<");
  });
  it("decorates Explorer rows with real Git, diagnostics and dirty state, spoken too", () => {
    const html = renderToStaticMarkup(createElement(Explorer, {
      entries: [{ path: "src", directory: true }, { path: "src/app.py", directory: false }],
      active: "src/app.py",
      open: noop,
      decorations: { git: new Map([["src/app.py", "M"], ["src", "•"]]), problems: new Map([["src/app.py", { errors: 2, warnings: 0 }]]), dirty: new Set(["src/app.py"]) },
    }));
    expect(html).toContain('aria-label="app.py"');
    expect(html).toContain('aria-description="modified, 2 errors, unsaved changes"');
    expect(html).toContain('data-git="M"');
    expect(html).toContain('aria-selected="true"');
  });
});

describe("OLIVE developer assistant context", () => {
  it("sends only the context the person switched on", () => {
    expect(withStudioContext("Why?", {})).toBe("Why?");
    const text = withStudioContext("Fix it", { problems: "a.py:1 error", changes: "" });
    expect(text).toContain("Problems reported in this workspace:\na.py:1 error");
    expect(text).not.toContain("Uncommitted changes");
    expect(text).not.toContain("Failing test");
  });
  it("shows the Studio thread after its anchor, not the whole conversation", () => {
    const chat = { id: "c", messages: [{ id: "1", role: "user", content: "old" }, { id: "2", role: "assistant", content: "old answer" }, { id: "3", role: "user", content: "new" }] } as unknown as Chat;
    expect(threadAfter(chat, { chatId: "c", after: "2" }).map((m) => m.id)).toEqual(["3"]);
    expect(threadAfter(chat, { chatId: "other", after: "2" })).toEqual([]);
    expect(threadAfter(chat, undefined)).toEqual([]);
  });
});
