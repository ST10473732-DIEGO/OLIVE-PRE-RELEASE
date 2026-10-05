# Desktop packaging architecture

Status: OLIVE 1.0 PASS 2B (2026-10-03). This is a packaging *foundation*. No installer
has been published. Linux (AppImage) is the only package built and launched so far.

## Pieces

| Piece | Where | Notes |
| --- | --- | --- |
| Electron shell | `desktop/` → `app.asar` | Only `out/electron`, `out/renderer` and `package.json` |
| Python backend artefact | `packaging/backend/build_backend.py` → `desktop/backend-artifact/` → `resources/backend` | Relocatable CPython (python-build-standalone), hash-locked wheels, `olive/` |
| Legal notices | `resources/legal/` | `LICENSE`, `THIRD_PARTY_NOTICES.md`, `desktop/THIRD_PARTY.md`; Electron adds its own `LICENSE*` |
| Icons | `assets/branding/` | `.ico` (Windows), `.icns` (macOS, `packaging/icons/make_icons.py`), PNG (Linux) |
| Runtime manifest | `olive/runtime_manifest/1.0.0.json` (inside the backend) | What first-run setup may install; see [first-run-setup.md](first-run-setup.md) |
| Linux entries | `packaging/linux/*.in` = `olive/services/linux_desktop_entries.py` | Visible `olive.desktop`, hidden `local.dmdo.desktop.desktop` |
| Windows installer script | `packaging/electron/installer.nsh` | Optional desktop shortcut; never deletes data |
| macOS entitlements | `packaging/electron/entitlements.mac*.plist` | Hardened-runtime placeholders; not signed |

Build per OS on that OS (cross builds are refused):

```bash
python packaging/backend/build_backend.py     # backend for this OS (verifies downloads, smoke-tests)
cd desktop && npm ci && npm run build
npm run package:linux                          # OLIVE-1.0.0.AppImage
npm run package:win                            # OLIVE-Setup-1.0.0.exe   (on Windows)
npm run package:mac                            # OLIVE-1.0.0-arm64.dmg   (on Apple Silicon)
```

`desktop/scripts/require-backend.cjs` (electron-builder `beforePack`) refuses to package
without a backend whose `olive-backend.json` matches the target platform and architecture,
whose interpreter sits where that platform expects it, and which contains no Qt fallback,
`dmdo` package, Playwright or pip.

## How the packaged app starts its backend

`desktop/electron/platform.ts`:

- interpreter: `resources/backend/bin/python3` (Linux, macOS) or `resources/backend/python.exe`;
- arguments: `-s -P -u -m olive.bridge`. `-P` means the working directory is never on
  `sys.path`; `olive` is found through `site-packages/olive-backend.pth`;
- environment: `PYTHONHOME`, `PYTHONPATH`, `PYTHONSTARTUP` and `PYTHONUSERBASE` are removed,
  `PYTHONDONTWRITEBYTECODE=1` (byte-code is precompiled with unchecked hashes),
  `OLIVE_DATA_DIR` = the resolved profile, `OLIVE_APP_EXECUTABLE` = `$APPIMAGE` or the
  installed executable, `OLIVE_START_OLLAMA=1` unless set.

The backend recognises a packaged install by `olive-backend.json` next to `olive/`
(`olive.app_paths.packaged()`).

## Path authority

`olive/app_paths.py` is the single authority for locations outside the profile. The profile
itself keeps `olive.identity.resolve_profile` (unchanged).

| What | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Profile | existing `~/.dmdo` or `~/.olive`, else `$XDG_DATA_HOME/olive` | `%USERPROFILE%\.olive` (or `.dmdo`) | `~/.olive` (or `.dmdo`) |
| Per-user data root | `$XDG_DATA_HOME/olive` (default `~/.local/share/olive`) | `%LOCALAPPDATA%\OLIVE` | `~/Library/Application Support/OLIVE` |
| Runtimes | `<root>/runtime` | `<root>\runtime` | `<root>/runtime` |
| Media models | `<root>/models` | `<root>\models` | `<root>/models` |
| Studio toolchains | `<root>/toolchains` (source checkouts also read `.toolchains/`) | same | same |
| Start locks | `$XDG_RUNTIME_DIR`, else `~/.cache/olive` | `<root>\locks` | `<root>/locks` |
| Temporary jobs | OS temp, or profile staging folders | same | same |
| Electron shell state | `<profile>/electron-shell` | same | same |

