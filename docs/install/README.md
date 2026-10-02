# Installing OLIVE

**No OLIVE 1.0 installer has been published yet.** Installers are being prepared
on the `release/olive-1.0` branch. Until then, OLIVE runs from a source checkout
([development](../development/README.md)).

## Platform status

| Platform | OLIVE 1.0 target | Today | Remaining work |
| --- | --- | --- | --- |
| Linux desktop | Yes | Runs from source with `run_olive.sh`. Verified on the reference CachyOS/KDE machine; Desktop Navigation and control are KDE-only | Self-contained backend, AppImage (or equivalent) package, desktop entry `olive.desktop`, first-run model setup, clean-machine acceptance |
| Windows desktop | Yes | Runs from source (`setup_windows.bat`, then `npm ci` and `npm run build` in `desktop/`, then `run_olive.bat`). The last full Windows acceptance predates Connect World, Notes, Draw and Chat media | Self-contained backend, installer, Windows media runtime wiring (VIDEO, AUDIO), current-tree acceptance. The first installer may be unsigned, so SmartScreen will warn |
| macOS desktop | Yes | **Not supported yet** | Keychain credential backend (Connect, World, Mail and Discord need it), opening files with `open`, Ollama/ComfyUI lifecycle on macOS, a launcher (`run_olive.sh` needs bash 4 and `sha256sum`), app bundle, icon, signing and notarization |
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
existing `~/.dmdo` profile, which is reused in place. Installing, updating or
removing OLIVE must never delete it.
