"""Strict, schema-validated code edit proposals.

The coding model PROPOSES edits in this shape. OLIVE decides whether each one
is valid: paths are workspace-relative and re-resolved, replacements must target
text OLIVE actually read, and no field can carry permissions, confirmations,
commands or other authority. Anything unexpected rejects the whole proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import json
import re

ACTIONS = ("replace", "create", "rewrite")
MAX_EDITS = 12
MAX_TEXT = 80_000
FIELDS = {"action", "path", "find", "replace", "content"}
REQUIRED = {"replace": {"find", "replace"}, "create": {"content"}, "rewrite": {"content"}}
# Fields that look like authority are refused wherever they appear.
AUTHORITY_WORDS = {"approved", "approval", "owner_mode", "permission", "permissions", "confirm", "confirmation",
                   "grant", "grant_root", "sudo", "command", "commands", "shell", "execute", "disable_stop"}

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "edits"],
    "properties": {
        "summary": {"type": "string", "description": "One or two factual sentences describing the change."},
        "edits": {"type": "array", "maxItems": MAX_EDITS, "items": {
            "type": "object", "additionalProperties": False, "required": ["action", "path"],
            "properties": {
                "action": {"enum": list(ACTIONS)},
                "path": {"type": "string", "description": "Workspace-relative path using forward slashes."},
                "find": {"type": "string", "description": "replace: exact existing text, copied verbatim, that occurs once in the file."},
                "replace": {"type": "string", "description": "replace: the new text for that block."},
                "content": {"type": "string", "description": "create/rewrite: the complete file content."}}}}}}


@dataclass(frozen=True, slots=True)
class Edit:
    action: str
    path: str
    find: str = ""
    replace: str = ""
    content: str = ""


@dataclass(frozen=True, slots=True)
class EditProposal:
    summary: str
    edits: tuple[Edit, ...]


def _path(value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 400:
        raise ValueError("Invalid proposed path")
    value = value.strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    pure = PurePosixPath(value)
    if (pure.is_absolute() or re.match(r"^[A-Za-z]:", value) or ".." in pure.parts or value.startswith("~")
            or any(ch in value for ch in "\0\n\r$`") or not pure.parts):
        raise ValueError("Proposed paths must be relative to the workspace")
    if any(part in {".git", ".ssh", ".gnupg", "node_modules", "bin", "obj", ".venv", "venv"} for part in pure.parts):
        raise ValueError("Proposed path targets a protected or generated folder")
    return pure.as_posix()


def parse(raw, *, read_files: dict[str, str], existing: set[str]) -> EditProposal:
    """Validate a model proposal against what OLIVE actually read.

    read_files: workspace-relative path -> the complete text OLIVE read (or the
    visible excerpt, for large files). existing: paths known to exist.
    """
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict) or set(value) != {"summary", "edits"}:
        raise ValueError("Proposal fields must be exactly summary and edits")
    summary, edits = value["summary"], value["edits"]
    if not isinstance(summary, str) or len(summary) > 1000:
        raise ValueError("Invalid proposal summary")
    if not isinstance(edits, list) or len(edits) > MAX_EDITS:
        raise ValueError("Invalid edit list")
    parsed, seen = [], {}
    for item in edits:
        if not isinstance(item, dict) or set(item) - FIELDS or not {"action", "path"} <= set(item):
            raise ValueError("Unknown or missing edit field")
        if AUTHORITY_WORDS & {str(k).casefold() for k in item}:
            raise ValueError("Edit proposals cannot carry authority")
        action = item["action"]
        if action not in ACTIONS:
            raise ValueError("Unknown edit action")
        path = _path(item["path"])
        needed = REQUIRED[action]
        for key in FIELDS - {"action", "path"}:
            if key in item and not isinstance(item[key], str):
                raise ValueError("Edit text fields must be strings")
            if key in item and key not in needed and item[key] != "":
                raise ValueError(f"Field {key} is not valid for {action}")
            if key in item and len(item[key]) > MAX_TEXT:
                raise ValueError("Proposed text is too large")
        if any(key not in item for key in needed):
            raise ValueError(f"{action} requires {', '.join(sorted(needed))}")
        folded = path.casefold()
        earlier = seen.get(folded, [])
        if earlier and (action in {"create", "rewrite"} or {"create", "rewrite"} & set(earlier)):
            raise ValueError("A created or rewritten file cannot receive other edits in the same proposal")
        if action == "create":
            if folded in {p.casefold() for p in existing}:
                raise ValueError("create would overwrite an existing file")
        else:
            if path not in read_files:
                raise ValueError("Edits may only change files OLIVE has read in this task")
            if action == "replace":
                if not item["find"] or item["find"] == item["replace"]:
                    raise ValueError("replace needs distinct non-empty text")
                if read_files[path].count(item["find"]) != 1:
                    raise ValueError(f"The text to replace must occur exactly once in {path}")
        seen.setdefault(folded, []).append(action)
        parsed.append(Edit(action, path, item.get("find", ""), item.get("replace", ""), item.get("content", "")))
    return EditProposal(summary.strip(), tuple(parsed))
