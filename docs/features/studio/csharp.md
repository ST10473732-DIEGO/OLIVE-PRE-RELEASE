# Studio C# starter and presentation cleanup

Choose **Studio → New Project → Starter → C#**. The local console starter includes `Program.cs`, `App.csproj` targeting .NET 10, `.gitignore`, a README and a NuGet configuration with no remote sources. Creation only writes starter files; Run uses the installed .NET SDK through existing RunSessions and permission checks. No package or SDK is installed. Existing C# syntax highlighting is retained; no LSP/debugger is claimed. The starter has no unit-test suite.

The Welcome footer slogan and Studio's two implementation captions were removed. Actual save/conflict notifications remain.

Live testing exposed missing NuGet directory context in the filtered run environment. .NET now receives project-local CLI/user-cache directories under `obj/.olive-dotnet` and Windows installation-directory variables. It does not inherit the user's application-data directory or credential environment variables. Directory resolution rejects escape from the workspace. The SDK's first-run banner and telemetry are disabled; compiler errors remain visible. This does not change execution isolation or permissions.

Implementation references: [SDK-style projects](https://learn.microsoft.com/en-us/dotnet/core/project-sdk/overview), [NuGet directory resolution](https://raw.githubusercontent.com/NuGet/NuGet.Client/dev/src/NuGet.Core/NuGet.Common/PathUtil/NuGetEnvironment.cs), and [supported CLI environment settings](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-environment-variables).

Evidence is local under `artifacts/core/studio-cleanup/`: actual Electron screenshots were opened and inspected; `run.json` records the real C# operation, stdout `Hello from OLIVE!`, completed state and exit code 0. The installed SDK emits a non-blocking workload-verification warning; no workload update was attempted. Earlier failing runs are preserved separately. The final focused Electron group passed 6 scenarios, including Java/Studio/security regressions. TypeScript, lint, build and 23 frontend tests passed. Python totals are recorded in the release STATUS. This is not a new full ordinary Electron suite run or clean-machine packaging result.
