# OLIVE documentation

OLIVE (formerly DMDO) is a local-first desktop AI assistant with an iPhone
companion. Ollama is the default inference provider. This index covers the
source repository on the `release/olive-1.0` branch.

**Release status.** OLIVE 1.0 installers are still being prepared. Today OLIVE
runs from a source checkout (see [development](development/README.md)). OLIVE 1.0
targets Linux, Windows and macOS desktops plus the iPhone companion; macOS desktop
support has open implementation work ([install status](install/README.md)).

## Start here

| Section | Contents |
| --- | --- |
| [Getting started](getting-started/README.md) | What OLIVE is and what runs where |
| [Install](install/README.md) | Installer status per platform; running from source |
| [iPhone](mobile/README.md) | The companion app, pairing and current distribution |
| [Troubleshooting](troubleshooting/README.md) | Common "needs setup" and connection states |

## Features

| Page | Contents |
| --- | --- |
| [Chat modes](features/chat-modes.md) | FAST, NORMAL, MAX, UNCENSORED, NOW, DEEP, REIMAGINE, AUDIO, VIDEO |
| [Research (NOW)](features/research.md) | Live web research with sources |
| [Video](features/video.md) | Target duration, long-form segments, image-to-video |
| [REIMAGINE: Qwen-Image 2.1 gate](features/reimagine-qwen-image-2.1-gate.md) | Blocked evaluation record; current REIMAGINE routing is in chat modes |
| [Agent Workspace](features/agent-workspace.md) | Coding tasks with diffs, tests and receipts |
| [Notes](features/notes.md) · [Draw](features/draw.md) | Local-first notes and drawings that sync with the iPhone |
| [Desktop navigation (Linux)](features/desktop-navigation.md) · [desktop control (Linux)](features/desktop-control-linux.md) · [desktop control (Windows, 3.4)](features/desktop-control-windows.md) | Operating desktop applications |
| [Mail](features/mail.md) · [Personal](features/personal.md) | Local mail with optional transports; profile, contacts, calendar, tasks, reminders |
| [Studio: C#](features/studio/csharp.md) · [WinForms designer](features/studio/winforms-designer.md) | IDE features |

## Connect and Connect World

| Page | Contents |
| --- | --- |
| [Connect overview](connect/README.md) | Pairing, devices and the protocol family |
| [Connect World](connect-world/README.md) | Reaching your computer away from home through a relay you run |

## Architecture and security

| Page | Contents |
| --- | --- |
| [Overview](architecture/overview.md) | Agent platform, services and boundaries |
| [Core](architecture/core.md) · [Core and app boundaries](architecture/core-app-boundaries.md) | Shared capabilities and app separation |
| [Cross-device](architecture/cross-device.md) | Desktop ↔ phone architecture |
| [Model routing](architecture/model-routing.md) · [model selection](architecture/model-selection.md) | Presets, roles, measurements |
| [Natural language](architecture/natural-language.md) · [research](architecture/research.md) | Request interpretation; research evidence model |
| [Legacy DMDO compatibility](architecture/legacy-dmdo-compatibility.md) | Identifiers kept on purpose, Linux desktop identity, launchers |
| [Credentials](security/credentials.md) · [Owner Mode](security/owner-mode.md) | OS vault use; scoped task authority |
| [Security policy](../SECURITY.md) | Reporting vulnerabilities |

## Development

| Page | Contents |
| --- | --- |
| [Development](development/README.md) | Running from source, quality bar, tests |
| [Python dependencies](development/dependencies.md) | Where dependencies are declared and why |
| [Agent instructions](../AGENTS.md) | Repository rules for coding agents |

## Design, history and records

| Location | Contents |
| --- | --- |
| [design/](design/) | Approved design systems (V2, Grove, Studio V2, GO, mobile C9) and artifacts. Path is fixed: scripts and CSS comments refer to it |
| [history/](history/PROJECT_JOURNEY.md) | [Journey](history/PROJECT_JOURNEY.md), [decisions](history/PROJECT_DECISIONS.md), [sources](history/PROJECT_HISTORY_SOURCES.md) |
| [releases/](releases/) | Frozen 3.5 / 3.5.1 release records, written by the `scripts/*requirements*.py` generators. Historical; not updated |
| [evidence/](evidence/) | Machine-readable evidence and freeze manifests read by `scripts/check_*`. Historical; not updated |
| [archive/](archive/README.md) | Historical milestone and acceptance reports, kept unchanged |

Release-level files at the repository root: [README](../README.md),
[CHANGELOG](../CHANGELOG.md), [LICENSE](../LICENSE),
[THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md) and [SECURITY](../SECURITY.md).
