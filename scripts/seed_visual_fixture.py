"""Isolated visual-QA fixture: realistic edge cases layered on the standard demo data.

Long titles, long paths, Unicode, large code blocks, wide tables and many rows.
Refuses existing or non-temporary profiles exactly like seed_electron_fixture.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LONG_TITLE = (
    "Fixture · a deliberately long conversation title about migrating the greenhouse "
    "irrigation controller firmware to the new scheduling model (2026 revision)"
)
CODE = "\n".join(
    [
        "from dataclasses import dataclass, field",
        "from typing import Iterable",
        "",
        "",
        "@dataclass",
        "class Zone:",
        "    name: str",
        "    minutes: int",
        "    days: tuple[str, ...] = ('Mon', 'Wed', 'Fri')",
        "    history: list[float] = field(default_factory=list)",
        "",
        "    def schedule(self) -> Iterable[str]:",
        "        for day in self.days:",
        "            yield f'{day}: {self.minutes} minutes for {self.name}'",
        "",
    ]
    + [f"zone_{i} = Zone('bed-{i:02d}', minutes={5 + i % 7})" for i in range(1, 41)]
    + [
        "",
        "if __name__ == '__main__':",
        "    for line in zone_1.schedule():",
        "        print(line)  # a very long trailing comment that keeps going past the usual reading width to test horizontal scrolling inside code blocks only",
    ]
)
TABLE = "\n".join(
    ["| Zone | Mon | Tue | Wed | Thu | Fri | Sat | Sun | Notes |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    + [
        f"| bed-{i:02d} | {i}m | – | {i + 2}m | – | {i + 1}m | – | – | Shade cloth after 14:00; check emitters weekly; 日本語メモ |"
        for i in range(1, 9)
    ]
)
ASSISTANT = (
    "Here is a plan that covers the schedule, the data model and the tests.\n\n"
    "## Data model\n\n```python\n" + CODE + "\n```\n\n"
    "## Weekly schedule\n\n" + TABLE + "\n\n"
    "## Notes\n\n"
    "- Unicode is expected everywhere: café, naïve, Straße, 東京, العربية, emoji 🌱🫒.\n"
    "- A long unbroken reference: https://example.invalid/documentation/irrigation/controllers/firmware/v2/scheduling-model/appendix/very-long-path-segment-that-does-not-break/index.html\n"
    "- Nested lists\n  - keep their indentation\n    - at three levels\n\n"
    "> Blockquotes stay readable and do not overflow the reading width.\n\n"
    "This is synthetic demonstration content, not a model response or execution result."
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile")
    args = parser.parse_args()
    profile = Path(args.profile).resolve()
    if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()) or any(profile.iterdir()):
        raise ValueError("Use an empty temporary profile for synthetic fixtures")
    import seed_electron_fixture  # noqa: E402  (same directory)

    sys.argv = [sys.argv[0], str(profile)]
    import io
    from contextlib import redirect_stdout

    captured = io.StringIO()
    with redirect_stdout(captured):
        seed_electron_fixture.main()
    base = json.loads(captured.getvalue())
    os.environ["OLIVE_DATA_DIR"] = str(profile)
    from olive.models import Chat
    from olive.storage.chat_repository import ChatRepository
    from olive.storage.workspace_repository import WorkspaceRepository
    from olive.workspace import Workspace

    # A second workspace with a long nested path and long file names.
    deep = profile / "fixture-long" / "very" / "long" / "nested" / "directory" / "structure" / "for" / "the" / "explorer"
    deep.mkdir(parents=True)
    (deep / "a_very_long_module_name_that_tests_tab_and_explorer_wrapping_behaviour.py").write_text(
        '"""Long path fixture."""\n\n\ndef value():\n    return 42\n', encoding="utf-8"
    )
    (profile / "fixture-long" / "README.md").write_text("# Long path fixture\n\nSynthetic.\n", encoding="utf-8")
    (profile / "fixture-long" / "tests").mkdir()
    (profile / "fixture-long" / "tests" / "test_value.py").write_text(
        "import unittest\nimport sys\nsys.path.insert(0, 'very/long/nested/directory/structure/for/the/explorer')\n"
        "from a_very_long_module_name_that_tests_tab_and_explorer_wrapping_behaviour import value\n\n"
        "class ValueTests(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 42)\n",
        encoding="utf-8",
    )
    long_workspace = Workspace(
        title="Fixture · greenhouse irrigation controller firmware (a long workspace title for the header)",
        root_path=str(profile / "fixture-long"),
        trust_level="approved",
    )
    repo = WorkspaceRepository(profile / "workspaces.json")
    repo.save(long_workspace)

    chats = ChatRepository(profile / "chats.json")
    existing = chats.load_all()
    long_chat = Chat(title=LONG_TITLE, model="qwen3:8b")
    long_chat.add_message(
        "user",
        "Can you design the scheduling model for the irrigation controller?\n\nConstraints:\n"
        "1. Forty zones\n2. Per-day minutes\n3. Keep the history\n\nAlso handle names like Straße and 東京.",
    )
    long_chat.add_message("assistant", ASSISTANT)
    long_chat.add_message("user", "Short follow-up.")
    long_chat.add_message("assistant", "A short answer. This is synthetic demonstration content.")
    short_chat = Chat(title="Q", model="qwen3:8b")
    short_chat.add_message("user", "Hi")
    short_chat.add_message("assistant", "Hello. Synthetic content only.")
    chats.save_all([*existing.values(), long_chat, short_chat])
    print(json.dumps({**base, "long_workspace_id": long_workspace.id, "long_chat_id": long_chat.id}))


if __name__ == "__main__":
    main()
