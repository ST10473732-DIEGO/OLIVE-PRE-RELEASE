"""OLIVE VIDEO target duration: parser, precedence, policy, segment planner and
the olive-chat/1 duration contract. Pure logic; no engine, no FFmpeg."""
import json
import re
import unittest
from pathlib import Path

from olive.connect import chat_protocol as cp
from olive.connect.contracts import ConnectError
from olive.services import video_duration as vd

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / 'tests' / 'fixtures' / 'video_duration_vectors.json').read_text('utf-8'))


class ParserTests(unittest.TestCase):
    def test_shared_vectors(self):
        for text, seconds in VECTORS:
            self.assertEqual(vd.parse_duration(text)[0], seconds, text)

    def test_required_phrases(self):
        cases = {'20 second video': 20, '20-second video': 20, 'waves for 20 seconds': 20, 'rain, 20 sec': 20,
                 'rain, 20 secs': 20, 'a 20s video': 20, 'half a minute of rain': 30, 'a 1 minute video': 60,
                 'a 1 minute 30 seconds clip': 90, '90 seconds of waves': 90, 'a 2 minutes video': 120,
                 'waves (0:20)': 20, '01:30 of forest': 90}
        for text, seconds in cases.items():
            self.assertEqual(vd.parse_duration(text)[0], seconds, text)

    def test_scene_timing_and_ambiguous_numbers_are_not_durations(self):
        for text in ('the ball drops after 3 seconds', 'a woman in her 20s walking', 'the 1920s street scene',
                     'city at 5:30 pm', 'a 5m tall wave', 'Animate the clouds slowly.'):
            self.assertIsNone(vd.parse_duration(text)[0], text)

    def test_first_stated_duration_wins(self):
        self.assertEqual(vd.parse_duration('a 5 second clip, then 20 seconds of rain')[0], 5)

    def test_operational_words_are_removed_but_description_kept(self):
        text = 'Generate a 20 second cinematic scene of clouds moving over a futuristic city.'
        seconds, span = vd.parse_duration(text)
        self.assertEqual(vd.strip_duration(text, span), 'Generate a cinematic scene of clouds moving over a futuristic city.')
        self.assertEqual(vd.strip_duration('Create an 8 second clip', vd.parse_duration('Create an 8 second clip')[1]), 'Create a clip')
        self.assertEqual(vd.strip_duration('rain for 20 seconds', vd.parse_duration('rain for 20 seconds')[1]), 'rain')
        # Nothing descriptive left: the original prompt is kept.
        self.assertEqual(vd.strip_duration('for 0:20', vd.parse_duration('for 0:20')[1]), 'for 0:20')

    def test_swift_copy_of_the_vectors_matches(self):
        swift = (ROOT / 'mobile/ios/OLIVEMobileTests/RemoteChatTests.swift').read_text('utf-8')
        block = swift.split('// BEGIN video_duration_vectors')[1].split('// END video_duration_vectors')[0]
        rows = re.findall(r'\((".*?"), (nil|[0-9.]+)\),', block)
        parsed = [[json.loads(text), None if value == 'nil' else float(value)] for text, value in rows]
        self.assertEqual(parsed, [[t, s] for t, s in VECTORS])


