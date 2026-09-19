"""Bridge routes for real Studio tooling (language servers, debugger, terminals, projects)."""
import inspect

from ..studio_tooling.errors import StudioToolingError


def routes(services):
    tooling = services.studio_tooling
    return {
        'designer.load': tooling.designer.call,
        'designer.save': tooling.designer.call,
        'tooling.inventory': tooling.inventory,
        'lsp.start': tooling.language_start,
        'lsp.stop': tooling.language_stop,
        'lsp.restart': tooling.language_restart,
        'lsp.status': tooling.language_status,
        'lsp.open': tooling.language_open,
        'lsp.change': tooling.language_change,
        'lsp.close': tooling.language_close,
        'lsp.saved': tooling.language_saved,
        'lsp.request': tooling.language_request,
        'lsp.diagnostics': tooling.language_diagnostics,
        'dap.launch': tooling.debug_launch,
        'dap.stop': tooling.debug_stop,
        'dap.request': tooling.debug_request,
        'dap.breakpoints': tooling.debug_breakpoints,
        'dap.status': tooling.debug_status,
        'terminal.open': tooling.terminal_open,
        'terminal.write': tooling.terminal_write,
        'terminal.resize': tooling.terminal_resize,
        'terminal.close': tooling.terminal_close,
        'terminal.list': tooling.terminal_list,
        'project.scan': tooling.project_scan,
        'project.config_get': tooling.config_get,
        'project.config_save': tooling.config_save,
        'project.build': tooling.build,
        'project.test': tooling.test,
        'project.run': tooling.run,
        'project.toolchains': tooling.toolchains,
        'project.new_preview': tooling.new_project_preview,
        'project.new': tooling.new_project,
        'project.cancel': tooling.job_cancel,
        'project.jobs': tooling.jobs_list,
        'project.create': tooling.scaffold,
        'project.add_existing': tooling.add_existing,
        'web.request': tooling.web_request,
        'web.history': tooling.web_history,
    }


async def call(services, method, args):
    function = routes(services).get(method)
    if function is None:
        raise ValueError('Unsupported Studio tooling operation')
    try:
        result = function(**args)
        return await result if inspect.isawaitable(result) else result
    except StudioToolingError:
        raise
    except (ValueError, RuntimeError, FileNotFoundError, ConnectionError, TimeoutError, PermissionError) as error:
        # Tooling messages describe the user's own project and sessions; make them readable.
        raise StudioToolingError(str(error)[:1500] or type(error).__name__) from error
