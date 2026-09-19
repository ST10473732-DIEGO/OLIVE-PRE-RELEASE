# Approved direction and Studio revision

> **Recovery checkpoint, 10 September 2026:** The material below is recovered
> historical documentation. Its test totals, security audit and approval claims
> are not fresh acceptance. See [RECOVERY_REPORT.md](RECOVERY_REPORT.md) for the
> current verified state. The latest brief requires a new visual-review stop.

The user approved the M1 visual direction ("i like the direction") and requested fewer repetitive approvals, Java and library support, an uncluttered IDE, named project folders, and dependable requested actions including Discord delivery. This approves continuing beyond the M1 gate. It is not final visual or release acceptance.

## Implemented and verified

- Electron Studio Open, Save, Compare, Reconcile, Run, Restart and Test use the direct UI action as consent. Python creates a short-lived, single-use receipt bound to task ID, tool and canonical arguments. DENY policies still win. Receipts are not accepted in IPC arguments, model output or persisted settings. Agent-proposed actions keep their existing review path. Save still checks the disk hash and creates checkpoints.
- New Project offers Java, Python, JavaScript and empty starters. Files live under the active DMDO data directory's `projects/<name>` folder (normally `~/.dmdo/projects/<name>`). Project and workspace records are linked. Names cannot escape the directory; existing folders are never overwritten. No old files are moved. A failed metadata write leaves recoverable files rather than deleting them; multi-repository creation is not transactional yet.
- Monaco recognises Java and additional source extensions. Plain Java projects use the installed JDK, root-source compilation and a `lib/*` classpath. Java 21.0.9 was detected locally. The actual Electron acceptance created a Java project, saved an edit, compiled against a harmless locally built JAR, and printed `Hello from a local library!` through RunSession output. No dependency download occurred.
- Build output names the check even when successful compilation prints nothing. Project creation uses the shared accessible drawer instead of expanding the editor layout.

Implementation: `dmdo/agent/direct_action.py`, `dmdo/application/studio_controller.py`, `dmdo/bridge/host.py`, `dmdo/services/project_scaffold.py`, existing build/run/workspace services, and `desktop/src/features/NewProject.tsx` / `Studio.tsx`.

## Evidence

- UNIT / MOCKED INTEGRATION: 536 Python tests passed; five new tests cover consent binding/expiry/reuse, DENY precedence, directory escape/collision preservation and starter/build contracts.
- FRONTEND: strict TypeScript, lint, production build and five component/contract tests passed.
- LIVE LOCAL: all five Electron tests passed, including real Ollama streaming/cancel, Java plus local library, Python save/test/run with **zero approval events**, conflict rejection, navigation and renderer security checks.
- QT FALLBACK: 49 checks passed. The restricted run failed the local WebEngine preview; the isolated rerun with local networking available passed. This was an environment limitation, not recorded as an independently reproduced product defect.
- VISUALLY REVIEWED: [Java Studio with real library output](evidence/studio-java-project.png). Synthetic temporary profile only. No external message was sent.
- Targeted compile passed. Existing 37/37, 145/145 and 4/4 semantic scores are previous baseline evidence, not rerun in this revision.

## Still required

This is a partial implementation of the user's revision, not a completed release or universal autonomy claim. Direct consent is currently connected to the listed Electron Studio actions. Natural-language cross-feature actions, desktop navigation and communication still need an appropriate deterministic user-intent authorization scope and regression coverage. No global permission policy was changed.

No supported Discord bot/application submission transport is connected. The existing generic native control path is not evidence of supported automatic Discord delivery. Implement and configure the supported transport before claiming that sending works; do not use user tokens or a simulated-input workaround. Destination ambiguity and uncertain submission must remain explicit. Do not perform unattended external sends.

Java language servers/debugging, a package-management UI, generalized build/run configurations, and full VS Code-like action parity remain unfinished. The new Java route targets root `Main.java`; run Test after changing other Java classes so their compiled output is current. Maven/Gradle hooks pre-existed but their installed toolchains and live workflows were not validated here. JavaScript starter execution requires an available Node runtime; no system runtime was installed. Root Java compilation disables annotation processors. These limitations must not be presented as full Java IDE support.

Continue R351-REV1-04 through 06, then remaining M2/M3/M4 obligations. Preserve the running user preview and unsaved work when refreshing application builds. Qt remains the default launcher; no release tag or packaged executable was created.

Java launcher reference: [Oracle Java command documentation](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html). Installed-runtime behaviour was tested separately as described above.
