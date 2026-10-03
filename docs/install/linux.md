# OLIVE on Linux (AppImage)

Status (2026-10-03): the AppImage can be built and was launched on the reference CachyOS
machine in an isolated profile. It is **not published**, and no clean-machine acceptance
has been done. The checklist for Ubuntu 24.04, Fedora and Debian is in
[linux-clean-machine-acceptance.md](linux-clean-machine-acceptance.md).

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
- **Chromium sandbox.** See [Chromium sandbox](#chromium-sandbox) below. OLIVE never starts
  without it.
- **Desktop entry.** The AppImage carries `olive.desktop`: Name OLIVE, icon `olive`,
  `StartupWMClass=olive`. AppImage integration tools install it. When desktop control
  first needs the KDE portal, OLIVE writes the hidden `local.dmdo.desktop.desktop`
  (`NoDisplay=true`) to `~/.local/share/applications`.
- **Launch at login** points at the AppImage file (`$APPIMAGE`), never at the temporary
  mount.

## Chromium sandbox

OLIVE isolates web content with Chromium's sandbox. Inside an AppImage the SUID
`chrome-sandbox` helper cannot work, so the sandbox needs **unprivileged user namespaces**.

When they are unavailable (`unshare -Ur true` fails), electron-builder's AppImage launcher adds
`--no-sandbox`. **OLIVE refuses to start in that case** and shows "OLIVE could not start safely"
with these instructions. It never weakens the sandbox by itself.

### Ubuntu 24.04 and later (AppArmor)

Ubuntu restricts unprivileged user namespaces to programs that have an AppArmor profile allowing
them (`kernel.apparmor_restrict_unprivileged_userns=1`). An AppImage mounts at a different
temporary path on every start, so give OLIVE a fixed path first:

```bash
./OLIVE-1.0.0.AppImage --appimage-extract          # creates ./squashfs-root
mkdir -p ~/Applications && mv squashfs-root ~/Applications/OLIVE
```

Then create `/etc/apparmor.d/olive` (replace `YOU` with your user name):

```
abi <abi/4.0>,
include <tunables/global>

profile olive /home/YOU/Applications/OLIVE/olive flags=(unconfined) {
  userns,

  include if exists <local/olive>
}
```

Load it and start OLIVE's executable from that folder directly (not `AppRun`: its own
`unshare -Ur true` probe is not covered by the profile and would still add `--no-sandbox`):

```bash
sudo apparmor_parser -r /etc/apparmor.d/olive
~/Applications/OLIVE/olive
```

This grants user namespaces to that one executable only. **[Not yet validated on Ubuntu 24.04;
part of clean-machine acceptance.]** The system-wide alternative,
`sudo sysctl kernel.apparmor_restrict_unprivileged_userns=0`, removes the restriction for every
program; it is an administrator's decision, and OLIVE does not recommend it.

### Other distributions

Unprivileged user namespaces must be enabled:

- Debian (older kernels): `sudo sysctl kernel.unprivileged_userns_clone=1`;
- any distribution: `user.max_user_namespaces` must be greater than 0
  (`sysctl user.max_user_namespaces`);
- hardened kernels (for example `linux-hardened`) may disable them on purpose; use the
  distribution's documented setting.

Make a setting permanent with a file in `/etc/sysctl.d/`.

### Developer-only override

For development only, `OLIVE_UNSAFE_ALLOW_NO_SANDBOX_DEVELOPER_ONLY=1` lets OLIVE run when it was
started with `--no-sandbox`. OLIVE logs a warning. Never set it on a machine you use for real
work, and never in a launcher or desktop entry.

## Where OLIVE writes

Nothing is written inside the AppImage.

- **Profile:** an existing `~/.dmdo` or `~/.olive`, otherwise `$XDG_DATA_HOME/olive`.
- **Runtimes:** `$XDG_DATA_HOME/olive/runtime`.
- **Models:** `$XDG_DATA_HOME/olive/models`.

Existing source-run machines keep their runtimes in place: the packaged app adopts them
into `runtimes.json`.

## First-run setup

On a new profile OLIVE opens its setup wizard: name, system check, package (Core, Creator,
Complete), runtimes, models, verification, OLIVE Connect and Connect World. Downloads come only
from the pinned runtime manifest (`olive/runtime_manifest/1.0.0.json`), are verified by SHA-256 or
registry digest, and land in `$XDG_DATA_HOME/olive`. Existing installations are found and reused,
never replaced. See `docs/architecture/first-run-setup.md`.

## Not done yet

Clean-machine acceptance on other distributions, AppImage update channel, signing of SHA256SUMS,
and the Creator runtimes (image, video and audio engines), which are not installable from setup in
this build.
