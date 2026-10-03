// Validates desktop/backend-artifact/ before electron-builder copies it to resources/backend.
// The artefact is built per OS by packaging/backend/build_backend.py; see packaging/backend/README.md.
const fs = require("node:fs");
const path = require("node:path");

const TARGETS = {
  linux: { x64: "linux-x86_64" },
  win32: { x64: "windows-x86_64" },
  darwin: { arm64: "macos-arm64" },
};
const PYTHON = { linux: "bin/python3", win32: "python.exe", darwin: "bin/python3" };
// Never shipped in the Electron backend.
const FORBIDDEN = ["olive/ui_qt", "dmdo", "olive/__main__.py"];
const FORBIDDEN_PACKAGES = ["PySide6", "shiboken6", "playwright", "pip"];

function sitePackages(directory, platform) {
  if (platform === "win32") return path.join(directory, "Lib", "site-packages");
  const lib = path.join(directory, "lib");
  const version = fs.existsSync(lib) ? fs.readdirSync(lib).find((name) => /^python3\.\d+$/.test(name)) : undefined;
  return version ? path.join(lib, version, "site-packages") : path.join(lib, "python3", "site-packages");
}

/** Returns a list of problems; empty means the artefact fits this platform/arch. */
function validateBackendArtifact(directory, platform, arch) {
  const problems = [];
  const expected = TARGETS[platform]?.[arch];
  if (!expected) return [`No OLIVE backend target for ${platform}/${arch}`];
  if (!fs.existsSync(directory)) return [`Missing ${directory}. Run: python packaging/backend/build_backend.py`];
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(path.join(directory, "olive-backend.json"), "utf8"));
  } catch {
    return ["Missing or unreadable olive-backend.json (build the artefact with packaging/backend/build_backend.py)"];
  }
  if (manifest.schema !== "olive-backend/1") problems.push(`Unknown artefact schema ${manifest.schema}`);
  if (manifest.target !== expected) problems.push(`Artefact is for ${manifest.target}, packaging needs ${expected}`);
  const python = PYTHON[platform];
  if (manifest.layout?.python !== python) problems.push(`Artefact interpreter is ${manifest.layout?.python}, expected ${python}`);
  if (!fs.existsSync(path.join(directory, python))) problems.push(`Missing interpreter ${python}`);
  for (const file of ["olive/__init__.py", "olive/identity.json", "olive/bridge/__main__.py", "THIRD_PARTY-backend.txt"])
    if (!fs.existsSync(path.join(directory, file))) problems.push(`Missing ${file}`);
  for (const item of FORBIDDEN) if (fs.existsSync(path.join(directory, item))) problems.push(`Excluded ${item} is present`);
  const site = sitePackages(directory, platform);
  if (!fs.existsSync(path.join(site, "olive-backend.pth"))) problems.push("Missing olive-backend.pth");
  if (fs.existsSync(site))
    for (const name of fs.readdirSync(site))
      if (FORBIDDEN_PACKAGES.some((item) => name.toLowerCase() === item.toLowerCase() || name.toLowerCase().startsWith(item.toLowerCase() + "-")))
        problems.push(`Excluded package ${name} is present`);
  try {
    const identity = JSON.parse(fs.readFileSync(path.join(directory, "olive", "identity.json"), "utf8"));
    if (identity.version !== manifest.version) problems.push(`Artefact version ${manifest.version} differs from its olive ${identity.version}`);
  } catch {
    // Reported above as a missing file.
  }
  return problems;
}

module.exports = { validateBackendArtifact, TARGETS, PYTHON };
