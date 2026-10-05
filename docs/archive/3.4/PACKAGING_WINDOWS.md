# OLIVE 3.4 Windows packaging audit

## 3.5.1 Electron packaging checkpoint

M4 adds the canonical `olive.mail` Python modules using stdlib email/smtplib/imaplib
and the already-required Windows pywin32 Credential Manager binding. Include these
modules and pywin32 resources in the future self-contained backend. DOMPurify
3.4.15 is now a direct pinned frontend dependency (the version was already locked
as an override); its Apache-2.0/MPL-2.0 notices must ship with frontend notices.
`requirements-mail-test.txt` is test-only: aiosmtpd/atpublic/attrs and cryptography
for temporary TLS certificates are not production mail-server dependencies.
No installer, Windows shortcut, auto-update or default-launcher change is made by
M4. `desktop/backend-artifact` is still absent; clean-machine packaging remains
a release gate. No system certificate store or Windows registration was changed.

The prototype runs built local assets with the repository Python environment. Electron-builder is selected, but a production build requires a separately validated self-contained Python artifact outside ASAR. The packaging guard rejects a missing backend; no distributable/shortcut/installer or clean-machine test is claimed. The Qt default launcher is unchanged. See [desktop instructions](../../../desktop/README.md).

## Desktop-control dependencies and outstanding checks

Desktop control adds Windows-only pywinauto/comtypes/pywin32, psutil and an explicit
Pillow >=11.2 requirement for window-scoped capture. Preserve the existing Qt and Playwright
package collection. UIA helpers currently run the base Python interpreter with an explicit
virtual-environment site-directory bootstrap before `olive.desktop.uia_worker`; this keeps the
actual helper PID available for Windows foreground-permission handoff. A frozen
build needs an explicit worker entry point rather than relaunching its main GUI executable.
Test COM apartment setup, named-event stop propagation, DPI, native hotkey cleanup and capture
on a clean Windows account. Interactive Chrome/Edge must already be installed; there is no
automatic browser download. No clean-machine or installer certification is claimed.
Media control adds Windows-only PyWinRT Windows.Media.Control, Windows.Media,
Windows.Foundation and Windows.Foundation.Collections bindings (3.2.x). Collect their
runtime/native extension modules and test COM initialization on the background thread.
Clipboard and window control import pywin32 directly; package its DLLs and extensions.
The source environment passes real Chrome media-session pause/play/pause. Packaged playback
and clean-machine validation remain post-3.4 hardening. The default Windows audio-player
fixture did not expose a usable session; no codec was installed.

## Research dependencies

The source environment adds `beautifulsoup4>=4.13,<5`, `ddgs>=9,<10` and `playwright>=1.55,<2`. Tested versions are BeautifulSoup 4.15.0, DDGS 9.16.0 and Playwright 1.62.0. Collect their package data and DDGS/Playwright native dependencies, including the Playwright driver executable and JavaScript package, greenlet and the DDGS HTTP backend. Verify Windows Python architecture and wheel availability when freezing; import success alone is insufficient.

Rendered Research uses installed Microsoft Edge when available, with a fresh isolated context. Otherwise install Chromium manually with `.venv\Scripts\python.exe -m playwright install chromium`. OLIVE detects missing runtime support and does not download it automatically. A packaged build must choose a documented browser installation location and test offline startup, missing-browser diagnostics, subprocess teardown and the public-only proxy on a clean account. Research does not use Qt WebEngine or a WebChannel host bridge; Studio localhost preview retains its existing separate WebEngine packaging requirements.

No production installer or clean-machine certification is claimed. Browser engines are large external runtime components and need their own update/testing policy. Normal tests use offline fixtures; `scripts/research_live_smoke.py` is opt-in and requires existing Ollama models and public network access.

OLIVE now launches through PySide6 / Qt 6. The migration was tested from the local virtual environment on Windows; no production installer or clean-machine certification is claimed.

## Runtime and entry point

