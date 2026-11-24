import { expect, it } from "vitest";
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir, userInfo } from "node:os";
import path from "node:path";
import { backendEnvironment, findExternalWorkspace, WORKSPACE_ANCHOR } from "../electron/platform";

it.skipIf(process.platform !== "darwin")(
  "separates macOS login-Keychain HOME from verified external Ollama HOME",
  () => {
    const external = "/Volumes/Example Drive/OLIVE-macOS";
    const profile = external + "/data-private/packaged-preview";
    const env = backendEnvironment({
      HOME: external + "/envs/ollama-home",
      OLLAMA_MODELS: external + "/model-store/ollama",
      HF_HOME: external + "/cache/hf",
      XDG_CACHE_HOME: external + "/cache/xdg",
      XDG_CONFIG_HOME: external + "/envs/ollama-home/.config",
      TMPDIR: external + "/cache/tmp/",
      OLIVE_MACOS_KEYCHAIN_LOGIN_HOME: "1",
      OLIVE_MACOS_EXTERNAL_ROOT: external,
    }, { packaged: true, profile, uiProcessId: 4321, executable: "/Applications/OLIVE.app" });
    expect(env.HOME).toBe(userInfo().homedir);
    expect(env.OLIVE_OLLAMA_EXTERNAL_HOME).toBe(external + "/envs/ollama-home");
    expect(env.OLLAMA_MODELS).toBe(external + "/model-store/ollama");
    expect(env.HF_HOME).toBe(external + "/cache/hf");
    expect(env.XDG_CACHE_HOME).toBe(external + "/cache/xdg");
    expect(env.OLIVE_DATA_DIR).toBe(profile);
    // An external HOME outside the verified workspace (or no workspace) is refused.
    for (const root of [undefined, "/Volumes/Other Drive/OLIVE-macOS"])
      expect(() => backendEnvironment({ HOME: external + "/envs/ollama-home", OLIVE_MACOS_KEYCHAIN_LOGIN_HOME: "1",
        ...(root ? { OLIVE_MACOS_EXTERNAL_ROOT: root } : {}) },
        { packaged: true, profile, uiProcessId: 4321, executable: "/Applications/OLIVE.app" })).toThrow();
  },
);

it("finds the workspace from the app's own location, never a built-in path", () => {
  const volumes = realpathSync(mkdtempSync(path.join(tmpdir(), "olive-volumes-")));
  const root = path.join(volumes, "Any Drive", "OLIVE-macOS");
  const app = path.join(root, "apps/v13/mac-arm64/olive.app/Contents/MacOS/olive");
  mkdirSync(path.dirname(app), { recursive: true });
  writeFileSync(app, "");
  mkdirSync(path.join(root, "docs"));
  const uuid = "12345678-1234-1234-1234-123456789ABC";
  writeFileSync(path.join(root, WORKSPACE_ANCHOR), JSON.stringify({ root, volume_uuid: uuid }));
  expect(findExternalWorkspace(app, {}, volumes)).toEqual({ root, volume: path.join(volumes, "Any Drive"), volumeUuid: uuid });
  // The anchor must name its own folder, and the app must be inside it.
  writeFileSync(path.join(root, WORKSPACE_ANCHOR), JSON.stringify({ root: "/elsewhere", volume_uuid: uuid }));
  expect(findExternalWorkspace(app, {}, volumes)).toBeNull();
  writeFileSync(path.join(root, WORKSPACE_ANCHOR), JSON.stringify({ root, volume_uuid: uuid }));
  const outside = path.join(volumes, "outside-app");
  writeFileSync(outside, "");
  expect(findExternalWorkspace(outside, { OLIVE_MACOS_EXTERNAL_ROOT: root }, volumes)).toBeNull();
  // Not on a mounted volume (for example the system disk): refused.
  expect(findExternalWorkspace(app, {}, path.join(volumes, "Any Drive", "OLIVE-macOS", "apps"))).toBeNull();
});
