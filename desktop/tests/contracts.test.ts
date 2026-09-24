import { describe, expect, it } from "vitest";
import { validateCall } from "../electron/contracts";
const id = "550e8400-e29b-41d4-a716-446655440000";
describe("main-process contract", () => {
  it("accepts a selected workspace reference without accepting authority fields", () => {
    const args = {chat_id: "chat", text: "Run my project", workspace_id: "selected"};
    expect(validateCall({id, method: "interaction.submit", args}).args).toEqual(args);
    for (const field of ["approved", "owner_mode", "permission", "ignore_user_policy", "disable_stop", "grant_root", "extra_recipient"])
      expect(() => validateCall({id, method: "interaction.submit", args: {...args, [field]: true}})).toThrow();
  });
  it("rejects arbitrary service methods and workspace path injection", () => {
    expect(() =>
      validateCall({ id, method: "agent.tool", args: {} }),
    ).toThrow();
    expect(() =>
      validateCall({
        id,
        method: "workspace.open",
        args: { path: "C:/private" },
      }),
    ).toThrow();
    expect(() =>
      validateCall({
        id,
        method: "studio.open",
        args: { workspace_id: "w", path: "a", shell: "powershell" },
      }),
    ).toThrow();
  });
  it("requires explicit approval identity and boolean", () => {
    expect(() =>
      validateCall({
        id,
        method: "approval.respond",
        args: { approved: true },
      }),
    ).toThrow();
    expect(() =>
      validateCall({
        id,
        method: "approval.respond",
        args: { approval_id: "a", fingerprint: "b", approved: "yes" },
      }),
    ).toThrow();
  });
  it("bounds source buffers and rejects extra envelope fields", () => {
    expect(() =>
      validateCall({ id, method: "runtime.snapshot", args: {}, secret: true }),
    ).toThrow();
    expect(() =>
      validateCall({
        id,
        method: "studio.save",
        args: {
          workspace_id: "w",
          path: "p",
          text: "x".repeat(400001),
          expected_hash: "hash",
        },
      }),
    ).toThrow();
    expect(
      validateCall({ id, method: "runtime.snapshot", args: {} }).method,
    ).toBe("runtime.snapshot");
  });
});
