import { expect, it } from "vitest";
import { mkdtempSync, mkdirSync, realpathSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { resolveProfile } from "../electron/identity";
import { backendArguments, backendEnvironment, backendPython, brandingAsset, iconName } from "../electron/platform";

it("selects native development executables and preserves Windows", () => {
  expect(backendPython("repo", false, {}, "linux")).toBe(path.join("repo", ".venv/bin/python"));
  expect(backendPython("repo", false, {}, "win32")).toBe(path.join("repo", ".venv/Scripts/python.exe"));
  expect(backendPython("repo", false, { OLIVE_PYTHON: "/custom/python" }, "linux")).toBe("/custom/python");
  expect(iconName("linux")).toBe("olive-256.png");
  expect(iconName("win32")).toBe("olive.ico");
});

it("honours absolute XDG paths and refuses conflicting profile data", () => {
  const home = realpathSync(mkdtempSync(path.join(tmpdir(), "olive-xdg-")));
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

it("starts the packaged backend from its own artefact with a clean interpreter environment", () => {
  expect(backendPython("/opt/OLIVE/resources/backend", true, { OLIVE_PYTHON: "/repo/.venv/bin/python" }, "linux"))
    .toBe(path.join("/opt/OLIVE/resources/backend", "bin/python3"));
  expect(backendPython("C:/OLIVE/resources/backend", true, {}, "win32")).toBe(path.join("C:/OLIVE/resources/backend", "python.exe"));
  expect(backendArguments(true)).toEqual(["-s", "-P", "-u", "-m", "olive.bridge"]);
  expect(backendArguments(false)).toEqual(["-u", "-m", "olive.bridge"]);
  const inherited = { PATH: "/usr/bin", PYTHONHOME: "/elsewhere", PYTHONPATH: "/elsewhere", APPIMAGE: "/home/u/OLIVE-1.0.0.AppImage" };
  const packaged = backendEnvironment(inherited, { packaged: true, profile: "/p", uiProcessId: 7, executable: "/tmp/.mount_x/olive" });
  expect(packaged.PYTHONHOME).toBeUndefined();
  expect(packaged.PYTHONPATH).toBeUndefined();
  expect(packaged.PYTHONDONTWRITEBYTECODE).toBe("1");
  expect(packaged.OLIVE_APP_EXECUTABLE).toBe("/home/u/OLIVE-1.0.0.AppImage");
  expect(packaged.OLIVE_START_OLLAMA).toBe("1");
  expect(packaged.OLIVE_DATA_DIR).toBe("/p");
  expect(backendEnvironment({ OLIVE_START_OLLAMA: "0" }, { packaged: true, profile: "/p", uiProcessId: 7, executable: "/x" }).OLIVE_START_OLLAMA).toBe("0");
  const source = backendEnvironment(inherited, { packaged: false, profile: "/p", uiProcessId: 7, executable: "/x" });
  expect(source.PYTHONPATH).toBe("/elsewhere");
  expect(source.OLIVE_APP_EXECUTABLE).toBeUndefined();
});

it("reads branding next to the packaged backend, from assets in a checkout", () => {
  expect(brandingAsset("olive-256.png", true, "/r/backend", "/r")).toBe(path.join("/r", "olive-256.png"));
  expect(brandingAsset("olive-256.png", false, "/repo", "/unused")).toBe(path.join("/repo", "assets/branding", "olive-256.png"));
});
