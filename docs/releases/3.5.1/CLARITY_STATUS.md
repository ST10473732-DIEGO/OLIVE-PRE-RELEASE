# OLIVE clarity-first redesign + multi-project Studio — working status

Branch `design/olive-clarity-and-multi-project`, created from
`design/olive-workbench-redesign` at `dfda419`. Resumable record for the brief
"clarity-first complete redesign + multi-project Studio". Update at every
checkpoint; do not restart from scratch.

## What this brief changes about the previous one

- The global work-item tab shelf is **replaced** by a restrained labelled
  navigation pane (compact mode + narrow overlay). Global feature navigation and
  local work-item navigation are separate jobs again.
- Welcome is **no longer pinned** to its old composition and may be redesigned,
  keeping the olive identity (dot-matrix, real depth rotation, Enter OLIVE).
- Home is rebuilt around one composer + one feature launcher, not several
  overlapping collections of the same destinations.
- Studio gains an always-available **New project** wizard and **truly
  independent** workspace sessions.

## What must be preserved (verified working at the branch point)

Language services (OmniSharp/pylsp), DAP debugging (netcoredbg/debugpy), ConPTY
terminals, the .NET solution/project system, structured tests, safe file editing
with hash checks, Monaco, native Personal Core, Mail, Research, Desktop Control,
the validated bridge, permissions/approvals, profile locking.

## Checkpoints

- [x] 1 Feature registry: one source driving navigation, Home launcher, palette,
      availability labels and search aliases.
- [x] 2 Shell: labelled navigation pane (default), compact mode, narrow overlay;
      remove the global tab shelf; Studio keeps local document/workspace tabs.
- [x] 3 Home: greeting, one composer, one "Your apps" launcher, compact Continue,
      contextual activity only when useful.
- [x] 4 Welcome redesign + entrance transition.
- [x] 5 Status and privacy copy accuracy (Idle · AI offline, no blanket claims).
- [x] 6 Backend: toolchain/template discovery (cached, bounded, off the UI thread)
      and multi-language project creation at a chosen location.
- [x] 7 Studio: New project wizard (language → template → name/location →
      options → open behaviour) with real creation; distinct from New file,
      Open workspace, Add project to solution, OLIVE Project.
- [x] 8 Studio: independent workspace sessions + switcher; per-workspace state;
      routing safety for diagnostics, saves, stop, debug, terminal.
- [x] 9 Other pages kept consistent; action-level parity ledger.
- [x] 10 Tests, acceptance journey A–O, visual QA at 1920/1440/1366/narrow,
      fresh full regression, final report.

## Notes

- Repository object store has pre-existing missing blobs in old history from a
  failed background gc; `gc.auto=0` is set. Recent commits and the worktree are
  intact.
