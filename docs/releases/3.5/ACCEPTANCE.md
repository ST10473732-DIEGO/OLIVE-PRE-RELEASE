# DMDO 3.5 acceptance

Evidence classes: UNIT, MOCKED INTEGRATION, LIVE LOCAL, LIVE EXTERNAL,
VISUALLY REVIEWED, NOT TESTED. User approval is separate from assistant review.

## Independently rerun baseline

| Check | Evidence | Result |
| --- | --- | --- |
| Commit/tag identity | Git read-only | v3.4.1 -> 7007fe9 |
| Compile actual sources/tests | UNIT | PASS |
| Full unittest discovery | UNIT / MOCKED INTEGRATION | 514/514, 18.914 s |
| Existing Qt smoke | LIVE LOCAL fixture | 49/49 |
| Original 37 interpretation cases | LIVE LOCAL Ollama, no execution | PASS |
| Expanded 145 interpretation cases | LIVE LOCAL Ollama, no execution | PASS |
| Original four compounds | LIVE LOCAL Ollama, no execution | PASS |
| Previous live browser/external send | Historical only | NOT RERUN for 3.5 baseline |

Commands use `.venv/Scripts/python.exe`: `-m compileall -q dmdo tests scripts main.py`,
`-m unittest discover -s tests -v`, `scripts/qt_desktop_smoke.py`,
`scripts/natural_language_evaluation.py --limit 37`, `--broad --limit 145`,
`--compound --limit 4`. Runtime logs are ignored; durable results belong here.

## M1 gate

Working prototype delivered for review; **not user approved**. Current automated
result 523/523; legacy Qt 49/49 with localhost access; new actual local UI 17/17 at
1366×768, 1920×1080 and 150% scaling. See [M1_REVIEW.md](M1_REVIEW.md) and
[machine-readable local evidence](evidence/shell-results.json). Real screenshots
and recording are linked there. This does not accept all release requirements.
Full mandatory scope, outstanding M1 polish and later milestones remain tracked.

Not accepted. Required: actual Welcome/Enter/Home/Chat/Studio; same service graph;
state retention; empty/populated synthetic profile; screenshots; recording if
available; startup/navigation/resource timings; keyboard, resize and reduced
motion checks. The user must approve or request revisions before M2 begins.

## Release gate

M2-M6, native personal data, mail transports/vault, all E2E demonstrations,
packaging and final visual approval are NOT TESTED / NOT IMPLEMENTED.
No v3.5.0 tag is authorized until applicable acceptance and user approval exist.

M0 integration evidence: `scripts/qt_quick_spike.py --backend default` and
`--backend opengl`; additional `--webengine` run. All checks PASS, QML errors=0.
Direct3D11 is selected from measured lower construction/RSS cost and successful
coexistence with actual local WebEngine and native docks. Qt documents an extra
offscreen pass and disabled threaded render loop for QQuickWidget; these costs
must still be measured in the final composition, not assumed absent.
[Qt QQuickWidget documentation](https://doc.qt.io/qt-6/qquickwidget.html).
