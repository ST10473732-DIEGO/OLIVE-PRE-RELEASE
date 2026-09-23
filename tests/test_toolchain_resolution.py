"""Discovery and execution must agree without a login-shell PATH."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from olive.studio_tooling import toolchain


class ToolchainResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def executable(self, relative):
        path = self.root / relative / toolchain._binary("dotnet") if relative.endswith("dotnet") else self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
        path.chmod(0o755)
        return str(path)

    def jdk(self):
        for name in ("java", "javac"):
            self.executable(".toolchains/jdk/bin/" + toolchain._binary(name))

    def test_local_tools_work_without_path_and_do_not_copy_secrets(self):
        dotnet = self.executable(".toolchains/dotnet")
        self.jdk()
        with patch.object(toolchain, "REPOSITORY", self.root), patch.dict(os.environ, {"SECRET_TOKEN": "private"}, clear=True), patch.object(toolchain.shutil, "which", return_value=None):
            self.assertEqual(toolchain.dotnet_executable(), dotnet)
            source = {"PATH": "system"}
            result = toolchain.developer_environment(source)
            self.assertEqual(source, {"PATH": "system"})
            self.assertNotIn("SECRET_TOKEN", result)
            self.assertEqual(result["JAVA_HOME"], str(self.root / ".toolchains/jdk"))
            self.assertIn(str(Path(dotnet).parent), result["PATH"].split(os.pathsep))

    def test_explicit_missing_roots_do_not_silently_select_other_installations(self):
        self.executable(".toolchains/dotnet")
        self.jdk()
        with patch.object(toolchain, "REPOSITORY", self.root), patch.dict(os.environ, {"DOTNET_ROOT": str(self.root / "missing"), "JAVA_HOME": str(self.root / "missing")}, clear=True):
            self.assertIsNone(toolchain.dotnet_executable())
            self.assertIsNone(toolchain.java_executable())

    def test_runtime_without_compiler_is_not_a_jdk(self):
        self.executable(".toolchains/jdk/bin/" + toolchain._binary("java"))
        with patch.object(toolchain, "REPOSITORY", self.root), patch.dict(os.environ, {}, clear=True), patch.object(toolchain.shutil, "which", return_value=None):
            self.assertIsNone(toolchain.java_executable())

    def test_refresh_clears_negative_module_results(self):
        toolchain._MODULE_CACHE[("fixture", "module")] = False
        toolchain.clear_probe_cache()
        self.assertNotIn(("fixture", "module"), toolchain._MODULE_CACHE)
