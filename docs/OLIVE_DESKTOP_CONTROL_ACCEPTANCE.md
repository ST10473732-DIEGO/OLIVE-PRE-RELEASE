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
| responsive | Failed at 640×480 | Explorer overlay intercepts Output hit test; exception pending |
| winforms-designer | Failed selecting template | Native Windows-only functionality; Windows acceptance pending |

The proposed responsive change is a state-only close of the Explorer overlay
when a panel opens in narrow mode. It has not been applied without approval.
No assertions or screenshot expectations were weakened.

Live capture, input, emergency shortcut, physical takeover, vision grounding,
real Firefox/Kate/Dolphin and messaging acceptance remain pending. Installed
libraries and portable substitutions do not count as those passes.
