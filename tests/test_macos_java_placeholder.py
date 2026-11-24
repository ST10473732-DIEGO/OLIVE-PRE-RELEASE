"""macOS /usr/bin/java and javac are placeholders: never treat them as an installed JDK."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olive.studio_tooling import toolchain


class MacJavaPlaceholderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.jdk = Path(self.temp.name) / "jdk"
        (self.jdk / "bin").mkdir(parents=True)
        for tool in ("java", "javac"):
            path = self.jdk / "bin" / tool
            path.write_text("#!/bin/sh\n")
            path.chmod(0o755)

    def resolve(self, java_home_result):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return java_home_result

        env = {k: v for k, v in os.environ.items() if k != "JAVA_HOME"}
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, env, clear=True), \
                patch.object(toolchain.shutil, "which", lambda name: "/usr/bin/javac"), \
                patch.object(toolchain.subprocess, "run", run), \
                patch.object(toolchain, "toolchain_roots", lambda: [Path(self.temp.name) / "none"]):
            return toolchain.java_executable("javac"), calls

    def test_placeholder_without_a_jdk_is_not_a_jdk(self):
        missing = subprocess.CompletedProcess(["/usr/libexec/java_home"], 1, "", "Unable to locate a Java Runtime.")
        found, calls = self.resolve(missing)
        self.assertIsNone(found)
        self.assertEqual(calls, [["/usr/libexec/java_home"]])  # /usr/bin/javac itself never ran.

    def test_java_home_jdk_is_used_behind_the_placeholder(self):
        present = subprocess.CompletedProcess(["/usr/libexec/java_home"], 0, str(self.jdk) + "\n", "")
        found, _ = self.resolve(present)
        self.assertEqual(found, str(self.jdk / "bin" / "javac"))


if __name__ == "__main__":
    unittest.main()
