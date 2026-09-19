"""Live local-model draft correction/cancellation; every consequence is denied."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main():
    reviews = []
    async def deny(request):
        reviews.append(request.tool_name)
        return ConfirmationResponse(False)
    with tempfile.TemporaryDirectory(prefix="olive-context-acceptance-") as directory:
        services = ServiceContainer(lambda *args: None, deny, directory, migrate=False)
        try:
            await services.model_registry.refresh()
            result = await services.interaction.submit("Send John a message saying hello.")
            context = services.interaction.context(services.current_chat_id)
            pending = context.pending
            if not pending or pending["entities"].get("recipient") != "John" or pending["entities"].get("message") != "hello":
                raise AssertionError("Draft creation failed: " + result["messages"][-1]["content"])
            original_id = pending["id"]
            destination = {k: pending["entities"][k] for k in ("application", "recipient", "server", "channel")}
            result = await services.interaction.submit("Actually say hello everyone.")
            if (not context.pending or context.pending["id"] != original_id or
                    context.pending["entities"].get("message") != "hello everyone" or
                    any(context.pending["entities"][k] != v for k, v in destination.items()) or
                    context.pending["state"] != "prepared"):
                raise AssertionError("Field-scoped correction failed: " + result["messages"][-1]["content"])
            result = await services.interaction.submit("Don't send it.")
            if context.pending is not None:
                raise AssertionError("Draft cancellation failed: " + result["messages"][-1]["content"])
            print(json.dumps({"same_pending_action": True, "recipient_preserved": True,
                "body_correction_verified": True, "cancellation_verified": True,
                "external_send_approved": False, "review_count": len(reviews)}), flush=True)
        finally:
            await services.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
