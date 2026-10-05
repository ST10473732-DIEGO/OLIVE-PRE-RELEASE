# Installing OLIVE

**No OLIVE 1.0 installer has been published yet.** Packaging is being prepared on the
`release/olive-1.0` branch ([architecture](../architecture/packaging.md)). Until then,
OLIVE runs from a source checkout ([development](../development/README.md)).

Per platform: [Linux AppImage](linux.md) · [Windows installer](windows.md) · [macOS DMG](macos.md).

## Platform status

| Platform | OLIVE 1.0 target | Today | Remaining work |
| --- | --- | --- | --- |
| Linux desktop | Yes | Runs from source with `run_olive.sh`. An AppImage with a self-contained backend builds and starts in an isolated profile (not published). Desktop Navigation and control are KDE-only | First-run model setup, clean-machine acceptance on other distributions |
| Windows desktop | Yes | Runs from source (`setup_windows.bat`, then `npm ci` and `npm run build` in `desktop/`, then `run_olive.bat`). The per-user NSIS installer is configured but not built. The last full Windows acceptance predates Connect World, Notes, Draw and Chat media | Windows backend build, installer build, current-tree acceptance including VIDEO/AUDIO. Builds are unsigned at first, so SmartScreen will warn |
| macOS desktop | Yes | **Not supported yet.** Foundations exist (Keychain vault, `open`, runtime paths and process launching, unsigned DMG config, `.icns`), but nothing has been validated on a Mac | Apple Silicon backend and DMG build, physical validation, Developer ID signing and notarization (owner credentials) |
| iPhone companion | Yes | Developer install through Xcode ([iPhone](../mobile/README.md)) | TestFlight/App Store distribution, final bundle ID and version, in a dedicated iOS release phase |

## Models

OLIVE never downloads a model by itself. Chat modes report *Needs setup* until
their model or engine is installed. The planned first-run setup will offer
Core, Creator and Complete model sets. A model enters a set only once its source,
checksum and licence are recorded; until then it is **not yet distributable**.
That currently applies to the locally built UNCENSORED models and to the
FLUX.2 Klein, LTX video and Qwen-Image files.

## Data

Your data lives in your profile: `~/.olive` (Linux: `$XDG_DATA_HOME/olive`), or an
existing `~/.dmdo` profile, which is reused in place. OLIVE-owned runtimes and models live
in a per-user data folder (`$XDG_DATA_HOME/olive`, `%LOCALAPPDATA%\OLIVE` or
`~/Library/Application Support/OLIVE`), never inside the installed application.
Installing, updating or removing OLIVE never deletes either.
