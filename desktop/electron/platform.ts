import path from "node:path";

export function backendPython(root: string, packaged: boolean, env: NodeJS.ProcessEnv, platform = process.platform) {
  if (packaged) return path.join(root, platform === "win32" ? "python.exe" : "bin/python3");
  return env.OLIVE_PYTHON || path.join(root, ".venv", platform === "win32" ? "Scripts/python.exe" : "bin/python");
}

export function iconName(platform = process.platform) {
  return platform === "win32" ? "olive.ico" : "olive-256.png";
}
