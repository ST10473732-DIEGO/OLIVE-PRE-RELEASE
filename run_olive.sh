#!/usr/bin/env bash
# Native development launcher. Electron owns the private Python bridge and shutdown.
set -Eeuo pipefail
trap 'printf "OLIVE launch failed at line %s (exit %s).\n" "$LINENO" "$?" >&2' ERR
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$root"
umask 077
if [[ "${1:-}" == --enable-startup || "${1:-}" == --disable-startup ]]; then
  action="${1#--}"
  exec python3 -m olive.services.linux_startup "${action%-startup}"
fi
if [[ -x "$root/.toolchains/node/bin/node" ]]; then
  export PATH="$root/.toolchains/node/bin:$PATH"
fi
if [[ -z "${DOTNET_ROOT:-}" && -x "$root/.toolchains/dotnet/dotnet" ]]; then
  export DOTNET_ROOT="$root/.toolchains/dotnet"
  export PATH="$DOTNET_ROOT:$PATH"
fi
# Prefer the persistent OLIVE-managed Ollama runtime.
# Fall back to a repository-local runtime for development/legacy clones.
olive_ollama_dir=""
if [[ -x "$HOME/.local/share/olive/runtime/ollama/bin/ollama" ]]; then
  olive_ollama_dir="$HOME/.local/share/olive/runtime/ollama/bin"
elif [[ -x "$root/.toolchains/ollama/bin/ollama" ]]; then
  olive_ollama_dir="$root/.toolchains/ollama/bin"
fi

if [[ -n "$olive_ollama_dir" ]]; then
  export PATH="$olive_ollama_dir:$PATH"
fi

# Reuse the user's existing Ollama model library.
if [[ -d "$HOME/.ollama/models" ]]; then
  export OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
fi
# OLIVE-owned runtimes (ComfyUI image/video, VoiceStudio, the image model store)
# are located by the backend itself (olive/services/runtime_discovery.py) from the
# per-user runtime folder and <profile>/runtimes.json, exactly as in a packaged
# app. OLIVE_COMFY_ROOT/_PYTHON, OLIVE_VIDEO_COMFY_ROOT/_PYTHON,
# OLIVE_VOICESTUDIO_ROOT/_URL and OLIVE_MEDIA_MODELS remain optional overrides.
for tool in python3 node npm; do
  command -v "$tool" >/dev/null || { printf 'Missing dependency: %s. Install it before launching OLIVE.\n' "$tool" >&2; exit 1; }
done
node -e 'const [major,minor]=process.versions.node.split(".").map(Number); if (major<22 || (major===22 && minor<12)) { console.error("OLIVE requires Node 22.12+ or a newer supported LTS release."); process.exit(1); }'
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
# Refresh only when declared dependencies change. Failed installs never write the stamp.
fingerprint="$(cat requirements.txt requirements-personal.txt | sha256sum | cut -d ' ' -f 1)"
if [[ ! -f .venv/olive-linux-requirements.sha256 ]] || [[ "$(cat .venv/olive-linux-requirements.sha256)" != "$fingerprint" ]]; then
  .venv/bin/python -m pip install -r requirements.txt
  printf '%s\n' "$fingerprint" > .venv/olive-linux-requirements.sha256
fi
export OLIVE_PYTHON="${OLIVE_PYTHON:-${DMDO_PYTHON:-$root/.venv/bin/python}}"
# Share SDK/JDK resolution with Studio even when launched outside a login shell.
mapfile -t olive_tools < <(.venv/bin/python -c 'import os; from olive.studio_tooling.toolchain import developer_environment; e=developer_environment(dict(os.environ)); print(e.get("PATH", "")); print(e.get("DOTNET_ROOT", "")); print(e.get("JAVA_HOME", ""))')
export PATH="${olive_tools[0]}"
if [[ -n "${olive_tools[1]}" ]]; then export DOTNET_ROOT="${olive_tools[1]}"; fi
if [[ -n "${olive_tools[2]}" ]]; then export JAVA_HOME="${olive_tools[2]}"; fi
# developer_environment may rebuild PATH, so ensure the managed Ollama
# runtime remains discoverable by the backend.
if [[ -n "${olive_ollama_dir:-}" ]]; then
  export PATH="$olive_ollama_dir:$PATH"
fi
# The shared resolver preserves configured/legacy profiles and rejects conflicts.
export OLIVE_DATA_DIR
OLIVE_DATA_DIR="$(.venv/bin/python -c 'from olive.identity import resolve_profile; print(resolve_profile())')"
if [[ ! -d desktop/node_modules ]]; then
  npm ci --prefix desktop
fi
if [[ ! -x desktop/node_modules/electron/dist/electron ]]; then
  node desktop/node_modules/electron/install.js
fi
npm run build --prefix desktop
# The backend may start one loopback-only Ollama process; an existing server is reused.
export OLIVE_START_OLLAMA="${OLIVE_START_OLLAMA:-1}"
# exec preserves the Electron exit status and avoids an extra launcher process.
exec desktop/node_modules/electron/dist/electron "$root/desktop" "$@"
