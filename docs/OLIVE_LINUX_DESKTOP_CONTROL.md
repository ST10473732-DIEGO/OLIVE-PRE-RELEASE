# Linux Desktop Control implementation ledger

Work in progress on `feature/olive-desktop-control-linux-v1`.
BASELINE_HEAD: `2df73b31ca11374978363a8f9d9c34ab052a74a4`.
Historical DESIGN_BASE: `50003790c42aff620d63d664dff89c0338347cab`.
The starting worktree was clean; both ancestry and the inherited wizard exception
were verified. No model mapping, user profile, or Connect contract is migrated.

Implementation proceeds in runnable phases:

1. Reproduce inherited failures; record immutable V3 frozen bytes.
2. Add user-session portal observation, accessibility and emergency Stop.
3. Add bounded input and app discovery with current focus/geometry checks.
4. Bind adaptive proposals to trusted, finite direct-user task authority.
5. Exercise owned fixtures, then separately consented real desktop workflows.
6. Repair demonstrated GO/backend defects and approved renderer exceptions.
7. Run full regression; distinguish host, fixture and pending hosted evidence.

No desktop capture or input is authorized merely by capability discovery.
Live acceptance requires the user's session approval and a demonstrated global
Stop. Compositor dialogs are handled by the human. No persistent restore grants,
network automation service, root input, KWin scripting or browser debug ports.

The native helper uses the installed distribution GObject libraries in a separate
user process. OLIVE itself and its tests continue to use the project venv.
No packages have been installed for this milestone.

## Initial host observation (2026-09-23)

KDE Wayland, KWin 6.7.5; application portal 1.22.1 and KDE backend 6.7.5.
Read-only introspection exposes RemoteDesktop v2, ScreenCast v5 and
GlobalShortcuts v2. PipeWire 1.6.9, libei 1.6.0, AT-SPI 2.60.7 and GStreamer
1.28.7 are installed. This is API availability, not live input acceptance.
Three active displays: two 1920×1080 at scale 1, and 2560×1600 at scale 1.25.
Firefox 156.0.1, Kate and Dolphin 26.08.1 are installed; Discord is present.

Frozen V3 bytes are recorded separately in
`docs/evidence/linux-desktop-frozen.json`. The original V2 manifest/checker is
unchanged. Any subsequent approved exception must be recorded separately.

## Primary references

- [RemoteDesktop application portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
- [ScreenCast application portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
- [GlobalShortcuts application portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)
- [libei](https://libinput.pages.freedesktop.org/libei/api/)
- [AT-SPI](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/)
- [Electron WebContents](https://www.electronjs.org/docs/latest/api/web-contents)
- [Discord account-automation policy](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots)

Discord prohibits ordinary-account automation outside its OAuth2/bot API and
warns of account termination. There is no documented mouse/keyboard exemption.
A generic GUI route is not official Discord support or protection from bans.
Real sends require the user to choose account, destination and content with
awareness of this risk. No real message has been sent for this milestone.
