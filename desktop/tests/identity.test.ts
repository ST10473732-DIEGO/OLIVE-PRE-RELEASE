import { describe, expect, it } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { identity, normalizeEnvironment, resolveProfile } from "../electron/identity";
import metadata from "../package.json";
describe("shared OLIVE identity and profile continuity", () => {
  it("keeps current display identity and stable shell security identity", () => {
    expect(metadata.build.productName).toBe(identity.name);
    expect(metadata.name).toBe(identity.slug + "-desktop");
    expect(metadata.build.appId).toBe(identity.app_id);
    expect(identity.renderer_scheme).toBe("dmdo");
    expect(metadata.version.replace("-dev.", ".dev")).toBe(identity.version);
  });
  it("reuses legacy data, respects explicit paths, and refuses conflicting homes", () => {
    const home = mkdtempSync(path.join(tmpdir(), "olive-path-test-"));
    try {
      const old = path.join(home, ".dmdo"), current = path.join(home, ".olive");
      expect(resolveProfile({}, home, "win32")).toBe(current);
      expect(resolveProfile({}, home, "linux")).toBe(path.join(home, ".local/share/olive"));
      mkdirSync(old); writeFileSync(path.join(old, "settings.json"), "{}");
      expect(resolveProfile({}, home)).toBe(old);
      mkdirSync(current);
      expect(resolveProfile({}, home)).toBe(old);
      writeFileSync(path.join(current, "settings.json"), "{}");
      expect(() => resolveProfile({}, home)).toThrow("Both OLIVE");
      expect(resolveProfile({DMDO_DATA_DIR: old}, home)).toBe(old);
      expect(resolveProfile({OLIVE_DATA_DIR: "~/.olive"}, home)).toBe(current);
      expect(() => resolveProfile({DMDO_DATA_DIR: old, OLIVE_DATA_DIR: current}, home)).toThrow("Conflicting");
    } finally { rmSync(home, {recursive: true}); }
  });
  it("normalizes old settings but never silently overrides a conflicting security value", () => {
    expect(normalizeEnvironment({DMDO_ATTACH_DIAGNOSTICS: "1"}).OLIVE_ATTACH_DIAGNOSTICS).toBe("1");
    expect(() => normalizeEnvironment({DMDO_ATTACH_DIAGNOSTICS: "0", OLIVE_ATTACH_DIAGNOSTICS: "1"})).toThrow("Conflicting");
  });
});
