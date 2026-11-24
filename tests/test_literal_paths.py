"""Literal paths with spaces ("/Volumes/Data Drive/...", "~/My Documents/...")."""
import tempfile
import unittest
from pathlib import Path

from olive.authority.owner import OwnerPolicy, owner_identity
from olive.interaction.deliverable import direct_deliverable, instruction_text
from olive.interaction.literal_paths import literal_paths, mask_paths
from olive.interaction.ordinary_requests import directory_request, file_transfer
from olive.studio_tooling.pty import program_terminal_supported


class LiteralPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Data Drive" / "My Documents"
        self.root.mkdir(parents=True)
        self.file = self.root / "report final.txt"
        self.file.write_text("x")
        settings = {"owner_mode": True, "owner_installation": {"id": "fixture", "owner": owner_identity()}}
        self.policy = OwnerPolicy(lambda: settings)

    def test_paths_without_spaces_read_exactly_as_before(self):
        self.assertEqual(literal_paths("Move /tmp/a.txt to /tmp/b.txt"), ["/tmp/a.txt", "/tmp/b.txt"])
        self.assertEqual(literal_paths("Delete ~/x.log please"), ["~/x.log"])
        self.assertEqual(file_transfer("Move /tmp/a.txt to /tmp/b.txt")["steps"][0]["entities"],
                         {"path": "/tmp/a.txt", "destination": "/tmp/b.txt"})

    def test_existing_and_new_paths_with_spaces(self):
        new = self.root / "copy.txt"
        self.assertEqual(literal_paths(f"Copy {self.file} to {new}"), [str(self.file), str(new)])
        self.assertEqual(file_transfer(f"Copy {self.file} to {new}")["steps"][0]["entities"],
                         {"path": str(self.file), "destination": str(new)})
        self.assertEqual(file_transfer(f"Delete {self.file}")["steps"][0]["entities"], {"path": str(self.file)})
        folder = self.root / "Reports"
        self.assertEqual(directory_request(f"Create a folder at {folder}.")["steps"][0]["entities"], {"path": str(folder)})

    def test_connecting_words_and_trailing_words_never_join_a_new_name(self):
        new = self.root / "b.txt"
        self.assertEqual(literal_paths(f"Copy {self.file} to {new} and then tell me"), [str(self.file), str(new)])
        self.assertEqual(literal_paths(f"Delete {self.file} please"), [str(self.file)])

    def test_path_words_are_data_not_instructions(self):
        folder = Path(self.temp.name) / "Application Support" / "tests and copy"
        folder.mkdir(parents=True)
        text = f"Create a folder at {folder / 'Reports'}"
        self.assertNotIn("application", instruction_text(text))
        self.assertNotIn("copy", instruction_text(text))
        self.assertIsNone(direct_deliverable(text, {}))  # Not mistaken for a request for code.
        self.assertEqual(mask_paths(text)[1], [str(folder / "Reports")])

    def test_owner_grants_bind_the_full_spaced_path(self):
        target = self.root / "moved.txt"
        with self.policy.request(f"Move {self.file} to {target}", "chat", local=True) as grant:
            self.assertEqual((grant.source, grant.destination), (str(self.file.resolve()), str(target.resolve())))
            self.assertTrue(self.policy.authorize("filesystem.move", {"path": str(self.file), "destination": str(target)}))
            self.assertFalse(self.policy.authorize("filesystem.move", {"path": str(self.root), "destination": str(target)}))

    def test_programs_run_in_the_terminal_where_studio_has_one(self):
        for platform in ("linux", "darwin", "win32"):
            self.assertTrue(program_terminal_supported(platform))
        self.assertFalse(program_terminal_supported("freebsd"))


if __name__ == "__main__":
    unittest.main()
