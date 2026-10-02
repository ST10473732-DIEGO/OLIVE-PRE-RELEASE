# Studio toolchain repair

2026-09-23. No system installation, shell aliases, SDK deletion or framework
retargeting. The installed repository SDK was .NET 10.0.401, MSBuild 18.9.11,
.NET/ASP.NET runtimes 10.0.12. It was absent from this process's initial PATH;
Java and `/usr/lib/jvm` were absent, as was `archlinux-java`.

The user approved repository-local Temurin JDK 21.0.12.1+1, Linux x64,
207,473,347 bytes. Official release/checksum provenance is pinned in
`evidence/backend-v3-acquisition.json`. Installation uses an ignored versioned
folder and `.toolchains/jdk` symlink; no global Java default changed.
`java -version` and `javac -version` both verify 21.0.12.1.

Shared discovery now respects explicit DOTNET_ROOT/JAVA_HOME, then PATH and
repository-local fallback. A Java runtime without javac is not a complete JDK.
Native approved runs and language services receive only the discovered tool
locations in their already filtered environment. The shell launcher uses the
same resolver. No personal home is hardcoded. Explicit invalid roots do not
silently fall back. SDK global.json and project frameworks remain authoritative.

Refresh clears SDK/module probe state. A failed template probe no longer
advertises assumed .NET templates; runtime-only/failed SDK probes do not count
as an available SDK. Executable, SDK, language-server and debugger remain
separate facts. OmniSharp 1.39.15 requests net6.0 with LatestMajor roll-forward;
its real diagnostics run succeeded on the installed runtime. netcoredbg remains
3.2.0-1092. No Linux WinForms/native Windows parity is claimed.

## Evidence

- Actual `dotnet --info`, `--list-sdks`, `--list-runtimes` checked.
- 29 focused discovery/Studio tests: 28 passed, one Windows PTY skip. Real
  OmniSharp diagnostics, DAP breakpoint/locals/step/continue and cleanup passed.
- Existing Electron Python and C# interactive Run tests both passed, including
  Console.ReadLine input, Stop and route changes.
- Real Java compiler validation, run exit 0 and Stop-owned-process release
  passed through Studio's existing services. Java interactive input and
  debugger/language-server support are not exposed by the current controller.
- Real structured MSTest through Studio passed 1 test, parsed from TRX. It
  used existing cached MSTest 4.0.2 and Microsoft.NET.Test.Sdk 18.0.1 with
  package sources cleared in the disposable fixture; no package download.
- Normal `run_olive.sh` launch succeeded with a temporary profile. C# was ready.
  Both C# and Java were ready on two subsequent fresh launches. Studio,
  Devices, GO, Chat and REIMAGINE opened through the existing controls.
  No existing OLIVE .desktop entry was found in the standard user locations;
  a desktop-entry launch is not claimed.

## Approved V2 wizard state exception

The C# and Java creation journeys time out waiting for `.wizard-done` after
successful backend creation. Frozen Studio mounts separate NewProjectWizard
instances in its empty-workspace and open-workspace branches. The onCreated
callback switches branches, discarding the first wizard's result state.
The source is identical to DESIGN_BASE. The user explicitly approved only the prepared state fix in
NewProjectWizard.tsx: keep the created workspace with the result and open it
when Done/close is used. All Created/Done assertions were retained. The four
focused C#/Java/interactive Electron journeys now pass. The exact approved
hash is recorded separately from the immutable DESIGN_BASE hashes; no style,
layout, label or IPC changed.

Older Electron fixture interpreter paths and PowerShell process counting were
ported narrowly to the native venv and psutil. No assertions, visual expectations,
timeouts or platform skips were removed/relaxed.

Rollback: revert the toolchain code commit; retain all existing SDKs and profiles.
Unset any explicit JAVA_HOME override to resume prior resolution. The optional
local JDK and its archive can remain inert; removal is not required for rollback.
