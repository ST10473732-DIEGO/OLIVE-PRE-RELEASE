"""Project-local package commands; no arbitrary shell or global install route."""
from pathlib import Path
import re
import shutil
import sys


def installation_plan(workspace, manager, package):
    if workspace.trust_level == 'untrusted':
        raise PermissionError('Approve this workspace before installing dependencies.')
    root = workspace.resolve('.')
    if manager == 'python':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}(?:==[A-Za-z0-9][A-Za-z0-9_.+-]{0,79})?', package):
            raise ValueError('Enter a package name, optionally followed by ==version.')
        environment = workspace.resolve('.venv')
        python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        commands = []
        if environment.exists() and not python.is_file():
            raise ValueError('The project .venv is incomplete. Repair it before installing packages.')
        if not python.is_file():
            commands.append([sys.executable, '-m', 'venv', str(environment)])
        commands.append([str(python), '-m', 'pip', '--isolated', '--disable-pip-version-check',
                         '--require-virtualenv', 'install', '--only-binary=:all:', '--no-input', package])
        return commands
    if manager == 'node':
        if not re.fullmatch(r'(?:@[a-z0-9][a-z0-9_.-]{0,79}/)?[a-z0-9][a-z0-9_.-]{0,99}(?:@[0-9][A-Za-z0-9.+-]{0,79})?', package):
            raise ValueError('Enter an npm package name, optionally followed by @version.')
        if not workspace.resolve('package.json').is_file():
            raise ValueError('Create a package.json in this project first.')
        node = shutil.which('node')
        cli = Path(node).parent / 'node_modules/npm/bin/npm-cli.js' if node else None
        if not cli or not cli.is_file():
            raise ValueError('Node with npm is not available. Configure a local Node installation first.')
        return [[node, str(cli), 'install', '--ignore-scripts', '--no-audit', '--no-fund', '--save-exact', package]]
    raise ValueError('Choose Python or Node. Java projects can use local JARs in lib/.')
