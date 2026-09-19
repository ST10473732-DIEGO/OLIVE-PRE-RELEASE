from __future__ import annotations

import asyncio
from pathlib import Path
import re

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition

_ADMIN = re.compile(r"(?i)\b(runAs|Start-Process.+-Verb\s+RunAs|net\s+(user|localgroup)|bcdedit|diskpart)\b")
_DESTRUCTIVE = re.compile(r"(?i)\b(Remove-Item|del|erase|rmdir|rd|format|Clear-Disk|git\s+reset\s+--hard)\b")


class TerminalRunTool:
    definition = ToolDefinition("terminal.run", "Run a bounded command in PowerShell, CMD, or Python", "terminal",
        {"type":"object","required":["environment","command","working_directory"]}, risk_level="high",
        required_permissions=("terminal.execute",), confirmation_required=True, timeout_seconds=125)

    @staticmethod
    def requires_admin(command: str) -> bool: return bool(_ADMIN.search(command))
    @staticmethod
    def destructive(command: str) -> bool: return bool(_DESTRUCTIVE.search(command))

    async def execute(self, arguments, context):
        cwd = Path(arguments.get("working_directory", "")).expanduser().resolve(strict=False)
        if not cwd.is_dir(): raise NotADirectoryError("An existing explicit working directory is required")
        environment = str(arguments.get("environment", "powershell")).lower(); command = str(arguments.get("command", ""))
        if not command.strip(): raise ValueError("Command cannot be empty")
        executable = {"powershell":"powershell.exe", "cmd":"cmd.exe", "python":"python.exe"}.get(environment)
        if not executable: raise ValueError("Environment must be powershell, cmd, or python")
        args = [executable, "-NoProfile", "-Command", command] if environment == "powershell" else \
               [executable, "/d", "/s", "/c", command] if environment == "cmd" else [executable, "-c", command]
        timeout = min(120.0, max(0.1, float(arguments.get("timeout", 30))))
        max_output = min(1024*1024, max(1024, int(arguments.get("max_output_bytes", 65536))))
        from ..services.run_service import ExecutionPolicy
        process = await asyncio.create_subprocess_exec(*args, cwd=str(cwd), stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE,
                                                       env=ExecutionPolicy().environment(),
                                                       creationflags=getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0))
        async def drain(stream, channel):
            import codecs
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            chunks = ""
            truncated = False
            while block := await stream.read(8192):
                chunks += decoder.decode(block)
                if len(chunks) > max_output:
                    chunks = chunks[-max_output:]
                    truncated = True
                if context.progress_callback:
                    context.progress_callback({"channel": channel, "text": chunks})
            chunks += decoder.decode(b"", final=True)
            return chunks[-max_output:], truncated

        stdout_task = asyncio.create_task(drain(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(drain(process.stderr, "stderr"))
        completed = asyncio.create_task(process.wait())
        cancellation = asyncio.create_task(context.cancellation_event.wait()) if context.cancellation_event else None
        status = None
        try:
            watched = {completed, cancellation} if cancellation else {completed}
            done, _ = await asyncio.wait(watched, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if completed not in done:
                status = "Cancelled" if cancellation and cancellation in done else "Timeout"
                if process.returncode is None:
                    process.kill()
                await completed
            stdout, stderr = await asyncio.wait_for(asyncio.gather(stdout_task, stderr_task), 2)
            data = {"exit_code": process.returncode, "stdout": stdout[0], "stderr": stderr[0],
                    "stdout_truncated": stdout[1], "stderr_truncated": stderr[1]}
            if status:
                return ToolResult.failure("Command cancelled" if status == "Cancelled" else f"Command timed out after {timeout:g}s", status, **data)
            return ToolResult(process.returncode == 0, f"Command exited with code {process.returncode}", data,
                              None if process.returncode == 0 else "NonZeroExit")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            tasks = [stdout_task, stderr_task, completed] + ([cancellation] if cancellation else [])
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
