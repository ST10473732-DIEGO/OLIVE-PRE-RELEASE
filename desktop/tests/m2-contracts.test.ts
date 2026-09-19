import { expect, it } from "vitest";
import { validateCall } from "../electron/contracts";
import { fileActionSchema } from "../electron/file-actions";
it("native file choices cannot be supplied as generic renderer paths", () => {
  for (const method of [
    "data.backup",
    "data.restore",
    "data.export",
    "knowledge.attach",
    "data.create_workspace",
  ]) {
    expect(() =>
      validateCall({ id: "fixture", method, args: { path: "unapproved" } }),
    ).toThrow();
  }
  expect(() =>
    fileActionSchema.parse({ action: "backup", path: "unapproved" }),
  ).toThrow();
  expect(
    fileActionSchema.parse({ action: "export-chat", chat_id: "fixture" }),
  ).toEqual({ action: "export-chat", chat_id: "fixture" });
});
it("M2 methods reject unknown and oversized nested arguments", () => {
  expect(() =>
    validateCall({
      id: "fixture",
      method: "data.save_settings",
      args: {
        chat_id: "fixture",
        params: {},
        system_prompt: "",
        settings: { nested: Array(201).fill("x") },
      },
    }),
  ).toThrow();
  expect(() =>
    validateCall({
      id: "fixture",
      method: "data.projects",
      args: { arbitrary: "x" },
    }),
  ).toThrow();
});
