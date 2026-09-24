import tempfile, unittest
from pathlib import Path
from olive.agent.tool_schema import ToolContext
from olive.tools.filesystem import filesystem_tools

class FilesystemTests(unittest.IsolatedAsyncioTestCase):
    async def test_trash_has_no_permanent_delete_fallback_and_refuses_directories(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'owned.txt';source.write_text('owned')
            tool=next(t for t in filesystem_tools() if t.action=='trash')
            with patch('send2trash.send2trash',side_effect=PermissionError('Trash unavailable')):
                with self.assertRaises(PermissionError):await tool.execute({'path':str(source)},ToolContext('owned'))
            self.assertEqual(source.read_text(),'owned')
            with self.assertRaises(PermissionError):await tool.execute({'path':str(root)},ToolContext('owned'))

    async def test_delete_requires_no_destination_and_preserves_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.txt"
            path.write_text("Fixture")
            tool = next(tool for tool in filesystem_tools() if tool.action == "delete")
            with self.assertRaises(OSError):
                await tool.execute({"path": tmp}, ToolContext("fixture"))
            self.assertTrue(path.exists())
            self.assertTrue((await tool.execute({"path": str(path)}, ToolContext("fixture"))).success)
            self.assertFalse(path.exists())

    async def test_search_stops_at_requested_match_limit(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            visited = []
            def paths(*args):
                for index in range(100):
                    visited.append(index)
                    yield Path(tmp) / f"fixture{index}.txt"
            tool = next(tool for tool in filesystem_tools() if tool.action == "search")
            with patch.object(Path, "rglob", paths):
                result = await tool.execute({"path": tmp, "limit": 2}, ToolContext("fixture"))
            self.assertEqual(len(result.data["paths"]), 2)
            self.assertEqual(len(visited), 2)
            self.assertTrue(result.data["truncated"])

    async def test_write_read_search_copy_move_and_safe_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tools={tool.definition.name:tool for tool in filesystem_tools()}; context=ToolContext("t")
            target=root/"a.txt"
            self.assertTrue((await tools["filesystem.write_text"].execute({"path":str(target),"text":"hello"},context)).success)
            self.assertEqual((await tools["filesystem.read_text"].execute({"path":str(target)},context)).data["text"],"hello")
            self.assertFalse((await tools["filesystem.write_text"].execute({"path":str(target),"text":"no"},context)).success)
            found=await tools["filesystem.search"].execute({"path":str(root),"pattern":"*.txt"},context); self.assertEqual(len(found.data["paths"]),1)
            copied=root/"b.txt"; await tools["filesystem.copy"].execute({"path":str(target),"destination":str(copied)},context)
            moved=root/"c.txt"; await tools["filesystem.move"].execute({"path":str(copied),"destination":str(moved)},context)
            self.assertTrue(moved.exists())
    async def test_binary_and_bounded_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"x.bin"; path.write_bytes(b"a\x00b")
            tool={x.definition.name:x for x in filesystem_tools()}["filesystem.read_text"]
            self.assertEqual((await tool.execute({"path":str(path)},ToolContext("t"))).error_type,"BinaryFile")
