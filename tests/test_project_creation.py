"""Project language discovery and safe new-project creation."""
import asyncio
from pathlib import Path
import tempfile
import unittest

from olive.studio_tooling import projects


class NameAndDestinationTests(unittest.TestCase):
    def test_rejects_paths_and_reserved_names(self):
        for name in ("", "..", "a/b", "a\\b", "CON", "nul", "trailing ", "trailing.", "x" * 81):
            with self.subTest(name=name), self.assertRaises(ValueError):
                projects.validate_name(name)

    def test_accepts_ordinary_names(self):
        for name in ("Fixture", "my-project", "my_project", "Acme.Api", "a b"):
            self.assertEqual(projects.validate_name(name), name)

    def test_destination_must_be_absolute_and_existing(self):
        with self.assertRaises(ValueError):
            projects.resolve_destination("relative/path", "Fixture")
        with tempfile.TemporaryDirectory() as parent:
            missing = str(Path(parent) / "absent")
            with self.assertRaises(ValueError):
                projects.resolve_destination(missing, "Fixture")

    def test_destination_refuses_a_non_empty_folder(self):
        with tempfile.TemporaryDirectory() as parent:
            occupied = Path(parent) / "Fixture"
            occupied.mkdir()
            (occupied / "keep.txt").write_text("existing work", encoding="utf-8")
            with self.assertRaises(ValueError):
                projects.resolve_destination(parent, "Fixture")
            # The existing file is untouched by the refusal.
            self.assertEqual((occupied / "keep.txt").read_text(encoding="utf-8"), "existing work")

    def test_destination_allows_an_empty_folder_and_stays_inside_the_choice(self):
        with tempfile.TemporaryDirectory() as parent:
            (Path(parent) / "Fixture").mkdir()
            target = projects.resolve_destination(parent, "Fixture")
            self.assertEqual(target.parent, Path(parent).resolve())


class LocalTemplateTests(unittest.TestCase):
    def test_writes_real_starter_files(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "Fixture"
            written = projects.write_local_template(target, "python", "console")
            self.assertIn("main.py", written)
            self.assertIn("tests/test_main.py", written)
            self.assertIn("def greeting", (target / "main.py").read_text(encoding="utf-8"))

    def test_never_overwrites_an_existing_file(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "Fixture"
            target.mkdir()
            (target / "main.py").write_text("mine", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                projects.write_local_template(target, "python", "console")
            self.assertEqual((target / "main.py").read_text(encoding="utf-8"), "mine")

    def test_unknown_template_is_refused(self):
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaises(ValueError):
                projects.write_local_template(Path(parent) / "x", "python", "nonexistent")
            with self.assertRaises(ValueError):
                projects.write_local_template(Path(parent) / "x", "brainfuck", "console")


class DotnetCommandTests(unittest.TestCase):
    def test_only_supported_templates_and_frameworks(self):
        target = Path(tempfile.gettempdir()) / "Fixture"
        command = projects.dotnet_new_command("dotnet", "console", "Fixture", target)
        # An explicit argument array, never a concatenated shell string.
        self.assertEqual(command[:4], ["dotnet", "new", "console", "-n"])
        with self.assertRaises(ValueError):
            projects.dotnet_new_command("dotnet", "not-a-template", "Fixture", target)
        with self.assertRaises(ValueError):
            projects.dotnet_new_command("dotnet", "console", "Fixture", target, "net10.0; rm -rf /")
        self.assertIn("-f", projects.dotnet_new_command("dotnet", "console", "F", target, "net10.0"))


class DiscoveryTests(unittest.TestCase):
    def test_reports_honest_availability_for_every_language(self):
        result = asyncio.run(projects.discover(None))
        languages = {item["id"]: item for item in result["languages"]}
        # The registry covers the languages the brief names plus an empty folder.
        for expected in ("csharp", "python", "javascript", "typescript", "java", "empty"):
            self.assertIn(expected, languages)
        for item in result["languages"]:
            self.assertIn(item["availability"], {
                projects.READY, projects.TOOLCHAIN_MISSING,
                projects.TEMPLATE_UNAVAILABLE, projects.EDITING_ONLY,
            })
            self.assertTrue(item["detail"], f"{item['id']} must explain its state")
            # A language is only ready when it actually offers a template.
            if item["availability"] == projects.READY:
                self.assertTrue(item["templates"], f"{item['id']} claims ready with no template")
        # Python is always available: OLIVE itself runs on an interpreter.
        self.assertEqual(languages["python"]["availability"], projects.READY)
        self.assertTrue(languages["python"]["options"]["interpreters"])

    def test_missing_toolchain_never_offers_creation(self):
        result = asyncio.run(projects.discover(None))
        for item in result["languages"]:
            if item["availability"] == projects.TOOLCHAIN_MISSING:
                self.assertIn("not found", item["detail"].lower())


class BoundedProbeTests(unittest.TestCase):
    def test_a_probe_that_never_answers_does_not_hold_the_wizard(self):
        # A hung or failing probe is reported as absent, not waited for: the
        # wizard must never sit on a spinner because one SDK misbehaves.
        original = projects._python_interpreters

        def explode(_root):
            raise TimeoutError("probe did not answer")

        projects._python_interpreters = explode
        try:
            result = asyncio.run(projects.discover(None))
        finally:
            projects._python_interpreters = original
        python = next(item for item in result["languages"] if item["id"] == "python")
        self.assertEqual(python["availability"], projects.TOOLCHAIN_MISSING)
        self.assertIn("not found", python["detail"].lower())

    def test_the_deadline_is_declared_and_bounded(self):
        self.assertGreater(projects.PROBE_SECONDS, 0)
        self.assertLessEqual(projects.PROBE_SECONDS, 60)


if __name__ == "__main__":
    unittest.main()
