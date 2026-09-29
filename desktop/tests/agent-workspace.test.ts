import { describe, expect, it } from "vitest";
import { validateCall } from "../electron/contracts";
import { panelTabs, PANEL_LABELS } from "../src/features/studio/studioModel";

const id = "550e8400-e29b-41d4-a716-446655440000";

describe("agent workspace contracts", () => {
  it("exposes task inspection and control by task id only", () => {
    for (const method of ["agent.task_diff", "agent.stop_task", "agent.stop_preview", "agent.revert"] as const)
      expect(validateCall({ id, method, args: { task_id: "t1" } }).args).toEqual({ task_id: "t1" });
    expect(validateCall({ id, method: "agent.chat_tasks", args: { chat_id: "c" } }).args).toEqual({ chat_id: "c" });
    expect(validateCall({ id, method: "agent.workspace_task", args: { workspace_id: "w" } }).args).toEqual({ workspace_id: "w" });
  });
  it("rejects authority, paths and commands on task routes", () => {
    for (const extra of [{ approved: true }, { path: "/etc/passwd" }, { command: "rm -rf /" }, { owner_mode: true }])
      expect(() => validateCall({ id, method: "agent.revert", args: { task_id: "t1", ...extra } })).toThrow();
    expect(() => validateCall({ id, method: "agent.run_command", args: { command: "ls" } })).toThrow();
  });
});

describe("Studio task panel", () => {
  it("adds the Task tab last, only when a task exists", () => {
    expect(panelTabs(false)).not.toContain("task");
    expect(panelTabs(false, { task: true }).at(-1)).toBe("task");
    expect(panelTabs(true, { task: true })).toEqual(["output"]);
    expect(PANEL_LABELS.task).toBe("Task");
  });
});
