"""One named ordinary control, grounded by GUI-Owl plus independent OCR evidence."""
import asyncio
import re
from ..visual_targets import locate, validate_point


async def click(runtime, grant, pid):
    d = runtime.desktop
    if re.search(r'send|submit|delete|remove|buy|pay|checkout|password|sign in|log in|security|install|terminal|run|execute|upload|attach|grant|allow', grant.scope.content, re.I):
        raise PermissionError('This visual control requires a more specific effect and semantic verification')
    frame = await runtime.native.call('visual_observe', {'pid': pid}, timeout=5)
    if re.search(r'password|sign in|log in|checkout|payment|firewall|security|authentication|overwrite|deletion',
                 frame['window'].get('title', ''), re.I):
        raise PermissionError('This screen requires effect-specific human handling')
    bounds = await asyncio.to_thread(locate, frame, grant.scope.content)
    d.record.current_action = 'Finding the requested control'
    d.publish()
    if runtime.gui is None:
        from ...services.gui_model_service import GuiModelService
        runtime.gui = GuiModelService(d.s.model_residency)
    proposal = await runtime.gui.action(frame, 'Click ' + grant.scope.content + '. The target must be visible; otherwise interact.')
    point = validate_point(proposal, frame, bounds)
    runtime.check_task(grant)
    fresh = await runtime.native.call('visual_observe', {'pid': pid}, timeout=5)
    if fresh['window']['id'] != frame['window']['id'] or fresh['window']['bounds'] != frame['window']['bounds'] or (fresh['width'], fresh['height']) != (frame['width'], frame['height']):
        raise ValueError('Visual window geometry changed; discarded the proposal')
    current_bounds = await asyncio.to_thread(locate, fresh, grant.scope.content)
    if current_bounds != bounds:
        raise ValueError('The target moved during inference; discarded the proposal')
    runtime.check_task(grant)
    d.record.current_action = 'Clicking the requested control'
    d.publish()
    await runtime.native.call('visual_click', {'revision': fresh['revision'], 'point': list(point)})
    after = await runtime.native.call('visual_observe', {'pid': pid}, timeout=5)
    if after['png'] == fresh['png']:
        raise ValueError('Click dispatched once; no visible change verified')
    from ...services.gui_model_service import MODEL
    d.record.history.append({'operation': 'visual_click', 'status': 'dispatched; changed frame observed',
                             'model': MODEL, 'seconds': runtime.gui.metrics[-1]['seconds']})
    d.record.status = 'completed'
    d.record.verification = 'The requested text control was independently located, clicked through EIS, and a changed frame observed.'
    return d.record.verification
