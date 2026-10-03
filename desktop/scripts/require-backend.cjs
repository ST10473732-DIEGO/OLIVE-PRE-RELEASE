// electron-builder beforePack hook: refuse to package without a validated, platform-correct backend.
const path = require("node:path");
const { validateBackendArtifact } = require("./backend-artifact.cjs");
const ARCH = { 0: "ia32", 1: "x64", 2: "armv7l", 3: "arm64", 4: "universal" };

module.exports = async (context) => {
  const directory = path.join(context.packager.projectDir, "backend-artifact");
  const arch = ARCH[context.arch] ?? String(context.arch);
  const problems = validateBackendArtifact(directory, context.electronPlatformName, arch);
  if (problems.length)
    throw new Error(
      `Packaging requires a self-contained OLIVE backend for ${context.electronPlatformName}/${arch}:\n- ` +
        problems.join("\n- ") +
        "\nBuild it on that platform with: python packaging/backend/build_backend.py",
    );
};
