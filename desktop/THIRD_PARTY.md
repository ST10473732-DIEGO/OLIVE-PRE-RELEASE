# Locally bundled dependencies

The exact dependency graph is in package-lock.json. Source packages retain their licence files in node_modules; packaging must include those notices alongside the Python artifact.

| Component | Licence | Role |
| --- | --- | --- |
| Electron | MIT; Chromium and Node notices included upstream | Desktop shell |
| React / React DOM | MIT | Presentation |
| qrcode.react 4.2.0 | ISC (includes QR encoder MIT notice) | Local rendering of public C2 pairing offers |
| Vite / React plugin | MIT | Build tooling |
| TypeScript | Apache-2.0 | Strict typing |
| Monaco Editor | MIT | Local source/diff editor and workers |
| xterm.js / FitAddon | MIT | Read-only output |
| Motion | MIT | Short presentation transitions |
| Radix Dialog | MIT | Accessible dialogs and focus management |
| Lucide | ISC | One frontend navigation icon family |
| React Markdown / remark-gfm | MIT | Inert Markdown and tables |
| Zod | MIT | Main-process contract validation |
| DOMPurify | Apache-2.0 OR MPL-2.0 | Monaco transitive sanitization |
| Playwright | Apache-2.0 | Isolated Electron tests |
| Vitest / ESLint / Prettier | MIT | Validation and formatting |

No proprietary fonts are distributed. The UI uses installed Segoe UI Variable/Segoe UI and system monospace fallbacks. The original olive source remains unchanged; existing derived assets are reused rather than redesigned.

DOMPurify is explicitly overridden to 3.4.15 because Monaco 0.56.0 pins an affected older release. The override is tested with the actual editor; the dependency audit reports zero known findings at this checkpoint. Audit results are time-specific, not a guarantee against all vulnerabilities.

## Studio developer tooling (release 3.5.1)

Provisioned by `scripts/provision_studio_tooling.py` into `.toolchains/studio/`
(git-ignored) and `requirements-studio.txt` into the repository virtual
environment. Nothing is installed system-wide; every download is verified
against a recorded SHA-256 digest before extraction. All are maintained,
official releases used at pinned versions.

| Component | Version | Licence | Provenance | Role |
| --- | --- | --- | --- | --- |
| OmniSharp-Roslyn (LSP mode) | 1.39.15 | MIT (.NET Foundation and Contributors) | GitHub release `omnisharp-win-x64-net6.0.zip`, sha256 `b03eb6b9…8658e8` | C# code intelligence |
| netcoredbg | 3.2.0-1092 | MIT (Samsung) | GitHub release `netcoredbg-win64.zip`, sha256 `3c410a45…9274a` | .NET debug adapter (DAP) |
| pywinpty | 3.0.5 | MIT | PyPI wheel | ConPTY-backed native terminals |
| debugpy | 1.8.21 | MIT | PyPI | Python debug adapter (DAP) |
| python-lsp-server (pylsp) | 1.15.0 | MIT | PyPI | Python code intelligence |

The .NET SDK and `dotnet` CLI are used from the user's existing installation
(detected, never installed or upgraded by OLIVE). Build, restore, test and
template operations run project-local (`obj/.olive-dotnet` DOTNET_CLI_HOME) and
follow the existing permission and approval policies. Language servers, debug
adapters and the terminal run as owned child processes of the Python runtime
under the approved-workspace and execution-policy environment; the renderer
reaches them only through validated bridge methods, never a raw process handle.
