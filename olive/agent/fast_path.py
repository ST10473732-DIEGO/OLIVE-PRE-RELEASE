from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import ast
import operator
import re
from pathlib import Path

from .planner import PlannedAction


@dataclass(slots=True)
class FastPathResult:
    level: int
    answer: str | None = None
    action: PlannedAction | None = None


class FastPathService:
    def resolve(self, request: str) -> FastPathResult | None:
        text = request.strip()
        match = re.fullmatch(r"(?:what is\s+)?([0-9+\-*/().\s]+)\??", text, re.I)
        if match:
            try: return FastPathResult(0, answer=str(_safe_math(match.group(1))))
            except (ValueError, ZeroDivisionError): pass
        match = re.fullmatch(r"(?:show|open)\s+(?:my\s+)?(downloads|desktop|documents)(?:\s+folder)?", text, re.I)
        if match:
            target = Path.home() / match.group(1).title()
            return FastPathResult(0, action=PlannedAction("system.open_path", {"path":str(target)}, "Open local folder"))
        match = re.fullmatch(r"create\s+(?:a\s+)?folder\s+named\s+([\w .-]+)\s+on\s+(?:my\s+)?desktop", text, re.I)
        if match:
            name=match.group(1).strip().strip(".")
            if name and name not in {"..","."}:
                return FastPathResult(0, action=PlannedAction("filesystem.create_directory", {"path":str(Path.home()/"Desktop"/name)}, "Create desktop folder"))
        match = re.fullmatch(r"open\s+([\w .-]+)", text, re.I)
        if match: return FastPathResult(0, action=PlannedAction("system.open_application", {"application": match.group(1).strip()}, "Open application"))
        match = re.fullmatch(r"(?:terminate|kill|force\s+close|end)\s+([\w .-]+)", text, re.I)
        if match: return FastPathResult(0, action=PlannedAction("system.terminate_application", {"application": match.group(1).strip()}, "Forcefully terminate application process tree"))
        match = re.fullmatch(r"(?:close|quit|exit)\s+([\w .-]+)", text, re.I)
        if match: return FastPathResult(0, action=PlannedAction("system.close_application", {"application": match.group(1).strip()}, "Close running application"))
        return None


def _safe_math(expression: str):
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
                  ast.USub: operator.neg, ast.UAdd: operator.pos}
    def walk(node):
        if isinstance(node, ast.Expression): return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return Decimal(str(node.value))
        if isinstance(node, ast.BinOp) and type(node.op) in operations: return operations[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in operations: return operations[type(node.op)](walk(node.operand))
        raise ValueError("Unsupported expression")
    result = walk(ast.parse(expression, mode="eval"))
    return int(result) if result == int(result) else result.normalize()