class PolicyTests(unittest.TestCase):
    def test_precedence_explicit_then_prompt_then_default(self):
        policy = vd.VideoPolicy()
        explicit = vd.resolve(20, 'make a 5 second scene', policy)
        self.assertEqual((explicit.seconds, explicit.source, explicit.prompt_seconds, explicit.conflict), (20, 'explicit', 5, True))
        prompt = vd.resolve(None, 'make a 5 second scene', policy)
        self.assertEqual((prompt.seconds, prompt.source, prompt.conflict), (5, 'prompt', False))
        default = vd.resolve(None, 'a calm lake', policy)
        self.assertEqual((default.seconds, default.source), (2.0, 'default'))

    def test_invalid_and_too_long_are_errors_not_shortened(self):
        policy = vd.VideoPolicy()
        for value in (0, -3, float('nan'), float('inf'), '20', True):
            with self.assertRaises(vd.DurationError) as caught:
                vd.resolve(value, '', policy)
            self.assertEqual(caught.exception.code, 'video_duration_invalid', value)
        with self.assertRaises(vd.DurationError) as caught:
            vd.resolve(None, 'a 0.1 second video', policy)
        self.assertEqual(caught.exception.code, 'video_duration_invalid')
        for value in (181, 999999 * 3600, 10 ** 30):
            with self.assertRaises(vd.DurationError) as caught:
                vd.resolve(value, '', policy)
            self.assertEqual(caught.exception.code, 'video_duration_too_long')
        with self.assertRaises(vd.DurationError):
            vd.resolve(None, 'a 2 hour movie', policy)

    def test_limits_come_from_settings_within_hard_ceilings(self):
        policy = vd.VideoPolicy.from_settings({'media_video': {'max_duration_seconds': 600, 'default_duration_seconds': 5,
                                                               'long_video_warning_seconds': 60}})
        self.assertEqual((policy.max_seconds, policy.default_seconds, policy.warning_seconds), (600, 5, 60))
        self.assertEqual(vd.resolve(None, 'x', policy).seconds, 5)
        self.assertEqual(vd.resolve(300, 'x', policy).seconds, 300)
        ceiling = vd.VideoPolicy.from_settings({'media_video': {'max_duration_seconds': 10 ** 12}})
        self.assertEqual(ceiling.max_seconds, vd.HARD_MAX_SECONDS)
        broken = vd.VideoPolicy.from_settings({'media_video': {'max_duration_seconds': 'lots', 'default_duration_seconds': None}})
        self.assertEqual((broken.max_seconds, broken.default_seconds), (180.0, 2.0))
        self.assertEqual(vd.VideoPolicy.from_settings({}).max_seconds, 180.0)
        self.assertGreaterEqual(vd.VideoPolicy().max_seconds, 120, 'minute-scale requests are allowed by default')


class PlannerTests(unittest.TestCase):
    def test_segment_counts_and_exact_trim(self):
        for seconds, segments, frames in ((1, 1, 24), (2, 1, 48), (5, 3, 120), (10, 5, 240), (13, 7, 312), (20, 10, 480),
                                          (30, 15, 720), (60, 30, 1440), (120, 60, 2880)):
            plan = vd.plan(seconds)
            self.assertEqual((plan.segment_count, plan.total_frames), (segments, frames), seconds)
            self.assertEqual(sum(s.keep_frames for s in plan.segments), frames)
            self.assertAlmostEqual(plan.final_seconds, seconds, places=6)
            self.assertTrue(all(s.frames == vd.NATIVE_FRAMES for s in plan.segments), 'bounded native segments only')

    def test_continuation_drops_the_held_first_frame(self):
        plan = vd.plan(20)
        self.assertEqual(plan.continuation, 'last_frame')
        self.assertEqual([(s.keep_start, s.source) for s in plan.segments[:3]],
                         [(0, 'text'), (1, 'continuation'), (1, 'continuation')])
        self.assertEqual(plan.segments[-1].keep_frames, 480 - 49 - 48 * 8)
        animated = vd.plan(20, image=True)
        self.assertEqual((animated.mode, animated.segments[0].source), ('image_to_video', 'image'))

    def test_independent_segments_without_image_to_video(self):
        plan = vd.plan(5, continuation=False)
        self.assertEqual(plan.continuation, 'independent')
        self.assertEqual([s.keep_start for s in plan.segments], [0, 0, 0])
        self.assertEqual([s.source for s in plan.segments], ['text', 'text-independent', 'text-independent'])

    def test_default_stays_one_native_segment_without_reencoding(self):
        self.assertTrue(vd.plan(2.0).direct)
        self.assertTrue(vd.plan(49 / 24).direct)
        self.assertFalse(vd.plan(1).direct)
        self.assertFalse(vd.plan(5).direct)

    def test_absurd_requests_never_allocate(self):
        for value in (0, -1, float('nan'), float('inf'), 10 ** 12):
            with self.assertRaises(vd.DurationError):
                vd.plan(value)

    def test_estimates_only_from_measurements(self):
        self.assertIsNone(vd.estimate(10, []))
        self.assertIsNone(vd.estimate(10, [45.0]))
        self.assertEqual(vd.estimate(10, [44.7, 57.0, 45.1]), (447.0, 570.0))
        self.assertEqual([vd.label(v) for v in (2, 2.5, 20, 60, 90, 120)], ['2 s', '2.5 s', '20 s', '1 min', '1 min 30 s', '2 min'])


