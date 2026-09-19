"""Explicit Studio tooling bridge methods and bounded argument contracts."""
import json

SPEC = {
    'designer.load': ({'workspace_id':str}, {}),
    'designer.save': ({'workspace_id':str,'layout':dict,'revision':str}, {}),
    'tooling.inventory': ({}, {}),
    'lsp.start': ({'workspace_id': str, 'language': str}, {}),
    'lsp.stop': ({'workspace_id': str}, {'language': str}),
    'lsp.restart': ({'workspace_id': str, 'language': str}, {}),
    'lsp.status': ({'workspace_id': str}, {}),
    'lsp.open': ({'workspace_id': str, 'path': str, 'text': str}, {'language_id': str}),
    'lsp.change': ({'workspace_id': str, 'path': str, 'text': str}, {}),
    'lsp.close': ({'workspace_id': str, 'path': str}, {}),
    'lsp.saved': ({'workspace_id': str, 'path': str}, {}),
    'lsp.request': ({'workspace_id': str, 'feature': str}, {'path': str, 'params': dict, 'language': str}),
    'lsp.diagnostics': ({'workspace_id': str}, {}),
    'dap.launch': ({'workspace_id': str}, {}),
    'dap.stop': ({'session_id': str}, {}),
    'dap.request': ({'session_id': str, 'command': str}, {'arguments': dict, 'generation': int}),
    'dap.breakpoints': ({'workspace_id': str, 'path': str, 'lines': list}, {}),
    'dap.status': ({'workspace_id': str}, {}),
    'terminal.open': ({'workspace_id': str}, {'shell': str}),
    'terminal.write': ({'session_id': str, 'data': str}, {}),
    'terminal.resize': ({'session_id': str, 'columns': int, 'rows': int}, {}),
    'terminal.close': ({'session_id': str}, {}),
    'terminal.list': ({'workspace_id': str}, {}),
    'project.scan': ({'workspace_id': str}, {}),
    'project.config_get': ({'workspace_id': str}, {}),
    'project.config_save': ({'workspace_id': str, 'config': dict}, {}),
    'project.build': ({'workspace_id': str, 'mode': str}, {'target': str}),
    'project.test': ({'workspace_id': str}, {'filters': list, 'list_only': bool, 'target': str}),
    'project.run': ({'workspace_id': str}, {}),
    'project.toolchains': ({}, {'workspace_id': str, 'refresh': bool}),
    'project.new_preview': ({'language': str, 'template': str, 'name': str, 'location': str}, {}),
    'project.new': ({'language': str, 'template': str, 'name': str, 'location': str},
                    {'framework': str, 'interpreter': str, 'git': bool}),
    'project.cancel': ({'job_id': str}, {}),
    'project.jobs': ({'workspace_id': str}, {}),
    'project.create': ({'workspace_id': str, 'kind': str, 'name': str}, {'directory': str, 'solution': str, 'references': list}),
    'project.add_existing': ({'workspace_id': str, 'solution': str, 'project': str}, {}),
    'web.request': ({'workspace_id': str, 'session_id': str, 'method': str, 'path': str}, {'headers': dict, 'body': str}),
    'web.history': ({'workspace_id': str}, {}),
}
LIMITS = {'text': 400_000, 'data': 65_536, 'body': 512_000, 'path': 4096}


def validate(method, args):
    required, optional = SPEC[method]
    if not isinstance(args, dict) or not set(required) <= set(args) or set(args) - (required.keys() | optional.keys()):
        raise ValueError('Invalid Studio tooling arguments')
    for key, value in args.items():
        if type(value) is not (required | optional)[key]:
            raise ValueError('Invalid Studio tooling argument type')
        if isinstance(value, str):
            limit = LIMITS.get(key, 4096)
            if len(value) > limit or '\x00' in value:
                raise ValueError('Studio tooling argument exceeds supported bounds')
        if isinstance(value, int) and not isinstance(value, bool) and not -10_000_000 <= value <= 10_000_000:
            raise ValueError('Studio tooling argument exceeds supported bounds')
    if len(json.dumps(args, allow_nan=False).encode()) > 900_000:
        raise ValueError('Studio tooling request exceeds bounds')

    def bounded(value, depth=0):
        if depth > 10:
            raise ValueError('Studio tooling nesting exceeds bounds')
        if isinstance(value, str) and ('\x00' in value or len(value) > 4_000_000):
            raise ValueError('Studio tooling text exceeds bounds')
        if isinstance(value, (list, dict)):
            if len(value) > 5000:
                raise ValueError('Studio tooling collection exceeds bounds')
            for item in (value.values() if isinstance(value, dict) else value):
                bounded(item, depth + 1)
    bounded(args)
    return args
