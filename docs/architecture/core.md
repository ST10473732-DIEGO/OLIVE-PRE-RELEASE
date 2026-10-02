# OLIVE dot-matrix Core

Current Welcome behaviour follows the user's subsequent explicit request: no Play/Pause button or motion-setting text at Enter. The large Welcome olive always rotates while visible, including when system/app reduced motion or a stored Core pause is set. Hidden/minimized/unmounted renderers still stop. Compact activity animation and its Appearance preferences remain unchanged. This Welcome-only exception supersedes the earlier opt-in behaviour described in the diagnostic history below; no Windows setting is changed.

This final Welcome change passed 4 focused Electron scenarios, 23 frontend tests, 697 Python tests, compilation, TypeScript, lint and build. Evidence: `artifacts/core/always/`; the regenerated Welcome screenshot was opened and inspected. A fresh isolated preview was opened for the user. Earlier full-suite counts below remain historical rather than repeated claims for this narrow follow-up.

The Electron Core now uses one reusable `OliveCore` Canvas component. This is a presentation change before M4; version, Python services, data, permissions, Qt fallback and the default launcher are unchanged.

## Reference and implementation

The supplied `assets/branding/olive-core-reference.png` is byte-identical to the original green cartoon olive artwork, rather than a blue concept poster. Both were inspected. The silhouette/opening informed the geometry; the user's written blue/cyan direction informed lighting. The external green olive icon/source are unchanged. The component does not display or rotate either PNG.

- `desktop/src/components/Core.tsx`: shared Welcome/compact component, accessible state label, non-motion attention markers and local dotted SVG failure fallback. Existing Core callers remain supported.
- `desktop/src/components/olive-core/geometry.ts`: stable asymmetric ellipsoid surface, recessed bowl and dotted rim; perspective projection, common 3D transforms and motion controller. There are 2,434 Welcome points and 357 compact points. Back-facing surface dots are culled; the bowl is clipped by its rotating aperture.
- `desktop/src/components/olive-core/renderer.ts`: Canvas 2D projection and lighting, no added dependency. No per-frame React updates. Logical canvas size is bounded to 300px, DPR to 2 and bitmap width to 600px; paints target at most 30/sec.
- Welcome and RailCore retain their existing shared positional handoff. Position-only projection avoids magnifying a low-resolution compact raster during the transition. Orientation is not continuously transferred between component instances.
- Electron main/preload forward a boolean native window-visibility signal privately to the DOM. No new renderer capability, backend endpoint or privileged API is exposed.

## Behaviour and lifecycle

Welcome gently accelerates into a roughly 12-second spin around the olive's own fixed, tilted pole-to-pole axis, like a planet. Local-axis rotation precedes the fixed tilt; the axis does not precess. This is decorative and makes no model request. Enter remains enabled. Compact Ready rests; Thinking/Working/Researching accelerate and brighten. Ready settles smoothly after work; approval, pause, degraded and error states stop active rotation and retain readable text/attention symbols.

The existing shared `runtime.activity` aggregation remains authoritative. No new task manager or focus-triggered fake activity was added. Activity-centre click behaviour remains intact.

System reduced motion is respected by default. Welcome explains when it is on and offers explicit Play/Pause Core animation; the activity centre also offers Follow system / Animate Core only / Pause. This local appearance preference affects only the Core and never changes Windows settings. OLIVE's explicit Reduced motion preference takes priority even over Core-only Play. Document visibility, native minimize/hide, intersection visibility and unmount stop the renderer. Resize/DPR/theme changes update it; frame deltas are capped on resume. Observers, media-query listeners and RAFs are disposed. Native minimize initially failed the live test using document visibility alone; the narrow native visibility signal corrected that observed defect, using supported [BrowserWindow visibility events](https://www.electronjs.org/docs/latest/api/browser-window#page-visibility).

