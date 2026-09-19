import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  outputReducer,
  validationChannel,
  type OutputState,
} from "../src/services/studioOutput";
import { visibleEntries } from "../src/components/Explorer";
import {
  features,
  launcherFeatures,
  navigationFeatures,
  searchFeatures,
} from "../src/navigation/features";
import { ApprovalSummary } from "../src/components/ApprovalSummary";

describe("M1 review corrections", () => {
  it("retains test identity when details change and isolates workspace selection", () => {
    let state: OutputState = { channels: [], selected: {} };
    const test = validationChannel({
      id: "test-1",
      workspace_id: "a",
      state: "completed",
      summary: "Passed",
      results: [{ name: "Tests", stdout: "OK" }],
    });
    state = outputReducer(state, { channel: test });
    state = outputReducer(state, {
      channel: {
        id: "details",
        workspace_id: "a",
        label: "Details",
        text: "diff",
      },
    });
    state = outputReducer(state, {
      channel: {
        id: "other-run",
        workspace_id: "b",
        label: "Run",
        text: "Other",
      },
    });
    state = outputReducer(state, { workspace: "a", select: "test-1" });
    expect(
      state.channels.find((c) => c.id === state.selected.a)?.text,
    ).toContain("OK");
    expect(state.selected.b).toBe("other-run");
    for (let i = 0; i < 20; i++)
      state = outputReducer(state, {
        channel: { ...test, id: `test-${i}`, text: "x".repeat(200000) },
      });
    expect(state.channels).toHaveLength(12);
    expect(state.channels.every((c) => c.text.length <= 150000)).toBe(true);
  });
  it("orders folders with their children and hides descendants on collapse", () => {
    const entries = [
      { path: "tests/test_main.py", directory: false },
      { path: "main.py", directory: false },
      { path: "tests", directory: true },
    ];
    expect(visibleEntries(entries, new Set()).map((e) => e.path)).toEqual([
      "tests",
      "tests/test_main.py",
      "main.py",
    ]);
    expect(
      visibleEntries(entries, new Set(["tests"])).map((e) => e.path),
    ).toEqual(["tests", "main.py"]);
  });
  it("drives navigation, the launcher and search from one feature registry", () => {
    // Every shipped capability the brief names must be reachable by label.
    for (const id of [
      "home", "chat", "studio", "research", "agent", "desktop", "projects",
      "knowledge", "memory", "calendar", "tasks", "reminders",
      "mail", "settings", "connections", "diagnostics",
    ])
      expect(features.map((f) => f.id)).toContain(id);
    // Ids and labels are unique, so navigation and the palette cannot show
    // two rows that mean the same destination.
    expect(new Set(features.map((f) => f.id)).size).toBe(features.length);
    expect(new Set(features.map((f) => f.label)).size).toBe(features.length);
    // Every feature carries a readable label and a one-line description.
    for (const feature of features) {
      expect(feature.label.trim().length).toBeGreaterThan(0);
      expect(feature.description.trim().length).toBeGreaterThan(0);
    }
    // Diagnostics is reached through Settings, so it is not its own nav row.
    expect(navigationFeatures.map((f) => f.id)).not.toContain("diagnostics");
    expect(features.find((f) => f.id === "diagnostics")?.within).toBe("settings");
    // The launcher offers destinations other than Home itself.
    expect(launcherFeatures.map((f) => f.id)).not.toContain("home");
    // Search finds a feature by a word a person would actually type.
    expect(searchFeatures("email").map((f) => f.id)).toContain("mail");
    expect(searchFeatures("ide").map((f) => f.id)).toContain("studio");
    expect(searchFeatures("todo").map((f) => f.id)).toContain("tasks");
    expect(searchFeatures("logs").map((f) => f.id)).toContain("diagnostics");
    expect(searchFeatures("zzzz")).toEqual([]);
  });
  it("places approval content and consequence before collapsed technical details", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalSummary, {
        approval: {
          id: "a",
          fingerprint: "f",
          summary: "Run checks",
          tool_name: "workspace.run_validation",
          risk_level: "high",
          targets: ["Fixture workspace"],
          arguments: {},
          presentation: {
            action: "Run tests",
            content: "python -m unittest",
            scope: "One workspace",
            consequence: "Executes project code",
          },
        },
      }),
    );
    expect(html.indexOf("python -m unittest")).toBeLessThan(
      html.indexOf("<details>"),
    );
    expect(html).toContain("Executes project code");
    expect(html).not.toContain("<details open");
  });
});
