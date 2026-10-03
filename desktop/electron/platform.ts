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

/** The only way to run OLIVE without Chromium's sandbox: set explicitly by a developer, never by OLIVE. */
export const UNSAFE_NO_SANDBOX_VARIABLE = "OLIVE_UNSAFE_ALLOW_NO_SANDBOX_DEVELOPER_ONLY";

export const SANDBOX_UNAVAILABLE_TITLE = "OLIVE could not start safely";
export const SANDBOX_UNAVAILABLE_MESSAGE = [
  "This system does not allow the sandbox OLIVE uses to isolate web content (unprivileged user namespaces are unavailable), so OLIVE did not start. Nothing was changed.",
  "",
  "To fix it:",
  "• Ubuntu 24.04 or later: AppArmor blocks user namespaces for apps without a profile. Extract OLIVE to a fixed folder and add an AppArmor profile that allows \"userns\" for its \"olive\" executable, as described in the OLIVE Linux install guide (\"Chromium sandbox\").",
  "• Other distributions: enable unprivileged user namespaces (for example sysctl kernel.unprivileged_userns_clone=1, or user.max_user_namespaces greater than 0).",
  "",
  "OLIVE never turns the sandbox off by itself.",
].join("\n");

/**
 * Linux sandbox policy. electron-builder's AppImage launcher appends --no-sandbox when
 * `unshare -Ur true` fails; OLIVE refuses to continue in that case (fail closed) unless a
 * developer set UNSAFE_NO_SANDBOX_VARIABLE=1 explicitly. Windows and macOS sandbox through
 * the operating system and are unaffected.
 */
export function sandboxPolicy(options: { platform: string; noSandboxSwitch: boolean; env: NodeJS.ProcessEnv }) {
  const unsandboxed = options.noSandboxSwitch || options.env.ELECTRON_DISABLE_SANDBOX === "1";
  if (options.platform !== "linux" || !unsandboxed) return { allowed: true, developerOverride: false };
  if (options.env[UNSAFE_NO_SANDBOX_VARIABLE] === "1") return { allowed: true, developerOverride: true };
  return { allowed: false, developerOverride: false, title: SANDBOX_UNAVAILABLE_TITLE, message: SANDBOX_UNAVAILABLE_MESSAGE };
}