The user-reported static preview was reproduced with ordinary Electron startup: `systemReduced=true`, app reduced preference false, visible/non-minimized window, stopped renderer. Evidence: `artifacts/core/axis/normal-launch.json`. Automated media emulation had concealed the actual system setting. This was a motion preference, not failed Canvas rendering. The axis correction separately follows the user's clarification; the regression now checks an invariant transformed pole over a full turn and moving off-axis surface/rim points.

Fixed-axis follow-up validation: 23 frontend and 697 Python tests passed; compilation, TypeScript, lint and production build passed. All 7 focused Electron scenarios passed together (motion opt-in/persistence, actual validation activity, concurrent activity, normal/reduced handoff, responsive layout and security). The full 29-scenario result below is the earlier Core checkpoint, not a fresh full-suite claim for this follow-up. A first focused run caught the selector's missing concise accessible name; it was fixed without weakening the assertion. Ordinary startup then verified advancing frames/angles with `systemReduced=true` and explicit `choice=play`; `artifacts/core/axis/verified-normal-launch.json` and `axis-2.png`/`axis-6.png` record this. Both actual images were opened and inspected. Playback was enabled through the Core Play button for the user's request, only in a new isolated preview profile; that preview is left open for the user.

## Acceptance and evidence

Evidence is ignored under `artifacts/core/`. `acceptance/result.json` contains real renderer counters and timestamps. `acceptance/olive-core.mp4` records Welcome angles, Enter, compact idle, actual Studio validation and return to idle. The test invokes Python unittest in a synthetic workspace with Ollama unavailable; it does not inject a completed task. The existing controlled concurrent-task scenario verifies unrelated work prevents false Ready.

Approval/paused/error/degraded visual variants are explicitly synthetic main-process presentation events. Canvas-unavailable and high-density emulation are test substitutions. No model, desktop input, external communication or real personal profile is needed. Screenshots and multiple recording frames were opened and visually inspected, including dark/light, 1440x920 and 1366x768 windows, in-app enlargement, DPR emulation, fallback and different rotation angles. Rim density and handoff raster scaling were corrected during internal review.

Fresh final validation: 697 Python tests, 23 frontend tests, 7 harness tests, TypeScript, lint, production build and `python -m compileall -q .` passed. The complete ordinary Electron run passed 29 scenarios with 3 opt-in skips, exit 0 (4.5 minutes). Logs: `artifacts/core/python-final.log`, `compile-final.log`, `harness-final.log`, `final/frontend-*.log`, and `electron-final.log`. Qt production code was not changed; its separate 49-check GUI harness was not rerun.

The three ordinary opt-ins remain separate: live local Chat, Agent/public Research, and M3 local-language evaluation. This logo change does not require rerunning those model/network operations. No opt-in live result is claimed.

An earlier full run failed the native-data test while opening Settings. It overlapped a frontend rebuild and is not used as the clean acceptance run. The failure is preserved in `electron-first-run.log` and `first-settings-failure.md`; the unchanged assertion passed in the subsequent complete run against the fixed build. No Settings fix or proven product root cause is claimed. Enlarged screenshot capture was corrected to use native `capturePage` after zoom, instead of a clipped CDP screenshot.

## Measurement limits

The final acceptance measured about 29 Canvas paints/sec across the Welcome samples, with the running draw-time estimate falling from 0.54ms to 0.38ms (maximum 2.0ms). Compact drawing measured about 0.22ms, maximum 0.40ms. Idle and minimized frame counters stopped. These are renderer CPU draw timings on this environment, not GPU time, total process memory or combined inference performance; samples are retained in `result.json`.

The recording uses event-driven CDP frames and does not establish display frame-rate smoothness. Physical multi-monitor/DPI changes and combined Ollama/GPU load were not measured. Canvas projection uses deliberately simple lighting/occlusion, not a physically based mesh renderer. The opening is near the pole and stays at the same pole during the fixed-axis spin; its rim and recessed dots rotate with the surface. Self-review is not independent human approval or accessibility certification.
