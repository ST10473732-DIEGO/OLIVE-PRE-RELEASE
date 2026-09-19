from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult
from ..services.package_service import installation_plan
from ..services.run_service import ExecutionPolicy
from ..services.workspace_service import require_approved_workspace


class PackageInstallTool:
    definition = ToolDefinition('studio.install_package', 'Install a named dependency in this project', 'studio',
        {'required': ['workspace', 'manager', 'package']}, risk_level='high',
        required_permissions=('filesystem.write', 'terminal.execute', 'network.download', 'software.install'),
        confirmation_required=True, timeout_seconds=300)

    def __init__(self, controller):
        self.controller = controller

    async def execute(self, args, context):
        services = self.controller.s
        workspace = require_approved_workspace(services.workspace_repo, args['workspace'])
        commands = installation_plan(workspace, args['manager'], args['package'])
        output = []
        for command in commands:
            if context.cancellation_event and context.cancellation_event.is_set():
                return ToolResult.failure('Package installation cancelled', 'Cancelled', stdout='\n'.join(output))
            session = await services.run_service.start(workspace, command, 'package_install',
                ExecutionPolicy(workspace.trust_level, 120, allow_network=True))
            try:
                result = await services.run_service.wait_cancellable(session.id, context.cancellation_event)
            finally:
                if session.state in {'starting', 'running'}:
                    await services.run_service.stop(session.id)
            output.append(result.stdout[-30000:] + result.stderr[-30000:])
            if result.state != 'completed':
                return ToolResult.failure('Package installation did not complete. Review the output before retrying.',
                                          'PackageInstallFailed', stdout='\n'.join(output))
        return ToolResult(True, 'Dependency installed in the project', {'stdout':'\n'.join(output), 'installed': True})
