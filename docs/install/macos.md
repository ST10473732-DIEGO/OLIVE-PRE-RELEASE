# OLIVE on macOS (DMG)

Status (2026-10-03): **foundations only**. No DMG has been built. Nothing is signed or
notarized. Nothing on macOS has been validated on a Mac. Intel Macs are not supported
(the bundled `cryptography` has no x86_64 macOS wheel).

## Build (on Apple Silicon)

```bash
python3 packaging/backend/build_backend.py              # macos-arm64 backend
cd desktop && npm ci && npm run build && npm run package:mac   # dist/OLIVE-1.0.0-arm64.dmg (unsigned)
```

An unsigned development DMG opens only after the user explicitly allows it in
*System Settings → Privacy & Security*. It is not distributable.

## Implemented foundations

- **Data:** the profile is in `~/.olive` (or `~/.dmdo`); runtimes and models are in
  `~/Library/Application Support/OLIVE`.
- **Credentials:** macOS Keychain, through keyring's macOS backend (Security
  framework), with service `OLIVE`. There is no plaintext fallback.
- **Opening files:** `/usr/bin/open`.
- **Processes:** owned runtimes start in their own session and are stopped through their
  process group.
- **Ollama:** found in `~/Library/Application Support/OLIVE/runtime/ollama`,
  `/Applications/Ollama.app`, Homebrew or `/usr/local`.
- **Truthful states:**
  - Creator runtimes (ComfyUI, VoiceStudio) report `validated_on_platform: false`;
  - the Studio terminal reports "not available on macOS in this build yet";
  - Windows-only features name macOS.

## Owner requirements before a distributable build

1. Apple Developer Program membership and a **Developer ID Application** certificate.
2. Notarization credentials (App Store Connect API key, or Apple ID with an app-specific
   password and Team ID).
3. Sign every Mach-O in `resources/backend` (the Python interpreter, `.so` and `.dylib`
   files) with the hardened runtime. Review `packaging/electron/entitlements.mac.plist`,
   especially `disable-library-validation`.
4. Set `mac.identity` and `mac.notarize` in `desktop/package.json`. Neither is set today.

## Physical validation checklist (on a Mac)

- [ ] `build_backend.py` completes, including its smoke test.
- [ ] The DMG builds; the app starts from `/Applications` with no Python, Node or Git
      installed.
- [ ] `runtime.runtimes` shows Needs setup for missing runtimes, and Ollama is found when
      Ollama.app is installed.
- [ ] Keychain: Connect pairing, World and Mail credentials survive a restart. Locking the
      keychain shows the macOS message.
- [ ] Opening a file or folder from OLIVE uses Finder or its default app.
- [ ] Quitting OLIVE stops only processes OLIVE started.
- [ ] Nothing is written inside `OLIVE.app`.
- [ ] Only then: Creator (ComfyUI, VoiceStudio) on Apple Silicon.
