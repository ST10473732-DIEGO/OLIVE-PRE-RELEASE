# OLIVE on Linux (AppImage)

Status (2026-10-03): the AppImage can be built and was launched on the reference CachyOS
machine in an isolated profile. It is **not published**, and no clean-machine acceptance
has been done.

## Build

```bash
python packaging/backend/build_backend.py
cd desktop && npm ci && npm run build && npm run package:linux   # dist/OLIVE-1.0.0.AppImage
```

The package needs no Python, Node, npm or Git on the user's machine.

## Running

```bash
chmod +x OLIVE-1.0.0.AppImage && ./OLIVE-1.0.0.AppImage
```

- **FUSE.** The AppImage runtime (electron-builder's appimage 12.0.1) mounts itself with
  `libfuse.so.2`. Distributions that ship only FUSE 3 need their `fuse2`/`libfuse2`
  package. Without it, run `APPIMAGE_EXTRACT_AND_RUN=1 ./OLIVE-1.0.0.AppImage`, which
  extracts to a temporary folder first.
- **Chromium sandbox.** The embedded `olive.desktop` does **not** pass `--no-sandbox`.
  The SUID `chrome-sandbox` helper cannot work from an AppImage mount, so Chromium relies
  on unprivileged user namespaces. If they are unavailable (`unshare -Ur true` fails, for
  example on Ubuntu 24.04+ with AppArmor's userns restriction), electron-builder's AppRun
  starts Electron with `--no-sandbox`. That is electron-builder behaviour, not an OLIVE
  setting. The safer remedy is an AppArmor profile for the AppImage or enabling user
  namespaces. Whether 1.0 should refuse to start instead is an open decision.
- **Desktop entry.** The AppImage carries `olive.desktop`: Name OLIVE, icon `olive`,
  `StartupWMClass=olive`. AppImage integration tools install it. When desktop control
  first needs the KDE portal, OLIVE writes the hidden `local.dmdo.desktop.desktop`
  (`NoDisplay=true`) to `~/.local/share/applications`.
- **Launch at login** points at the AppImage file (`$APPIMAGE`), never at the temporary
  mount.

## Where OLIVE writes

Nothing is written inside the AppImage.

- **Profile:** an existing `~/.dmdo` or `~/.olive`, otherwise `$XDG_DATA_HOME/olive`.
- **Runtimes:** `$XDG_DATA_HOME/olive/runtime`.
- **Models:** `$XDG_DATA_HOME/olive/models`.

Existing source-run machines keep their runtimes in place: the packaged app adopts them
into `runtimes.json`.

## Not done yet

Model and runtime download (first-run setup), clean-machine acceptance on other
distributions, AppImage update channel, signing of SHA256SUMS.
