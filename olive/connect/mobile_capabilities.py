"""What a paired phone can reach on this computer, by product area.

Remote AI (``models.remote``) serves OLIVE Chat to a paired phone over
olive-chat/1: every Chat mode, attachments and media artifacts, content only.
The remaining remote controls exist in the Connect vocabulary but are not
implemented in this version; listing them grants nothing. The desktop Devices
panel reads this module instead of keeping its own list.
"""

# Vocabulary entries whose function is served by another capability.
PROVIDED_BY = {'chat': 'models.remote'}

# Remote controls a phone cannot use in this version (shown as unavailable).
FUTURE_CONTROLS = ('tasks', 'calendar', 'reminders', 'notifications', 'files.shared', 'filesystem.full',
                   'terminal', 'apps.launch', 'desktop_control', 'software.install')


def unavailable_controls(capabilities):
    """Future controls this computer does not support, in display order."""
    supported = {c['capability'] for c in capabilities if c.get('supported') and not c.get('policy_disabled')}
    return [name for name in FUTURE_CONTROLS if name not in supported]
