import { expect, it } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { resolveProfile } from "../electron/identity";
import { backendPython, iconName } from "../electron/platform";

it("selects native development executables and preserves Windows", () => {
  expect(backendPython("repo", false, {}, "linux")).toBe(path.join("repo", ".venv/bin/python"));
  expect(backendPython("repo", false, {}, "win32")).toBe(path.join("repo", ".venv/Scripts/python.exe"));
  expect(backendPython("repo", false, { OLIVE_PYTHON: "/custom/python" }, "linux")).toBe("/custom/python");
  expect(iconName("linux")).toBe("olive-256.png");
  expect(iconName("win32")).toBe("olive.ico");
});

it("honours absolute XDG paths and refuses conflicting profile data", () => {
  const home = mkdtempSync(path.join(tmpdir(), "olive-xdg-"));
  try {
    const xdg = path.join(home, "data"), profile = path.join(xdg, "olive"), old = path.join(home, ".olive");
    expect(resolveProfile({ XDG_DATA_HOME: xdg }, home, "linux")).toBe(profile);
    expect(resolveProfile({ XDG_DATA_HOME: "relative" }, home, "linux")).toBe(path.join(home, ".local/share/olive"));
    mkdirSync(old); writeFileSync(path.join(old, "settings.json"), "{}");
    expect(resolveProfile({ XDG_DATA_HOME: xdg }, home, "linux")).toBe(old);
    mkdirSync(profile, { recursive: true }); writeFileSync(path.join(profile, "settings.json"), "{}");
    expect(() => resolveProfile({ XDG_DATA_HOME: xdg }, home, "linux")).toThrow("Multiple OLIVE");
    expect(resolveProfile({ XDG_DATA_HOME: xdg, OLIVE_DATA_DIR: old }, home, "linux")).toBe(old);
  } finally { rmSync(home, { recursive: true }); }
});
