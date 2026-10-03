import { afterEach, expect, it } from "vitest";
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const { validateBackendArtifact } = require("../scripts/backend-artifact.cjs") as {
  validateBackendArtifact: (directory: string, platform: string, arch: string) => string[];
};
const identity = require("../../olive/identity.json") as { version: string };
const roots: string[] = [];
afterEach(() => roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true })));

function artefact(target: string, python: string, site: string, extra: (root: string) => void = () => undefined) {
  const root = mkdtempSync(path.join(tmpdir(), "olive-artefact-"));
  roots.push(root);
  const put = (relative: string, content = "") => {
    mkdirSync(path.dirname(path.join(root, relative)), { recursive: true });
    writeFileSync(path.join(root, relative), content);
  };
  put(python);
  put("olive/__init__.py");
  put("olive/bridge/__main__.py");
  put("olive/identity.json", JSON.stringify({ version: identity.version }));
  put(`${site}/olive-backend.pth`, "../../..\n");
  put("olive-backend.json", JSON.stringify({ schema: "olive-backend/1", target, version: identity.version, layout: { python } }));
  extra(root);
  return root;
}

it("accepts the platform-correct layouts", () => {
  expect(validateBackendArtifact(artefact("linux-x86_64", "bin/python3", "lib/python3.14/site-packages"), "linux", "x64")).toEqual([]);
  expect(validateBackendArtifact(artefact("windows-x86_64", "python.exe", "Lib/site-packages"), "win32", "x64")).toEqual([]);
  expect(validateBackendArtifact(artefact("macos-arm64", "bin/python3", "lib/python3.14/site-packages"), "darwin", "arm64")).toEqual([]);
});

it("refuses a backend built for another platform or architecture", () => {
  const linux = artefact("linux-x86_64", "bin/python3", "lib/python3.14/site-packages");
  expect(validateBackendArtifact(linux, "win32", "x64")).toContain("Artefact is for linux-x86_64, packaging needs windows-x86_64");
  expect(validateBackendArtifact(linux, "darwin", "x64")).toEqual(["No OLIVE backend target for darwin/x64"]);
  expect(validateBackendArtifact(path.join(linux, "missing"), "linux", "x64")[0]).toMatch(/build_backend\.py/);
});

it("refuses a development tree: no manifest, Qt, dmdo, Playwright or pip", () => {
  const plain = artefact("linux-x86_64", "bin/python3", "lib/python3.14/site-packages", (root) => rmSync(path.join(root, "olive-backend.json")));
  expect(validateBackendArtifact(plain, "linux", "x64")[0]).toMatch(/olive-backend\.json/);
  const polluted = artefact("linux-x86_64", "bin/python3", "lib/python3.14/site-packages", (root) => {
    for (const dir of ["olive/ui_qt", "dmdo", "lib/python3.14/site-packages/PySide6", "lib/python3.14/site-packages/playwright", "lib/python3.14/site-packages/pip-25.0.dist-info"])
      mkdirSync(path.join(root, dir), { recursive: true });
  });
  const problems = validateBackendArtifact(polluted, "linux", "x64");
  for (const item of ["olive/ui_qt", "dmdo", "PySide6", "playwright", "pip-25.0.dist-info"])
    expect(problems.some((problem) => problem.includes(item))).toBe(true);
});
