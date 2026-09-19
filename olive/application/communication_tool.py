from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult
from ..agent.permission_service import PermissionDecision
import asyncio


class CommunicationSubmitTool:
    definition = ToolDefinition('communication.submit', 'Submit a message through a configured transport', 'communication',
        {'required':['provider','action_id','revision','server','channel','message']}, risk_level='high',
        required_permissions=('communication.send','app.discord.send_message'), confirmation_required=True, timeout_seconds=60)

    def __init__(self, services):
        self.services = services

    async def execute(self, arguments, context):
        if arguments.get('provider') != 'discord':
            raise ValueError('No configured submission provider matches this request.')
        def revalidate():
            if context.cancellation_event and context.cancellation_event.is_set():
                raise asyncio.CancelledError('Send cancelled before submission')
            for permission in self.definition.required_permissions:
                if self.services.permissions.evaluate(permission).decision == PermissionDecision.DENY:
                    raise PermissionError('Sending permission was revoked before submission.')
        result = await self.services.discord_transport.submit(arguments, revalidate)
        return ToolResult(True, 'Discord accepted the message', result)
