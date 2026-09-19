"""Harmless end-to-end coding-services smoke test using a temporary project."""
from __future__ import annotations
from pathlib import Path
import subprocess,tempfile,sys
from olive.agent.coding_plan import CodingPlan
from olive.agent.tool_schema import ToolDefinition
from olive.services.checkpoint_service import CheckpointService
from olive.services.code_index_service import CodeIndexService
from olive.services.editing_service import EditingService,file_hash
from olive.services.repository_map_service import RepositoryMapService
from olive.workspace import Workspace

def run():
    with tempfile.TemporaryDirectory(prefix="olive-32-integration-") as temporary:
        root=Path(temporary);(root/"tests").mkdir();(root/"tests"/"__init__.py").write_text("",encoding="utf-8")
        source=root/"calculator.py";test=root/"tests"/"test_calculator.py"
        source.write_text("def add(left, right):\n    return left - right\n",encoding="utf-8")
        test.write_text("import unittest\nfrom calculator import add\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n",encoding="utf-8")
        workspace=Workspace("Integration",str(root),"python");index=CodeIndexService().index(root);repo_map=RepositoryMapService(CodeIndexService()).build(root)
        definition=ToolDefinition("code.replace_exact","Targeted edit","code",{"type":"object","required":["workspace","path","old","new"]},{"type":"object"},"medium",("filesystem.write",),True)
        plan=CodingPlan.parse({"goal":"Fix failing addition","workspace":workspace.id,"reasoning_summary":"The indexed add function subtracts","steps":[{"description":"Correct operator","tool":"code.replace_exact","arguments":{"workspace":workspace.id,"path":"calculator.py","old":"return left - right","new":"return left + right"},"purpose":"Make addition correct"}],"expected_files":["calculator.py"],"validation_strategy":["unittest"],"completion_conditions":["test_add passes"]},[definition])
        command=[sys.executable,"-B","-m","unittest","discover","-s","tests","-v"]
        before=subprocess.run(command,cwd=root,capture_output=True,text=True)
        checkpoints=CheckpointService(root/".checkpoints");checkpoints.create(workspace,"integration",["calculator.py"])
        EditingService(workspace).replace_exact("calculator.py",plan.steps[0].arguments["old"],plan.steps[0].arguments["new"],"integration",file_hash(source))
        after=subprocess.run(command,cwd=root,capture_output=True,text=True)
        updated=CodeIndexService().index(root)
        old_hash=next(item["content_hash"] for item in index["files"] if item["relative_path"]=="calculator.py")
        new_hash=next(item["content_hash"] for item in updated["files"] if item["relative_path"]=="calculator.py")
        return {"initial_failed":before.returncode!=0,"fixed_passed":after.returncode==0,"planned_steps":len(plan.steps),"repository_files":repo_map["file_count"]>=2,"index_refreshed":new_hash!=old_hash}

def main():
    result=run()
    for key,value in result.items():print(f"{key}: {value}")
    if not all(result.values()):raise SystemExit(1)

if __name__=="__main__":main()
