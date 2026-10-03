import path from "node:path";

export function backendPython(root: string, packaged: boolean, env: NodeJS.ProcessEnv, platform = process.platform) {
  if (packaged) return path.join(root, platform === "win32" ? "python.exe" : "bin/python3");
  return env.OLIVE_PYTHON || path.join(root, ".venv", platform === "win32" ? "Scripts/python.exe" : "bin/python");
}

/** -s: no user site-packages; -P: never import from the working directory (olive is on the artefact's path). */
export function backendArguments(packaged: boolean) {
  return packaged ? ["-s", "-P", "-u", "-m", "olive.bridge"] : ["-u", "-m", "olive.bridge"];
}

/**
 * The packaged backend gets a clean interpreter environment: inherited PYTHONHOME/PYTHONPATH
 * can never redirect it, it writes no byte-code into the read-only installation, and it learns
 * which launcher (the AppImage file, not its temporary mount) desktop entries should start.
 */
export function backendEnvironment(
  env: NodeJS.ProcessEnv,
  options: { packaged: boolean; profile: string; uiProcessId: number; executable: string },
): NodeJS.ProcessEnv {
  const result: NodeJS.ProcessEnv = {
    ...env,
    OLIVE_DATA_DIR: options.profile,
    OLIVE_UI_PROCESS_ID: String(options.uiProcessId),
    PYTHONIOENCODING: "utf-8",
  };
  if (!options.packaged) return result;
  for (const key of Object.keys(result))
    if (key === "PYTHONHOME" || key === "PYTHONPATH" || key === "PYTHONSTARTUP" || key === "PYTHONUSERBASE")
      delete result[key];
  result.PYTHONDONTWRITEBYTECODE = "1";
  result.PYTHONNOUSERSITE = "1";
  result.OLIVE_APP_EXECUTABLE = env.APPIMAGE || options.executable;
  // The packaged app may start its own loopback Ollama when none is running (opt out with 0).
  result.OLIVE_START_OLLAMA = env.OLIVE_START_OLLAMA ?? "1";
  return result;
}

export function iconName(platform = process.platform) {
  return platform === "win32" ? "olive.ico" : "olive-256.png";
}

/** Branding files: copied next to the backend in a package, read from assets/ in a checkout. */
export function brandingAsset(name: string, packaged: boolean, root: string, resourcesPath: string) {
  return packaged ? path.join(resourcesPath, name) : path.join(root, "assets/branding", name);
}
