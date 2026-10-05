# Installing OLIVE

**OLIVE 1.0 is released.** Downloads: [OLIVE 1.0 release](https://github.com/ST10473732-DIEGO/get-olive/releases/tag/olive-1.0) (Linux x86_64 AppImage,
supported; Windows x86_64 installer, unsigned preview). The Linux Creator image runtime is
published separately ([creator-runtime-1.0.0-ecdb6702](https://github.com/ST10473732-DIEGO/get-olive/releases/tag/creator-runtime-1.0.0-ecdb6702)); setup downloads it when you
choose Creator. macOS and iPhone are not part of OLIVE 1.0. OLIVE also still runs from a source
checkout ([development](../development/README.md)); packaging is described in
[architecture](../architecture/packaging.md).

Per platform: [Linux AppImage](linux.md) · [Windows installer](windows.md) · [macOS DMG](macos.md).

## Platform status

| Platform | In OLIVE 1.0 | Today | Remaining work |
| --- | --- | --- | --- |
| Linux desktop | Yes, supported | Published AppImage (`OLIVE-1.0.0-linux-x86_64.AppImage`) with a self-contained backend and first-run setup; also runs from source with `run_olive.sh`. Desktop Navigation and control are KDE-only | Clean-machine acceptance on other distributions |
| Windows desktop | Yes, preview | Published per-user installer (`OLIVE-Setup-1.0.0-windows-x86_64.exe`), unsigned, so SmartScreen warns. Tested by hand on a Windows PC before release and launch-tested in release CI. No Creator engine; Ollama is installed separately. Also runs from source (`setup_windows.bat`, then `npm ci` and `npm run build` in `desktop/`, then `run_olive.bat`) | Code signing, a Windows Creator engine, setup-managed Ollama, VIDEO/AUDIO acceptance |
| macOS desktop | No | **Not supported yet.** Foundations exist (Keychain vault, `open`, runtime paths and process launching, unsigned DMG config, `.icns`), but nothing has been validated on a Mac | Apple Silicon backend and DMG build, physical validation, Developer ID signing and notarization (owner credentials) |
| iPhone companion | No | Developer install through Xcode ([iPhone](../mobile/README.md)) | TestFlight/App Store distribution, final bundle ID and version, in a dedicated iOS release phase |

## Models

OLIVE never downloads a model by itself. Chat modes report *Needs setup* until
their model or engine is installed. First-run setup offers Core, Creator and Complete
packages. A model enters a package only once its source, checksum and licence are recorded
and the release approves it; until then it is **not yet distributable**. That currently
applies to the locally built UNCENSORED models and to the FLUX.2 [klein] 9B, LTX video and
Qwen-Image files (FLUX.2 [klein] 4B is offered with the Linux Creator package).

## Data

Your data lives in your profile: `~/.olive` (Linux: `$XDG_DATA_HOME/olive`), or an
existing `~/.dmdo` profile, which is reused in place. OLIVE-owned runtimes and models live
in a per-user data folder (`$XDG_DATA_HOME/olive`, `%LOCALAPPDATA%\OLIVE` or
`~/Library/Application Support/OLIVE`), never inside the installed application.
Installing, updating or removing OLIVE never deletes either.
