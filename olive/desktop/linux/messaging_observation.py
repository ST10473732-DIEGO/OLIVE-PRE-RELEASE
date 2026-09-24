"""Evaluate visual messaging candidates when native semantics are unavailable.

Candidate labels/regions establish presence, not account or composer authority.
Until a client contract proves those roles, preserve drafts and enter no text.
"""
import asyncio
from ..visual_targets import evidence, validate_point
from ..target_region import TargetState


async def visual_candidates(runtime, grant, pid):
    runtime.check_task(grant)
    frame = await runtime.native.call('visual_observe', {'pid':pid}, timeout=5)
    if runtime.gui is None:
        from ...services.gui_model_service import GuiModelService
        runtime.gui = GuiModelService(runtime.desktop.s.model_residency)
    candidates = []
    for role, label in (('account', grant.scope.account), ('server', grant.scope.server),
                        ('destination', grant.scope.destination)):
        if not label:
            candidates.append({'role':role, 'state':'UNRESOLVED', 'grounded':False})
            continue
        observed = await asyncio.to_thread(evidence, frame, label)
        # Evaluate the installed model even when OCR abstains; a model-only
        # answer is recorded as rejected, never promoted into target evidence.
        proposal = await runtime.gui.action(frame, 'Locate the visible '+role+' label '+label+'. If absent, interact.')
        runtime.check_task(grant)
        grounded = False
        if observed.state == TargetState.FOUND:
            try:
                validate_point(proposal, frame, observed.bounds)
                grounded = True
            except ValueError:
                pass
        candidates.append({'role':role, 'state':str(observed.state), 'grounded':grounded})
    runtime.desktop.record.history.append({'operation':'visual_messaging_candidates', 'candidates':candidates,
        'status':'evaluated without input; client role/settings proof required'})
    raise ValueError('MESSAGING_VISUAL_CONTEXT_UNVERIFIED: visual candidates were evaluated, but account, destination, composer and current submission settings are not jointly verified. No text was entered or message sent.')
