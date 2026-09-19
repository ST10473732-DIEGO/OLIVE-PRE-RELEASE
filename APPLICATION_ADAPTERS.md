# OLIVE application adapters

Adapters are optional reliability optimizations. Generic Windows observation,
target resolution and UIA control require no per-application adapter. A real
standalone Qt fixture and Notepad both passed text-entry verification through
the generic gateway.
Installed Calculator also passes generic UIA invocation and exact display verification,
including its UWP frame-host identity. An accessible search-field operation is generic.

The current Windows navigation accelerators use the shell for Explorer and
allowlisted `ms-settings:` pages for Settings. Explorer verifies its actual
Shell location; Settings verifies an accessible page heading. These operations
are connected through registered tools and deterministic permissions.

The existing adapter registry remains a contract awaiting runtime plugin dispatch.
Windows media-session controls are implemented independently of named adapters.
Store search, product identification and installation preview pass through generic UIA,
without a Store adapter. Real Chrome media passes the Windows media-session provider.
Dedicated Discord navigation remains unvalidated. Visual Studio
and VS Code retain their existing IDE service. Generic interactive browser
operations use a separate visible OLIVE browser profile, not a Gmail-only engine.

Do not equate an observed capability with permission. Missing adapters fall back
to compatible generic controls; ambiguous controls and unsupported operations
require review instead of coordinate macros. Consequential actions require their
own semantic authorization and are not implied by application-control permission.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
