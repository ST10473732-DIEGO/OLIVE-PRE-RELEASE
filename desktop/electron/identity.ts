import identity from "../../olive/identity.json";
import path from "node:path";
import { existsSync, readdirSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
export { identity };
function canonicalPath(value: string, home = homedir()): string {
  const expanded = value === "~" ? home : /^~[\\/]/.test(value) ? path.join(home, value.slice(2)) : value;
  const absolute = path.resolve(expanded);
  if (existsSync(absolute)) return realpathSync(absolute);
  const parent = path.dirname(absolute);
  return parent === absolute ? absolute : path.join(canonicalPath(parent, home), path.basename(absolute));
}
export function normalizeEnvironment(env: NodeJS.ProcessEnv) {
  for (const old of Object.keys(env)) {
    if (!old.startsWith("DMDO_")) continue;
    const key = "OLIVE_" + old.slice(5), legacy = env[old], current = env[key];
    if (legacy && current && legacy !== current) {
      const isPath = ["OLIVE_DATA_DIR", "OLIVE_PYTHON"].includes(key);
      const equalPath = isPath && canonicalPath(legacy) === canonicalPath(current);
      if (!equalPath) throw new Error(`Conflicting ${key} and ${old}; select one explicit configuration`);
    }
    if (!current && legacy) env[key] = legacy;
  }
  return env;
}
export function resolveProfile(env: NodeJS.ProcessEnv, home = homedir(), platform: NodeJS.Platform = process.platform) {
  const config = normalizeEnvironment({ ...env });
  if (config.OLIVE_DATA_DIR) return canonicalPath(config.OLIVE_DATA_DIR, home);
  const current = path.join(home, identity.default_directory), legacy = path.join(home, identity.legacy_directory);
  const occupied = (p: string) => existsSync(p) && (!statSync(p).isDirectory() || readdirSync(p).length > 0);
  if (occupied(current) && occupied(legacy) && canonicalPath(current) !== canonicalPath(legacy))
    throw new Error("Both OLIVE and legacy DMDO profile locations contain data. Set OLIVE_DATA_DIR explicitly; nothing was merged or moved.");
  const xdg = config.XDG_DATA_HOME;
  const fallback = platform === "linux"
    ? path.join(xdg && path.isAbsolute(xdg) ? xdg : path.join(home, ".local/share"), "olive")
    : current;
  if (occupied(fallback) && [current, legacy].some(p => occupied(p) && canonicalPath(p) !== canonicalPath(fallback)))
    throw new Error("Multiple OLIVE profile locations contain data. Set OLIVE_DATA_DIR explicitly; nothing was merged or moved.");
  return canonicalPath(occupied(legacy) ? legacy : occupied(current) ? current : fallback);
}
