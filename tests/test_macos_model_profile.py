"""The Mac Studio Preview model profile is opt-in; release presets stay manifest-exact."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from olive.services import model_policy, presets

ROOT = Path(__file__).resolve().parents[1]
GPT_OSS = "f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe"


class MacModelProfileTests(unittest.TestCase):
    def test_profile_needs_both_macos_and_the_packaged_app_flag(self):
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {"OLIVE_MACOS_MODEL_PROFILE": "1"}):
            self.assertTrue(model_policy.macos_model_profile())
        with patch.object(sys, "platform", "linux"), patch.dict(os.environ, {"OLIVE_MACOS_MODEL_PROFILE": "1"}):
            self.assertFalse(model_policy.macos_model_profile())
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {}, clear=True):
            self.assertFalse(model_policy.macos_model_profile())

    @unittest.skipIf(presets.MACOS_PROFILE, "this process was started with the Mac profile")
    def test_release_presets_are_the_default(self):
        self.assertEqual(presets.profile_presets(False), presets.PRESETS)
        self.assertEqual(presets.PRESETS["fast"]["model"], "qwen3:8b")
        self.assertEqual(presets.THINKING, presets.RELEASE_THINKING)

    def test_mac_profile_is_exactly_the_qualified_mac_models(self):
        mac = presets.profile_presets(True)
        self.assertEqual(mac["fast"]["model"], "qwen3.5:4b-q4_K_M")
        self.assertEqual(mac["fast"]["pinned_digest"], "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04")
        self.assertEqual(mac["fast"]["params"], {"temperature": .3, "max_tokens": 4096})
        self.assertEqual((mac["normal"]["model"], mac["normal"]["pinned_digest"]), ("gpt-oss:20b", GPT_OSS))
        self.assertEqual(mac["normal"]["params"], {"temperature": .35, "max_tokens": 4096})
        self.assertEqual((mac["max"]["model"], mac["max"]["pinned_digest"], mac["max"]["role"]), ("gpt-oss:20b", GPT_OSS, "coding"))
        self.assertEqual(mac["max"]["params"], {"temperature": .2, "max_tokens": 8192})
        self.assertEqual((mac["deep"]["model"], mac["deep"]["pinned_digest"]), ("gpt-oss:20b", GPT_OSS))
        # Presets without a Mac entry are identical on both profiles.
        for key in set(mac) - set(presets.MACOS_PRESET_PROFILE):
            self.assertEqual(mac[key], presets.PRESETS[key])
        self.assertEqual(presets.MACOS_THINKING["max"], "high")
        self.assertEqual(presets.MACOS_THINKING["deep"], "medium")
        self.assertEqual(model_policy.MACOS_CANDIDATES["fast"][0], "qwen3.5:4b-q4_K_M")
        self.assertEqual(model_policy.MACOS_CANDIDATES["vision"][0], "qwen3.5:9b")

    @unittest.skipUnless(sys.platform == "darwin", "the profile only exists on macOS")
    def test_packaged_flag_applies_the_profile_everywhere_presets_are_read(self):
        code = ("import json; from olive.services import presets, model_policy; "
                "print(json.dumps([presets.PRESETS['fast']['model'], presets.PRESETS['max']['model'], "
                "presets.THINKING['max'], model_policy.CANDIDATES['fast'][0]]))")
        env = {**os.environ, "OLIVE_MACOS_MODEL_PROFILE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        output = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                                text=True, check=True).stdout
        self.assertEqual(json.loads(output), ["qwen3.5:4b-q4_K_M", "gpt-oss:20b", "high", "qwen3.5:4b-q4_K_M"])


if __name__ == "__main__":
    unittest.main()
