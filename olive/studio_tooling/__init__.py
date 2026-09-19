"""Real developer tooling hosted by the authoritative Python runtime.

Language servers (LSP), debug adapters (DAP), pseudo-terminals and the .NET/Python
toolchains run as owned child processes of approved workspaces. The renderer only
reaches them through validated bridge methods; every session start passes the
tool registry's permission and audit path.
"""
