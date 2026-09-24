import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from olive.desktop.linux.messaging_observation import visual_candidates
from olive.desktop.target_region import TargetEvidence, TargetState


class VisualMessagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_semantics_evaluates_visual_evidence_without_composer_authority(self):
        frame = {'width':100, 'height':100}
        for state in (TargetState.FOUND, TargetState.NOT_VISIBLE_HERE):
            with self.subTest(state=state):
                runtime = SimpleNamespace(check_task=Mock(),
                    native=SimpleNamespace(call=AsyncMock(return_value=frame)),
                    gui=SimpleNamespace(action=AsyncMock(return_value={'action':'left_click','coordinate':[150,150]})),
                    desktop=SimpleNamespace(record=SimpleNamespace(history=[])))
                grant = SimpleNamespace(scope=SimpleNamespace(account='Owner', server='Workshop', destination='Finch'))
                with patch('olive.desktop.linux.messaging_observation.evidence',
                           return_value=TargetEvidence(state,(10,10,20,20))):
                    with self.assertRaisesRegex(ValueError, 'MESSAGING_VISUAL_CONTEXT_UNVERIFIED'):
                        await visual_candidates(runtime, grant, 123)
                self.assertEqual(runtime.gui.action.await_count,3)
                runtime.native.call.assert_awaited_once_with('visual_observe', {'pid':123}, timeout=5)
                candidates = runtime.desktop.record.history[0]['candidates']
                self.assertEqual([c['grounded'] for c in candidates],[state == TargetState.FOUND]*3)

    async def test_stop_after_model_evaluation_prevents_any_input(self):
        runtime = SimpleNamespace(check_task=Mock(side_effect=[None,InterruptedError('Stopped')]),
            native=SimpleNamespace(call=AsyncMock(return_value={'width':100,'height':100})),
            gui=SimpleNamespace(action=AsyncMock(return_value={'action':'left_click','coordinate':[150,150]})),
            desktop=SimpleNamespace(record=SimpleNamespace(history=[])))
        grant = SimpleNamespace(scope=SimpleNamespace(account='Owner', server='', destination='Finch'))
        with patch('olive.desktop.linux.messaging_observation.evidence',
                   return_value=TargetEvidence(TargetState.FOUND,(10,10,20,20))):
            with self.assertRaises(InterruptedError):
                await visual_candidates(runtime, grant, 123)
        runtime.native.call.assert_awaited_once_with('visual_observe', {'pid':123}, timeout=5)
        self.assertEqual(runtime.desktop.record.history,[])
