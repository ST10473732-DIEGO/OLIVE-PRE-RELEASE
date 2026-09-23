# Linux Desktop Control acceptance

Status: **implementation in progress; not accepted**.

Initial isolated-profile reproduction on 2026-09-23 used Electron 44.3.0 and
the retained local Node/.NET/JDK toolchains. Six selected tests ran together:
**1 passed, 5 failed**. This is not a new full Electron aggregate.

| Inherited case | Reproduction | Current classification |
| --- | --- | --- |
| attach-diagnostics | Failed | Linux bridge rejects Desktop Control |
| m2-desktop | Failed | No native Linux adapter |
| owned-launch | Failed saving enabled policy | Linux platform guard |
| browser/GO | Passed | Intermittent defect still under investigation |
| responsive | Failed at 640×480 | Fixed by explicitly approved three-line state exception; focused journey passed |
| winforms-designer | Failed selecting template | Native Windows-only functionality; Windows acceptance pending |

The user approved the three-line state-only close of the Explorer overlay when
opening a panel in narrow mode. The unchanged assertion then exposed an inactive
fixture: it expected Stop while no program was running. The fixture now runs its
owned program waiting for input during resizing and stops it afterward. All
original assertions remain. The focused journey passed (1 test, 5.0 seconds).
No CSS or screenshot expectation changed. Both changes require the final full
Electron run before aggregate acceptance.

Live capture, input, emergency shortcut, physical takeover, vision grounding,
real Firefox/Kate/Dolphin and messaging acceptance remain pending. Installed
libraries and portable substitutions do not count as those passes.
