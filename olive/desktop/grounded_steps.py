"""One-step semantic suggestions for fields already fixed by the user's task.

No new authority, coordinates, model call or app-specific path. Every suggestion
still crosses the shared broker and a fresh native observation before execution.
Missing or ambiguous semantics fall back to the bounded planner/handoff.
"""
from .task_authority import is_composer, is_search_control, same_control_label


def next_step(scope, observation, submitted):
    if submitted:
        return None  # Verification, never a second submission, owns this phase.
    controls = [c for c in observation['controls'] if c.get('enabled')]
    if scope.effect == 'click':
        candidates = [c for c in controls if same_control_label(c.get('name', ''), scope.content)]
        if len(candidates) != 1:
            return None
        from .target_region import semantic_target, TargetState
        evidence = semantic_target(observation, candidates[0]['name'])
        if evidence.state != TargetState.FOUND:
            return None
        target = candidates[0]
        # Standard button keyboard activation avoids guessing a point when native
        # Chromium wrappers cannot provide a reliable cross-tree hit-test.
        if target.get('role') in {'button', 'push button'}:
            return dict(action='key' if target.get('focused') else 'focus', target=target['id'],
                        value='Space' if target.get('focused') else '', revision=observation['revision'],
                        expected='Activate the uniquely focused requested button')
        return dict(action='click', target=target['id'], value='', revision=observation['revision'],
                    expected='Observe the requested control after the click')
    if scope.effect == 'search':
        candidates = [c for c in controls if is_search_control(c)]
    elif scope.effect in {'send', 'draft'}:
        context = {'account': scope.account, 'destination': scope.destination, 'server': scope.server}
        if observation.get('destination') != context:
            # Navigate one semantic target at a time, re-observing full context.
            if scope.server and not any(c['name'] == scope.server and c.get('selected') for c in controls):
                matches = [c for c in controls if c['name'] == scope.server]
            else:
                matches = [c for c in controls if c['name'] == scope.destination and c.get('role') != 'heading']
            if len(matches) != 1:
                return None
            actions = [a for a in matches[0].get('actions', []) if a in {'click', 'press', 'activate', 'select'}]
            return dict(action='invoke' if len(actions) == 1 else 'click', target=matches[0]['id'], value=actions[0] if len(actions) == 1 else '', revision=observation['revision'],
                        expected='Verify the complete destination context')
        candidates = [c for c in controls if is_composer(c)]
    else:
        return None
    if len(candidates) != 1:
        return None
    target = candidates[0]
    value = target.get('value', '')
    if value and value != scope.content:
        return None  # Never overwrite an unrelated draft/query.
    if not target.get('focused'):
        action, argument = 'focus', ''
    elif not value:
        action, argument = 'type', scope.content
    elif scope.effect == 'draft':
        action, argument = 'finish', ''
    elif scope.effect == 'send':
        buttons = [c for c in controls if c.get('name', '').strip().casefold() in {'send', 'send message'}]
        if len(buttons) != 1:
            from .gui_evidence import enter_sends
            if buttons or not enter_sends(target):
                return None  # Unknown semantics never become an Enter guess.
            return dict(action='key', target=target['id'], value='Enter',
                        revision=observation['revision'], expected='Verify the outgoing message and status')
        target = buttons[0]
        advertised = [a for a in target.get('actions', []) if a in {'click', 'press', 'activate', 'invoke'}]
        action, argument = ('invoke', advertised[0]) if len(advertised) == 1 else ('click', '')
    else:
        action, argument = 'key', 'Enter'
    return dict(action=action, target=target['id'], value=argument,
                revision=observation['revision'], expected='Verify the requested state after this step')
