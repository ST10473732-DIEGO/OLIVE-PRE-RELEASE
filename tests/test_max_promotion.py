"""The promoted MAX preset is pinned to one artifact; the previous mapping is retained for rollback."""
from types import SimpleNamespace
import unittest

from olive.services.presets import PREVIOUS_MAX, PRESETS, PresetCatalog


class MaxPromotionTests(unittest.TestCase):
    def catalog(self, digest):
        model = SimpleNamespace(installed=True, supports_embeddings=False, capabilities=('completion',))
        services = SimpleNamespace(model_registry=SimpleNamespace(get=lambda name: model),
                                   model_infos=[SimpleNamespace(name=PRESETS['max']['model'], digest=digest)])
        return PresetCatalog(services)

    def test_exact_digest_is_required_for_max(self):
        self.assertEqual(PRESETS['max']['model'], 'orcarouter/Qwen3.8-27B-Uncensored:q3_K_M')
        self.assertTrue(self.catalog(PRESETS['max']['pinned_digest']).get('max')['available'])
        substituted = self.catalog('0' * 64).get('max')
        self.assertFalse(substituted['available'])
        self.assertEqual(substituted['status'], 'Needs setup')
        self.assertNotIn('pinned_digest', substituted)

    def test_other_roles_and_rollback_mapping_are_unchanged(self):
        self.assertEqual(PRESETS['fast']['model'], 'qwen3:8b')
        self.assertEqual(PRESETS['normal']['model'], 'gpt-oss:20b')
        self.assertEqual(PRESETS['deep']['model'], 'gpt-oss:20b')
        self.assertEqual(PRESETS['max']['params'], {'temperature': .2, 'max_tokens': 8192})
        self.assertEqual(PREVIOUS_MAX['model'], 'qwen3-coder:30b')


if __name__ == '__main__':
    unittest.main()