class ProtocolTests(unittest.TestCase):
    base = dict(conversation_id='22222222-2222-4222-8222-222222222222', mode='video', voice=None,
                messages=[dict(role='user', content='Generate a 20 second cinematic scene — café lights')],
                attachments=[dict(attachment_id='b' * 64, kind='image', mime='image/png', size=4321, name='Sky.png')])

    def test_duration_and_image_are_part_of_the_fingerprint(self):
        none = cp.start_fingerprint(self.base)
        five = cp.start_fingerprint(dict(self.base, options=dict(target_duration_ms=5000, duration_source='explicit')))
        twenty = cp.start_fingerprint(dict(self.base, options=dict(target_duration_ms=20000, duration_source='prompt')))
        other_image = cp.start_fingerprint(dict(self.base, attachments=[dict(self.base['attachments'][0], attachment_id='c' * 64)]))
        self.assertEqual(len({none, five, twenty, other_image}), 4)
        # Vectors shared with the Swift client (RemoteVideoTests).
        self.assertEqual(none, '74bc04bd810187ee7db16d7b310b5ccd000e8150c48a8b151fffb73754eaebe9')
        self.assertEqual(five, '8693619fc915e66887d761a7735ec6cf78822b7191cac690bd4f8e00c09aac7a')
        self.assertEqual(twenty, '5fbca25b6c6cf3096534fb7fc911465b5b32825e3002f4ad1ef029c20bd8b732')

    def test_options_are_validated_and_video_only(self):
        self.assertEqual(cp.start_options('video', {}), {})
        self.assertEqual(cp.start_options('video', {'target_duration_ms': 20000, 'duration_source': 'prompt'})['target_duration_ms'], 20000)
        for mode, value, code in (('normal', {}, 'invalid_request'), ('video', {'target_duration_ms': 0}, 'video_duration_invalid'),
                                  ('video', {'target_duration_ms': 20.5}, 'video_duration_invalid'),
                                  ('video', {'target_duration_ms': 10 ** 9}, 'video_duration_too_long'),
                                  ('video', {'target_duration_ms': 20000, 'output_path': '/tmp/x'}, 'invalid_request'),
                                  ('video', {'duration_source': 'prompt'}, 'invalid_request'),
                                  ('video', {'target_duration_ms': 20000, 'duration_source': 'guess'}, 'invalid_request'),
                                  ('video', [], 'invalid_request')):
            with self.assertRaises(ConnectError) as caught:
                cp.start_options(mode, value)
            self.assertEqual(str(caught.exception), code, (mode, value))

    def test_extensions_and_progress_are_bounded(self):
        self.assertEqual(cp.accepted(['mode_options/1', 'teleport/9']), ['mode_options/1'])
        for bad in ('mode_options/1', [1], ['x' * 41], ['A B'], ['a'] * 9):
            with self.assertRaises(ConnectError):
                cp.accepted(bad)
        self.assertEqual(cp.progress_item({'stage': 'segment', 'current': 3, 'total': 10}), {'stage': 'segment', 'current': 3, 'total': 10})
        for bad in (None, {'stage': 'rm -rf', 'current': 1, 'total': 1}, {'stage': 'segment', 'current': 11, 'total': 10},
                    {'stage': 'segment', 'current': 0, 'total': 10}, {'stage': 'segment', 'current': '1', 'total': 10}):
            self.assertIsNone(cp.progress_item(bad))

    def test_video_capability_is_integer_only_and_path_free(self):
        options = cp.video_options({'supports_text_to_video': True, 'supports_image_to_video': True, 'supports_audio': True,
                                    'native_segment_seconds': 49 / 24, 'fps': 24, 'max_images': 1, 'continuation': 'last_frame',
                                    'accepted_attachment_kinds': ['image', 'executable'],
                                    'duration': {'configurable': True, 'default_seconds': 2.0, 'minimum_seconds': 0.5,
                                                 'maximum_seconds': 180.0, 'long_video_warning_seconds': 30.0, 'presets': [2, 5, 20]}})
        self.assertEqual(options['native_segment_ms'], 2042)
        self.assertEqual(options['duration']['maximum_ms'], 180000)
        self.assertEqual(options['accepted_attachment_kinds'], ['image'])
        encoded = json.dumps(options)
        self.assertNotIn('.', re.sub(r'"[^"]*"', '', encoded), 'no fractional numbers on the wire')
        self.assertEqual(cp.video_options(None), {})


if __name__ == '__main__':
    unittest.main()
