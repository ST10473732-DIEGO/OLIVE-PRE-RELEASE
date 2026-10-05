import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  enforceSandboxPolicy,
  SANDBOX_REFUSED_EXIT_CODE,
  sandboxPolicy,
  SANDBOX_UNAVAILABLE_MESSAGE,
  SANDBOX_UNAVAILABLE_TITLE,
  UNSAFE_NO_SANDBOX_VARIABLE,
} from "../electron/platform";

describe("Linux Chromium sandbox policy", () => {
  it("launches normally when the sandbox is available", () => {
    expect(sandboxPolicy({ platform: "linux", noSandboxSwitch: false, env: {} })).toEqual({ allowed: true, developerOverride: false });
  });
  it("fails closed when a launcher fell back to --no-sandbox", () => {
    const refused = sandboxPolicy({ platform: "linux", noSandboxSwitch: true, env: {} });
    expect(refused.allowed).toBe(false);
    expect(refused.message).toBe(SANDBOX_UNAVAILABLE_MESSAGE);
    expect(refused.message).toMatch(/Ubuntu 24\.04/);
    expect(refused.message).toMatch(/user namespaces/);
    expect(sandboxPolicy({ platform: "linux", noSandboxSwitch: false, env: { ELECTRON_DISABLE_SANDBOX: "1" } }).allowed).toBe(false);
  });
  it("allows only the explicit developer override, never a lookalike", () => {
    expect(sandboxPolicy({ platform: "linux", noSandboxSwitch: true, env: { [UNSAFE_NO_SANDBOX_VARIABLE]: "1" } }))
      .toEqual({ allowed: true, developerOverride: true });
    for (const value of ["true", "yes", "0", ""])
      expect(sandboxPolicy({ platform: "linux", noSandboxSwitch: true, env: { [UNSAFE_NO_SANDBOX_VARIABLE]: value } }).allowed).toBe(false);
    expect(UNSAFE_NO_SANDBOX_VARIABLE).toMatch(/UNSAFE.*DEVELOPER_ONLY/);
  });
  it("does not affect Windows or macOS", () => {
    for (const platform of ["win32", "darwin"])
      expect(sandboxPolicy({ platform, noSandboxSwitch: true, env: {} }).allowed).toBe(true);
  });
  it("is enforced before any window or backend starts", () => {
    const main = readFileSync(path.join(__dirname, "../electron/main/index.ts"), "utf8");
    const check = main.indexOf("sandboxPolicy({");
    expect(check).toBeGreaterThan(0);
    expect(check).toBeLessThan(main.indexOf("new Backend("));
    expect(check).toBeLessThan(main.indexOf("new BrowserWindow("));
    expect(main).toMatch(/enforceSandboxPolicy\(sandbox,/);
    expect(main).toMatch(/if \(refused\) return;/);
    const config = JSON.parse(readFileSync(path.join(__dirname, "../package.json"), "utf8"));
    expect(config.build.appImage.executableArgs).toEqual([]);
  });
  it("refuses only after the modal error is dismissed, then exits with 78", () => {
    const events: string[] = [];
    let dismissed = false;
    const refused = enforceSandboxPolicy(sandboxPolicy({ platform: "linux", noSandboxSwitch: true, env: {} }), {
      error: (text) => events.push(`stderr:${text.split("\n")[0]}`),
      // dialog.showErrorBox is modal: it returns only when the person dismisses it.
      showError: (title, message) => {
        events.push(`dialog:${title}`);
        expect(message).toBe(SANDBOX_UNAVAILABLE_MESSAGE);
        dismissed = true;
      },
      exit: (code) => {
        expect(dismissed).toBe(true);
        events.push(`exit:${code}`);
      },
      warn: () => events.push("warn"),
    });
    expect(refused).toBe(true);
    expect(SANDBOX_REFUSED_EXIT_CODE).toBe(78);
    expect(events).toEqual([`stderr:${SANDBOX_UNAVAILABLE_TITLE}`, `dialog:${SANDBOX_UNAVAILABLE_TITLE}`, "exit:78"]);
  });
  it("continues (and warns only for the developer override) when the sandbox is allowed", () => {
    const calls: string[] = [];
    const effects = { error: () => calls.push("error"), showError: () => calls.push("dialog"), exit: () => calls.push("exit"), warn: (t: string) => calls.push(t) };
    expect(enforceSandboxPolicy(sandboxPolicy({ platform: "linux", noSandboxSwitch: false, env: {} }), effects)).toBe(false);
    expect(calls).toEqual([]);
    expect(enforceSandboxPolicy(sandboxPolicy({ platform: "linux", noSandboxSwitch: true, env: { [UNSAFE_NO_SANDBOX_VARIABLE]: "1" } }), effects)).toBe(false);
    expect(calls).toEqual([`${UNSAFE_NO_SANDBOX_VARIABLE}=1: running WITHOUT the Chromium sandbox (developer only).`]);
  });
});
