from __future__ import annotations

import asyncio
from fnmatch import fnmatch
from pathlib import Path
import shutil
import time

from ..agent.tool_result import ArtifactReference, ToolResult
from ..agent.tool_schema import ToolContext, ToolDefinition

MAX_READ_BYTES = 1024 * 1024


def _path(value) -> Path: return Path(str(value)).expanduser().resolve(strict=False)


class FilesystemTool:
    def __init__(self, action, permissions, risk="low", confirmation=False):
        self.action = action
        self.definition = ToolDefinition(f"filesystem.{action}", f"{action.replace('_',' ').title()} on the local filesystem",
            "filesystem", {"type":"object", "required":["path"] + (["destination"] if action in {"copy","move"} else [])},
            risk_level=risk, required_permissions=tuple(permissions),
            confirmation_required=confirmation, timeout_seconds=60)

    async def execute(self, arguments, context): return await asyncio.to_thread(self._execute, arguments)

    def _execute(self, a):
        source = _path(a["path"])
        if self.action == "list":
            if not source.is_dir(): raise NotADirectoryError(source)
            entries = [{"name": p.name, "path": str(p), "is_directory": p.is_dir()} for p in sorted(source.iterdir(), key=lambda x:x.name.lower())[:1000]]
            return ToolResult(True, f"Listed {len(entries)} entries", {"entries": entries})
        if self.action == "search":
            if not source.is_dir(): raise NotADirectoryError(source)
            pattern = a.get("pattern", "*"); recursive = bool(a.get("recursive", True)); limit = min(1000, max(1,int(a.get("limit",100))))
            after, before = a.get("after_ns"), a.get("before_ns")
            basis = a.get("time_basis", "modified")
            if basis not in {"modified", "created"} or any(value is not None and type(value) is not int for value in (after, before)):
                raise ValueError("Invalid timestamp search constraints")
            if after is not None and before is not None and before <= after:
                raise ValueError("Invalid timestamp search range")
            iterator = source.rglob("*") if recursive else source.glob("*")
            matches, truncated = [], False
            deadline = time.monotonic() + 5
            for visited, path in enumerate(iterator):
                if visited >= 20000 or time.monotonic() >= deadline:
                    truncated = True
                    break
                if fnmatch(path.name, pattern):
                    if a.get("files_only") and not path.is_file():
                        continue
                    if after is not None or before is not None:
                        stat = path.stat()
                        stamp = getattr(stat, "st_birthtime_ns", None) if basis == "created" else stat.st_mtime_ns
                        if stamp is None:
                            raise ValueError("This filesystem does not expose creation dates")
                        if (after is not None and stamp < after) or (before is not None and stamp >= before):
                            continue
                    matches.append(str(path))
                    if len(matches) >= limit:
                        truncated = True
                        break
            return ToolResult(True, f"Found {len(matches)} paths", {"paths": matches, "truncated": truncated})
        if self.action == "stat":
            if a.get("allow_missing") and not source.exists():
                return ToolResult(True, "The path does not exist", {"exists": False, "is_directory": False, "is_file": False})
            stat = source.stat(); return ToolResult(True, f"Inspected {source.name}", {"path":str(source),"size":stat.st_size,"is_file":source.is_file(),"is_directory":source.is_dir(),"modified_ns":stat.st_mtime_ns,
                "created_ns": getattr(stat, "st_birthtime_ns", None)})
        if self.action == "read_text":
            if not source.is_file(): raise FileNotFoundError(source)
            offset=max(0,int(a.get("offset",0))); length=min(MAX_READ_BYTES,max(1,int(a.get("length",MAX_READ_BYTES))))
            with source.open("rb") as handle: handle.seek(offset); raw=handle.read(length)
            if b"\x00" in raw: return ToolResult.failure("File appears to be binary", "BinaryFile")
            return ToolResult(True, f"Read {len(raw)} bytes", {"text":raw.decode(a.get("encoding","utf-8"),errors="replace"),"offset":offset,"bytes":len(raw),"truncated":source.stat().st_size>offset+len(raw)})
        if self.action == "create_directory": source.mkdir(parents=bool(a.get("parents",True)),exist_ok=bool(a.get("exist_ok",False))); return ToolResult(True,f"Created {source}",artifacts=[ArtifactReference(str(source),"directory")])
        if self.action == "write_text":
            if source.exists() and not a.get("overwrite",False): return ToolResult.failure("Target exists; overwrite was not approved", "TargetExists")
            source.parent.mkdir(parents=True,exist_ok=True); source.write_text(str(a.get("text","")),encoding=a.get("encoding","utf-8")); return ToolResult(True,f"Wrote {source.name}",artifacts=[ArtifactReference(str(source))])
        if self.action == "delete":
            if source.is_dir(): source.rmdir()
            else: source.unlink()
            return ToolResult(True,f"Deleted {source.name}")
        if self.action == "trash":
            # Single ordinary file only. No permanent-delete fallback, recursive
            # directory removal or shell interpolation when Trash is unavailable.
            import os
            raw = Path(a['path']).expanduser()
            if set(a) != {'path'} or any(p.is_symlink() for p in (raw,*raw.parents)) or not source.is_file():
                raise PermissionError('Trash requires one regular file without symbolic links')
            if hasattr(os,'getuid') and source.stat().st_uid != os.getuid():
                raise PermissionError('The file belongs to another user')
            from send2trash import send2trash
            send2trash(str(source))
            if source.exists():raise OSError('Trash did not remove the original path')
            return ToolResult(True, 'The requested file was moved to Trash.', {'trashed':True})
        destination = _path(a["destination"])
        if destination.exists() and not a.get("overwrite",False): return ToolResult.failure("Destination exists; overwrite was not approved", "TargetExists")
        if self.action == "copy":
            if source.is_dir(): shutil.copytree(source,destination,dirs_exist_ok=bool(a.get("overwrite",False)))
            else: destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,destination)
            return ToolResult(True,f"Copied to {destination}",artifacts=[ArtifactReference(str(destination))])
        if self.action == "move": destination.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(source),str(destination)); return ToolResult(True,f"Moved to {destination}",artifacts=[ArtifactReference(str(destination))])
        raise ValueError(self.action)


def filesystem_tools():
    return [FilesystemTool("list",("filesystem.read",)), FilesystemTool("search",("filesystem.read",)),
            FilesystemTool("stat",("filesystem.read",)), FilesystemTool("read_text",("filesystem.read",)),
            FilesystemTool("create_directory",("filesystem.write",),"medium"), FilesystemTool("write_text",("filesystem.write",),"medium"),
            FilesystemTool("copy",("filesystem.read","filesystem.write"),"medium"),
            FilesystemTool("move",("filesystem.read","filesystem.write"),"high",True),
            FilesystemTool("trash",("filesystem.delete",),"medium",True),
            FilesystemTool("delete",("filesystem.delete",),"critical",True)]
