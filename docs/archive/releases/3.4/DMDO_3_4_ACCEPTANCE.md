# DMDO 3.4.0 final acceptance

Validated on the user's Windows machine, RTX 3080 Ti Laptop 16 GB VRAM,
64 GB RAM and i9-12900HX. No new models were downloaded. This closes the revised
3.4 acceptance scope, with the specific limitations below; it does not certify
arbitrary operations in every third-party application.

## Results

| Requested result | Final evidence |
| --- | --- |
| Automated suite | 404 tests pass; whole-repository compileall passes |
| Qt smoke | 45 checks pass; real Qt windows, deterministic Chat streaming fixture |
| Single-window navigation | All major features share one main window; Home → Studio → Research → Chat → Studio preserves editor/workspace and service identities |
| Calculator | Real generic One invocation; Display is 1 verified; no adapter |
| Explorer | Actual Shell location matches approved temporary directory |
| Settings | Bluetooth heading verified; configuration unchanged |
| Unknown application | Independent Qt fixture: generic controls, exact text, capability inspection and verified action; no adapter |
| Interactive browser | Installed Chrome, separate DMDO profile; local DOM fill/click/scroll, tabs, upload, download and verification pass |
| Authenticated browser / Gmail | AUTHENTICATED_BROWSER_READY_BUT_LOGIN_REQUIRED; no credentials retrieved or entered; no Send |
| Media control | Real Windows transport pause → play → pause against Chrome playing an owned silent WAV; all states verified |
| Apple Music / default audio player | Apple Music session discovered as opened; playback not validated. Default audio-player fixture did not expose a usable session. Chrome is the successful compatible application |
| Microsoft Store | Search QuickLook, exact title, publisher emako, explicit free search-result evidence and Get control observed; semantic preview generated |
| Install readiness | READY_FOR_CONFIRMED_MANUAL_ACTION; no acquisition/purchase attempted; future action requires fresh price/identity review and software.install approval |
| Vision root cause | Installed qwen3-vl-thinking renderer/parser exhausts localization budget in reasoning channel before final JSON; 600 tokens, 2,100 reasoning characters, zero final characters, length finish |
| Final vision capability | Actual authorized window capture plus qwen3-vl label verification passes; expected answer is not supplied to the model; no input authority |
| qwen3-vl result | PREVIEW label: 79 tokens, approximately 6.4 seconds. Coordinate localization remains unreliable; no fabricated pass |
| Coordinates | Explicit normalized_0_1000/capture_pixels → capture → physical client/screen transform; negative origins, resize, offsets and invalid-space tests |
| Multi-app acceptance | Real Explorer → Chrome → filesystem handoff, fresh observations, explicit focus handoff and byte-verified saved download; separate A → B → A live fixture also passes |
| Emergency stop | Stops an active sequence independently of model calls; Qt immediate button passes; authorized mouse dispatch is rejected after stop |
| Focus loss / takeover | Deliberately changing foreground blocks input to the prior fixture. Approved browser launch handoff cannot survive another foreground change |
| Modal handling | Real local browser confirm pauses control; explicit reviewed dismissal is observed; no blind acceptance |
| Consequence protection | Punctuated Send/Get and acquisition IDs blocked in generic invocation; fingerprint/revocation guards tested; actual Qt Send/Install previews and cancellation pass |
| Roles selected | Fast/General/Reasoning: qwen3:8b; Coding: devstral:24b; Vision: qwen3-vl:8b; Embedding: qwen3-embedding:0.6b |
| Coding choice | Existing fixtures: devstral 4/5, qwen3-coder 3/5. Tool-call weaknesses remain schema-validated; results are local fixture evidence, not universal rankings |
| Residency | Only qwen3-vl reported loaded after vision, then only qwen3:8b after reasoning; one managed switch, no errors; approximately 5.79 GB → 5.27 GB VRAM |
| Performance | Bounded reasoning check 6.47 s including loading; deterministic desktop actions invoke no model. UIA retains 300-node/four-second traversal budget at sixteen levels |

## Fixes and files in the completion pass

The baseline was clean on development/3.4-desktop-control at 60992b9. The first
397-test rerun exposed an intermittent Studio immediate-stop cleanup race: cancelling
the collector before its first instruction skipped process reaping. Stop now always
waits for its owned process; the regression checks assert its exit and removal.

New files:

- dmdo/desktop/coordinates.py
- scripts/browser_auth_acceptance.py
- scripts/model_release_check.py
- scripts/store_live_acceptance.py
- DMDO_3_4_ACCEPTANCE.md

Modified implementation files:

- dmdo/application/desktop_controller.py and interactive_controller.py
- dmdo/desktop/browser_focus.py, gateway.py, interactive_browser.py, media.py,
  uia_worker.py, universal_workflow.py, vision.py and visual_input.py
- dmdo/services/ollama_service.py and run_service.py
- dmdo/ui_qt/components/desktop_workspace.py, dialogs/media.py and windows/desktop.py

Modified validation files:

- scripts/diagnose_vision_fixture.py, interactive_browser_acceptance.py,
  media_live_acceptance.py, qt_desktop_smoke.py and visual_live_acceptance.py
- tests/test_browser_focus.py, test_desktop_live_boundary.py, test_desktop_vision.py,
  test_interactive_browser.py, test_studio_run_ui.py and test_visual_input.py

Documentation updated: README.md, ROADMAP.md, ARCHITECTURE_3.md,
DEPLOYMENT_DESIGN.md, PACKAGING_WINDOWS.md, DESKTOP_CONTROL.md,
APPLICATION_ADAPTERS.md and MODEL_ROUTING.md.

No dependency was added in this final pass. Existing Windows requirements include
PySide6, pywinauto, comtypes, pywin32, Pillow, Playwright and PyWinRT media bindings.
No persistent core schema changed in this pass. Visual coordinate metadata and
browser login state are additive runtime observations. Existing chats, memories,
Knowledge, Research, projects, workspaces and permission repositories are preserved.

Logical completion commits cover Studio process cleanup, vision evidence/coordinates,
browser/media/Store safety, and final acceptance/documentation. The annotated release
tag is v3.4.0, created only after automated/live checks and a clean worktree.

## Exact limitations and release decision

- Vision label verification is useful and live verified; general coordinate
  localization is not reliable. Invalid final JSON never becomes input.
- Gmail requires manual login here. Authenticated Compose, real email sending,
  recipient chips and server-side attachment handling are not claimed live tested.
- Store preview was tested without installation. Price evidence came from the exact
  search result; future acquisition must revalidate the current product and price.
  Paid purchases/subscriptions are not enabled by installation permission.
- Apple Music playback/song search, Discord navigation, complex iframes/canvas UIs,
  universal adaptive recovery and general raw keyboard/mouse macros have limited or
  unvalidated coverage. Missing semantic controls cause review, not guessed input.
- The adapter registry remains a small extension contract. Adapters are not required
  for the tested generic UIA, browser or system-media operations.
- Clean-machine/frozen-helper packaging is post-release hardening. No installer
  certification, automatic browser installation or codec installation is claimed.
- No email API, calendar, voice, trading, Tor or new UI framework was introduced.

Under the user's final revised criteria, these results satisfy universal desktop
acceptance: compatible unknown applications work, real multi-app workflows work,
login-required is handled without bypass, media works in a compatible real app,
Store produces a guarded preview, and vision provides a verified non-localization
function. Third-party application limitations remain explicit.

Recommended 3.5 preparation, not implemented here: clean-machine packaging,
broader authenticated-app and accessibility evaluation, improved local-model
localization/reasoning fixtures, and stronger recovery for complex application state.
