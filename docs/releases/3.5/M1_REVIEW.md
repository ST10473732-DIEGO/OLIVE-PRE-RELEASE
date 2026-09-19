# M1 working prototype — visual review requested

This is `3.5.0.dev1`, not a completed 3.5 release. M0 is verified. The actual M1
application now has Welcome, an animated Core, Enter, Home, redesigned Chat and
the integrated native Studio shell. **No user visual approval has been granted.**
M2–M6 and Native Personal Core interfaces have not started.

## Actual application evidence

All images and the recording below were captured from QApplication/QMainWindow,
not generated mockups. Populated states use an isolated temporary profile with
explicit synthetic-data labels. No personal accounts or external messages were used.

- [Welcome](evidence/welcome.png)
- [Home empty](evidence/home-empty.png) / [Home populated](evidence/home-populated-fixture.png)
- [Chat empty](evidence/chat-empty.png) / [Chat populated](evidence/chat-populated-fixture.png)
- [Studio with real code and actual program output](evidence/studio-code-output-fixture.png)
- [All Spaces](evidence/all-spaces.png)
- [Light theme](evidence/home-light-fixture.png) / [narrow Home](evidence/home-narrow-fixture.png)
- [Component gallery](evidence/gallery.png)
- [Actual interaction recording](evidence/m1-interaction.mp4)

The recording shows keyboard Enter, page navigation, synthetic population, Studio
file access and run output, theme switching and narrow layout. It is a short
automated local recording with real capture timestamps; it is not a smoothness
benchmark. The offline Core correctly shows Degraded. Review other state examples
in Appearance → Component gallery; those examples are labelled synthetic.

## Integration and checks

One QApplication and one QMainWindow; QQuickWidget uses Qt's default Direct3D11.
Studio is still the real docked QWidget IDE. Services stay in Python behind the
existing worker runtime and deterministic permissions. Home has no separate parser.
The legacy presentation is available through `DMDO_PRESENTATION=legacy`.

- Compilation: PASS, actual source/test/script directories only.
- Automated regression: **523/523**; nine new lifecycle/persistence tests.
- Legacy Qt smoke: **49/49**, with localhost access for its disposable WebEngine server.
  Restricted runs were 48/49 because that local preview could not load; expectations
  were not weakened. The unrestricted localhost rerun passed.
- M1 LIVE LOCAL: **17/17** at 1366×768, 1920×1080 and 150% scaling.
- Independently rerun M0 natural-language baseline: **37/37**, **145/145**, compounds **4/4**.
  These interpretation suites were not rerun after presentation-only work. New Home
  request lifecycle is covered by mocked controller integration, not a new live-model
  Home end-to-end claim. No external browser/account tests were rerun for M1.

Checks include keyboard entry; model-offline entry; no repeated Welcome; all shipped
spaces; real fixture repository writes; authorised Studio open; retained unsaved
buffer/cursor and Chat composer; actual Studio Run output; light/Reduced Motion;
rapid navigation; no QML load errors; one primary window; hidden animation suspension.

## Measured performance

| Run | First painted Welcome including Qt imports | Cached navigation callback mean | Process RSS |
| --- | --- | --- | --- |
| 1366×768, recording enabled | 2,020 ms | 5.17 ms | 340.8 MiB |
| 1920×1080 | 1,955 ms | 5.02 ms | 353.0 MiB |
| 150% scaling | 1,965 ms | 4.84 ms | 382.0 MiB |

These are local warm-environment samples, not cold-machine measurements. The first
paint is measured at the QQuickWidget paint event; callback timing is not physical
display latency. The recorded 1366 run constructed the app in 889 ms. Hidden idle
CPU was 0.0–1.3% of one core during the 1.2-second samples. GPU VRAM, sustained visible
idle GPU use and display FPS are NOT MEASURED. Token contrast checks pass the
documented pairs; this is not accessibility certification.

## Olive and assets

The original `assets/branding/olive-source.png` is unchanged, SHA256
`2e26d64101d43d061ea6d128e90ba644b11b5ce8459337fa9919bf341c4e5145`.
The supplied RGB image contained a baked checkerboard. The image-generation tool
created `olive-transparent-candidate.png` using this edit instruction:
"Remove only the baked checkerboard; preserve the olive silhouette, orientation,
aspect ratio, outline, green fill, highlight and red detail; no redesign, shadow,
text or recolouring." The result has slight fill texture and is **not pixel-identical**
to the original. Its fidelity remains for user review.

`scripts/prepare_experience_assets.py` packages the derivative into `dmdo.ico`
and 16/24/32/48/64/128/256 PNGs with actual alpha and consistent padding.
The development application/window/tray selects the ICO. No executable/shortcut
was rebuilt and actual Windows taskbar appearance is not claimed verified.
The original local vector navigation family includes an MIT licence.

## Remaining mandatory work and limitations

The requirement ledger distinguishes implementation, unit/integration/live tests,
assistant visual review and user approval. This prototype is ready for direction
review; it does not imply every M1-labelled polish/acceptance item is complete.
No mandatory scope has been downgraded or removed.
The explicit [remaining M1 checklist](M1_OPEN.md) lists unfinished mandatory
acceptance/polish separately from the working prototype and later release work.

Still open within Experience work: keyboard-only audit of all controls, final
motion refinement and per-control state coverage. Context-chip inspection/clearing,
attachment chips and concise activity text are implemented; full cross-feature
acceptance of those controls remains open. Chat retains existing attachment and
project actions through its menus. Its composer grows
from 80 to 140 pixels, and Markdown blocks remain safe; code typography still
needs visual polish. Some layout metrics remain local constants during this
prototype. Explicit Pop out is available from Commands for eligible workspaces.
The native editor is retained; the bounded Monaco spike is
explicitly post-approval. Final editor conflict/comparison polish remains open.

The command palette already opens shipped spaces, new Chat and New Project; future Personal
Core actions and Settings search remain in M2/M3. Other feature pages retain
their existing controls until approval. Comprehensive new-shell parity across
every action is not yet accepted. Credentials, Contacts, Calendar, Tasks,
Reminders, native Mail, imports/exports and consistent SQLite backup work are
still unimplemented 3.5 scope. No installer, external-mail or clean-machine result.

## Review and continuation

Launch `run_dmdo.bat`, press Enter DMDO, open Chat and Studio, and use Appearance
for light theme, Reduced Motion and the component gallery. Ctrl+K opens Commands.
To regenerate isolated evidence:

```powershell
.venv/Scripts/python.exe scripts/experience_smoke.py --output .experience-350/review --record
```

The script exits after validation and never reads the normal profile. Recording
uses installed ffmpeg; no dependency is downloaded. The 3.4 tags remain untouched.

**Approve or revise the visual direction before work expands beyond M1.**
Final appearance approval and v3.5.0 acceptance remain separate future gates.