- `main.py` is the small Qt entry point; `run_olive.bat` continues to invoke it.
- PySide6 is constrained to `>=6.10,<6.12`; the tested environment uses 6.11.2 with matching Shiboken, Essentials and Addons packages.
- Flet is no longer a runtime requirement. Existing virtual environments may retain unused previously installed packages until recreated.
- The 3.5 development presentation uses local QML through QQuickWidget for Welcome,
  Home and navigation. Chat and docked Studio remain Widgets. There are no Monaco
  assets, Node build steps or runtime CDN assets.
- Ollama, optional Tesseract, Docker Desktop and project toolchains remain external. Nothing downloads a model or installs Docker automatically.

## Frozen-build collection

For 3.5 additionally collect `olive/ui_qt/experience/qml/*.qml`,
`olive/ui_qt/experience/tokens.json`, `assets/icons` (including its licence), and
`assets/branding/olive.ico` plus the `olive-*.png` assets. Retain their relative
layout under the distribution resource root. QML imports require QtQuick,
QtQuick.Controls (Basic style), QtQuick.Layouts and QtQuick.Shapes, as well as
QuickWidgets libraries. The Windows integration spike selected Qt's default
Direct3D11; do not force OpenGL. `experience/resources.py` supports a freezer's
`_MEIPASS` root and source-relative paths independently of the working directory.

Development QApplication/main-window/tray icons use the prepared olive ICO.
No executable, shortcut or installer has been rebuilt at M1; their icons and a
clean-machine install are **not verified**. Original artwork is preserved. The
transparent derivative's visual fidelity remains part of the M1 approval request.

Use the official PySide deployment tooling or a freezer with maintained PySide6 hooks. Lazy imports must still collect the Studio/preview modules. Inspect the resulting distribution rather than assuming import success guarantees a deployable build.

Collect the matching Qt libraries and plugin directories, including `platforms/qwindows.dll`, required image-format plugins, icon engines and any selected style plugins. Preserve the packaging tool's Qt directory structure; do not point a packaged build at another installed Qt distribution. Resolve executable/assets relative to the application package, not the working directory.

The localhost preview requires Qt WebEngineCore, WebEngineWidgets, WebChannel's Qt dependency where collected by Qt, `QtWebEngineProcess.exe`, the WebEngine resource files (including ICU and V8 data where supplied), and translation/locale resources. The application itself exposes no WebChannel bridge. WebEngine subprocess discovery must work from a path containing spaces. Keep its sandbox enabled. Inspect dependency collection because the installed Addons wheel contains more modules than Home uses.

Sources: [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/index.html), [pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html), [Qt WebEngine deployment](https://doc.qt.io/qt-6/qtwebengine-deploying.html).

## Data and security

User data remains under the existing OLIVE data directory. Existing JSON/SQLite repositories, legacy imports and ZIP backups remain compatible. `ui-qt-state.json` and the Qt runtime lock are separate from core data. Never package personal data, local models, developer paths or credentials.

Preview uses an off-the-record profile, rejects navigation/subresources outside the exact local origin, blocks downloads and permission requests, and exposes no Python host objects. Markdown blocks automatic resource loading. The native editor performs file operations through Python's existing authorized services.

## Acceptance before distributing an executable

1. Build and test clean Windows 10/11 accounts, including Unicode paths and paths with spaces.
2. Check Home, all feature windows, native dialogs, tray and keyboard navigation with Ollama absent and present.
3. Verify localhost preview, WebEngine subprocess/resources and clean profile teardown.
4. Verify missing optional OCR/Docker dependencies produce useful diagnostics and fail closed where required.
5. Exercise backup/restore, v2/v3 import, shutdown recovery, dirty-file prompts and corrupt/offscreen layouts.
6. Measure cold launch and distribution size; source-run Home construction ranged from approximately 0.43 to 1.34 seconds, not a packaged cold-start measurement.
7. Include third-party notices, review distribution requirements, then perform signing and clean-machine security checks.

No installer is produced by this migration. Source-run tests do not replace these distribution checks.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](../../architecture/legacy-dmdo-compatibility.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
