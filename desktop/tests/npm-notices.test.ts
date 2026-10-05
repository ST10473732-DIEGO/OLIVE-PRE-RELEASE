import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const { noticeText, runtimePackages } = require("../scripts/npm-notices.cjs") as {
  noticeText(project: string): { text: string };
  runtimePackages(project: string): { name: string; version: string }[];
};

const project = path.join(__dirname, "..");

describe("packaged third-party notices", () => {
  it("cover every runtime npm package with its own licence files, including the OFL fonts", () => {
    const packages = runtimePackages(project);
    const names = packages.map((p) => p.name);
    expect(names).toEqual(expect.arrayContaining(["react", "yjs", "zod", "dompurify", "@fontsource-variable/onest"]));
    expect(names).not.toContain("vitest"); // Development-only packages are not shipped.
    expect(names).not.toContain("electron");
    const { text } = noticeText(project);
    expect(text).toMatch(/SIL OPEN FONT LICENSE Version 1\.1/);
    expect(text).toMatch(/react \d+\.\d+\.\d+ \(MIT\)/);
    expect(text).toMatch(/Flagged for owner\/legal review/);
  });
  it("ship npm, Electron and Chromium notices in resources/legal", () => {
    const config = JSON.parse(readFileSync(path.join(project, "package.json"), "utf8"));
    const legal = Object.fromEntries(
      (config.build.extraResources as { from: string; to: string }[]).filter((r) => r.to.startsWith("legal/")).map((r) => [r.to, r.from]),
    );
    expect(legal["legal/THIRD_PARTY-npm.txt"]).toBe("out/legal/THIRD_PARTY-npm.txt");
    expect(legal["legal/LICENSE.electron.txt"]).toBe("node_modules/electron/dist/LICENSE");
    expect(legal["legal/LICENSES.chromium.html"]).toBe("node_modules/electron/dist/LICENSES.chromium.html");
    expect(config.scripts.build).toMatch(/npm-notices\.cjs/);
    expect(readFileSync(path.join(project, "scripts/require-backend.cjs"), "utf8")).toMatch(/THIRD_PARTY-npm\.txt/);
  });
});
