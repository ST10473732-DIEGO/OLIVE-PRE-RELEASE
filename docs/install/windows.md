# OLIVE on Windows (NSIS installer)

Status (2026-10-03): configuration only. `OLIVE-Setup-1.0.0.exe` has **not been built**.
It needs the Windows backend, which can only be built on Windows. Nothing on Windows is
validated on the current tree, including VIDEO and AUDIO.

## Build (on Windows x64)

```powershell
py -3 packaging\backend\build_backend.py
cd desktop; npm ci; npm run build; npm run package:win   # dist\OLIVE-Setup-1.0.0.exe
```

## Installer behaviour

- **Install scope.** Per-user, with no elevation, into `%LOCALAPPDATA%\Programs\olive-desktop`
  (electron-builder names the folder after the `desktop/package.json` package name; confirmed by
  the release CI smoke job on 2026-10-04). The directory cannot be changed, so it can never
  be pointed at a data folder that the uninstaller would then remove.
- **Shortcuts.** The installer always creates a Start Menu **OLIVE** entry. It asks once
  whether to add a desktop shortcut; silent installs and updates never add one.
- **Identity.** The app ID stays `local.dmdo.desktop`, for taskbar, notification and
  upgrade continuity.
- **Uninstall** removes the application files and its shortcuts only. It never removes
  the profile (`%USERPROFILE%\.olive` or `.dmdo`), runtimes or models
  (`%LOCALAPPDATA%\OLIVE`).
- **Unsigned dev/RC builds.** No signing certificate is configured. Windows SmartScreen
  shows "Windows protected your PC". Choose *More info → Run anyway* only for builds you
  made or received directly from the OLIVE owner. Signing is a later owner decision.

## Runtimes on Windows

Discovery looks in `%LOCALAPPDATA%\OLIVE\runtime`:

| Runtime | Location |
| --- | --- |
| Ollama | `ollama\ollama.exe`, then the official install in `%LOCALAPPDATA%\Programs\Ollama` |
| Image ComfyUI | `comfy\ComfyUI_windows_portable` (portable) or `comfy\ComfyUI` + `comfy-venv` |
| Video ComfyUI | `video-comfy\...`; the LTX GGUF loader stays whitelisted |
| VoiceStudio | `voicestudio`, using `.venv\Scripts\python.exe` |

Source checkouts also find the older `.media-runtime\ComfyUI_windows_portable`. Missing
runtimes show *Needs setup*. `scripts\media_engine.ps1 -Kind Image|Video` is a manual
developer tool that uses the same locations.

## Known gaps

- Studio terminal: `pywinpty` 3.0.5 is part of the Windows backend (core dependency). Not yet validated on a Windows build.
- Desktop Control's browser: Playwright is not in the backend yet; it reports that clearly.
- No current-tree Windows acceptance.
- Owned Ollama, ComfyUI and VoiceStudio starts are not validated.
