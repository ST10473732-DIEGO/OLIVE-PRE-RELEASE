"""Opt-in local-model file search/reference/read acceptance with temporary PDFs."""

import asyncio
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


def write_pdf(path, text):
    stream = ("BT /F1 12 Tf 40 740 Td (" + text + ") Tj ET").encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    path.write_bytes(data)


async def main():
    with tempfile.TemporaryDirectory(prefix="olive-file-language-") as directory:
        root = Path(directory)
        documents = root / "documents"
        documents.mkdir()
        chosen = documents / "release-notes.pdf"
        write_pdf(chosen, "OLIVE acceptance document. The sample release uses a violet theme and has seven stages.")
        write_pdf(documents / "older.pdf", "This older document is not the selected source.")
        yesterday = datetime.now() - timedelta(days=1)
        os.utime(chosen, (yesterday.timestamp(), yesterday.timestamp()))
        older = yesterday - timedelta(days=1)
        os.utime(documents / "older.pdf", (older.timestamp(), older.timestamp()))
        async def review(request):
            allowed = {"filesystem.search", "filesystem.stat", "filesystem.read", "knowledge.read_selected"}
            return ConfirmationResponse(request.tool_name in allowed and all(
                Path(target).resolve().is_relative_to(root) for target in request.targets))
        services = ServiceContainer(lambda *args: None, review, data_dir=root / "data", migrate=False)
        try:
            await services.model_registry.refresh()
            services.chat.update(services.current_chat_id, model="qwen3:8b")
            interpret = services.interaction.interpreter.interpret
            async def record_interpretation(text, context):
                result = await interpret(text, context)
                print(json.dumps({"interpretation": result}), flush=True)
                return result
            services.interaction.interpreter.interpret = record_interpretation
            execute = services.interaction.router.execute
            async def record(step, context):
                print(json.dumps({"interpreted": step}), flush=True)
                return await execute(step, context)
            services.interaction.router.execute = record
            result = await services.interaction.submit(f'Find the PDF I downloaded yesterday in "{documents}".')
            context = services.interaction.context(services.current_chat_id)
            if context.entities.get("path") != str(chosen):
                raise AssertionError("File selection failed: " + result["messages"][-1]["content"])
            open_step = context.resolve({"intent": "filesystem.open", "entities": {}, "references": {"path": "path"}})
            if open_step["entities"]["path"] != str(chosen):
                raise AssertionError("File reference changed")
            opened = []
            tool = services.agent.tool
            async def record_open(name, arguments, *args, **kwargs):
                if name == "system.open_path":
                    opened.append(arguments["path"])
                    return {"requested": True}  # Routing fixture; do not disturb a user's PDF viewer.
                return await tool(name, arguments, *args, **kwargs)
            services.agent.tool = record_open
            await services.interaction.submit("Open it.")
            if opened != [str(chosen)]:
                raise AssertionError("Natural file-open follow-up did not retain the selected PDF")
            result = await services.interaction.submit("Summarize it.")
            answer = result["messages"][-1]["content"]
            if "violet" not in answer.casefold():
                raise AssertionError("The answer did not use the selected document: " + answer)
            print(json.dumps({"temporary_pdf_search_verified": True, "relative_file_identity_verified": True,
                              "natural_file_open_routed": True,
                              "document_summary_verified": True, "external_file_viewer_opened": False}), flush=True)
        finally:
            await services.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