Writable state never goes into Program Files, the AppImage mount, the `.app` bundle,
`resources/backend` or the repository. Specific fixes in PASS 2B:

- Studio toolchains (`olive/studio_tooling/toolchain.py`) look in the per-user root first.
  The repository's `.toolchains` is read only in a source checkout.
- User projects without their own virtual environment never get the bundled interpreter.
  They use the user's `python3`/`python` instead (`BuildAndTestService.python_executable`),
  so nothing can `pip install` into the installation.
- Linux launch-at-login starts the AppImage file (`$APPIMAGE`), never its temporary mount
  or `run_olive.sh`.
- The Windows media script uses `%LOCALAPPDATA%\OLIVE\runtime` and its logs live there,
  not in `<repo>\.media-runtime`.
- Notification and tray icons are read from `resources/` in a package.

On Linux these are the locations `run_olive.sh` has always used, so an existing machine
keeps its runtimes and models where they are.

## Runtime discovery (`olive/services/runtime_discovery.py`)

Runtimes: `ollama`, `comfy` (image, :8188), `video_comfy` (:8190), `voicestudio` (:3900),
`media_models`. Each one resolves in a fixed order:

1. **Environment override.** These are developer/admin variables:
   - `OLIVE_OLLAMA_EXECUTABLE`;
   - `OLIVE_COMFY_ROOT` and `OLIVE_COMFY_PYTHON`;
   - `OLIVE_VIDEO_COMFY_ROOT` and `OLIVE_VIDEO_COMFY_PYTHON`;
   - `OLIVE_VOICESTUDIO_ROOT` and `OLIVE_VOICESTUDIO_URL`;
   - `OLIVE_MEDIA_MODELS`.

   An override is authoritative while it is set. An invalid one reports
   `invalid_override`. An override that differs from the saved choice reports
   `overrides_settings`.
2. **Persisted choice** (`<profile>/runtimes.json`, schema `olive-runtimes/1`). It holds
   paths and provenance only, never credentials. A stale path reports `stale` and lists
   what discovery would find in `also_found`. OLIVE never falls back to another
   installation on its own.
3. **Discovery.** Tiers are checked in this order:
   - OLIVE-owned folders under the runtime root;
   - in a source checkout only, the repository's `.toolchains` and `.media-runtime`;
   - for Ollama only, a system installation: `PATH`, plus on macOS
     `/Applications/Ollama.app`, Homebrew and `/usr/local`, and on Windows
     `%LOCALAPPDATA%\Programs\Ollama`.

   The first tier with a match wins. Two different matches in one tier are a
   `conflict`, which needs a choice (`RuntimeDiscovery.choose`). An unambiguous
   OLIVE-owned match is **adopted**: it is written to `runtimes.json` in place, and
   nothing is moved or copied. Repository and system matches are used live and never
   adopted.
4. **Nothing found.** The state is `needs_setup` with reason `missing`.

An unreadable `runtimes.json` is reported (`unreadable_settings`) and never overwritten.
`runtime.runtimes` (bridge, read-only) returns the states, paths, provenance and
`validated_on_platform` for each runtime.

`run_olive.sh` no longer exports runtime paths, so source launches use the same discovery
as a packaged app. It still prepends the OLIVE-owned Ollama to `PATH` and keeps
`OLLAMA_MODELS`.

## Runtime lifecycle (`olive/runtime/processes.py`)

| | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Owned process | private supervisor, subreaper (unchanged) | kill-on-close Job Object, no console | new session; process group signalled |
| Start lock | `fcntl.flock` | `msvcrt.locking` | `fcntl.flock` |
| Ollama | validated | prepared (`ollama.exe serve` from discovery) | prepared (`Ollama.app` binary or Homebrew) |
| ComfyUI image/video | validated | prepared; portable layout gets `-s --windows-standalone-build`; video keeps `--whitelist-custom-nodes ComfyUI-GGUF-Loader` | prepared, **not validated** |
| VoiceStudio | validated | prepared (`.venv\Scripts\python.exe`) | prepared, **not validated** |

A runtime that is already listening is reused and never stopped. Only processes OLIVE
started are stopped.

## Platform services

- Credentials: Windows Credential Manager (`DMDO/` namespace, unchanged), Linux Secret
  Service, **macOS Keychain** (`olive/services/macos_credentials.py`, through keyring's
  macOS backend, which uses the Security framework; service `OLIVE`; no plaintext
  fallback).
- `open_path`: `os.startfile`, `xdg-open`, `/usr/bin/open` (absolute path argument).
