"""Lexical owner-task families beyond single-file effects.

Pure functions over the literal local request. Quoted payloads, supplied code and
negated clauses are removed before any capability is derived. The result only
names capabilities and exact bindings; `OwnerPolicy.authorize` re-checks every
argument and persistent Deny is evaluated before Owner Mode.
"""
import hashlib
from pathlib import Path
import re

CODE_READ = {'code.read_file', 'code.read_range', 'code.search_text', 'code.search_symbol', 'code.list_symbols',
             'code.find_references', 'studio.open', 'studio.tree', 'studio.search', 'studio.compare',
             'studio.designer_read', 'studio.language_service'}
CODE_WRITE = {'code.replace_exact', 'code.replace_range', 'code.create_file', 'studio.save', 'studio.designer_save'}
GIT_WRITE = {'git.add', 'git.commit', 'git.create_branch', 'git.checkout'}
FS_READ = {'filesystem.list', 'filesystem.search', 'filesystem.stat', 'filesystem.read_text'}
APP_TOOLS = {'system.open_application', 'system.close_application', 'system.open_path', 'ide.open_workspace',
             'ide.open_file'}
SYSTEM_READ = {'system.audio_status', 'system.bluetooth_status', 'system.display_status', 'system.network_status'}
PERSONAL_WRITE = {'tasks.create', 'tasks.update', 'tasks.complete', 'tasks.reopen', 'tasks.schedule',
                  'calendar.create', 'calendar.update', 'reminders.create', 'reminders.update',
                  'reminders.snooze', 'reminders.dismiss'}
RESEARCH_READ = {'research.run', 'web.search', 'web.read', 'web.open', 'web.links', 'web.page_info', 'web.follow',
                 'web.scope'}
# Bounded mutation budgets per grant; every other mutation is reserved once.
BUDGETS = {'code.replace_exact': 32, 'code.replace_range': 32, 'code.create_file': 16, 'studio.save': 16}


def literal_quotes(text):
    return [next(g for g in m.groups() if g is not None)
            for m in re.finditer(r'"([^"\n]{1,400})"|\'([^\'\n]{1,400})\'|“([^”\n]{1,400})”', text)]


def _paths(text):
    return re.findall(r'(?<![\w/])(?:~/|/)[^\s\'";,]+', text)


def extend(text, instruction, *, workspace='', answer_only=False, forbidden=frozenset()):
    """Return (capabilities, bindings) for ordinary explicit owner families."""
    capabilities, bindings = set(), {}
    if answer_only:
        return capabilities, bindings
    positive = instruction
    # Directory reads: list/show/search the contents of a literal folder.
    folder_paths = [str(Path(p).expanduser().resolve()) for p in _paths(_strip_payloads(text))]
    if folder_paths and re.search(r'\b(?:list|show|find|search|look for|what(?:\'s| is) in)\b', positive):
        capabilities.update(FS_READ)
        bindings['read_roots'] = frozenset(folder_paths)
    # Directory creation.
    if re.search(r'\b(?:create|make)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:folder|directory)\b', positive) \
            and 'create' not in forbidden and len(folder_paths) == 1:
        capabilities.update({'filesystem.create_directory', 'filesystem.stat'})
        bindings['directories'] = frozenset(folder_paths)
    # Rename to a sibling name: "rename /a/b.txt to c.txt".
    match = re.search(r'\brename\s+((?:~/|/)[^\s\'";,]+)\s+(?:to|as)\s+([\'"]?)([^\s/\'"\x00]{1,255})\2(?:\s|[.]?$)',
                      _strip_payloads(text, keep_quotes=True), re.I)
    if match and 'rename' not in forbidden and match.group(3) not in {'.', '..'}:
        source = Path(match.group(1)).expanduser().resolve()
        bindings['rename'] = (str(source), str(source.parent / match.group(3)))
        capabilities.update({'filesystem.move', 'filesystem.stat'})
    # Workspace code: requires a selected approved workspace and an explicit
    # software target/execution request. Answer-only code never reaches here.
    from ..interaction.deliverable import code_action_requested
    if workspace and code_action_requested(text):
        if re.search(r'\b(?:inspect|read|explain|review|search|find|look|open|show|fix|edit|change|modify|refactor|'
                     r'update|add|implement|rename|create|write|debug|build|test|run)\b', positive):
            capabilities.update(CODE_READ)
        if re.search(r'\b(?:fix|edit|change|modify|refactor|update|add|implement|rename|create|write)\b', positive) \
                and not forbidden & {'edit', 'fix', 'create', 'change', 'modify', 'save'}:
            capabilities.update(CODE_WRITE)
        if re.search(r'\bbuild\b', positive) and 'build' not in forbidden:
            capabilities.add('studio.build')
        if re.search(r'\bdebug\b', positive):
            capabilities.add('studio.debug')
    # Explicit Git mutations in the selected approved repository only.
    if workspace and re.search(r'\bgit\b|\bcommit\b|\bbranch\b|\bstage\b', positive):
        git = {}
        if re.search(r'\bcommit\b', positive) and 'commit' not in forbidden:
            message = re.search(r'\b(?:message|saying|titled|with)\s+(["\'“])(.{1,200}?)(["\'”])', text)
            git['git.commit'] = message.group(2) if message else ''
        if re.search(r'\b(?:stage|git add|add (?:all|the|my)?\s*(?:changes|files|changed files))\b', positive) \
                or re.search(r'\bcommit (?:all|every)\b', positive):
            git['git.add'] = ('.',)
        branch = re.search(r'\bcreate\s+(?:a\s+)?(?:new\s+)?branch\s+(?:named\s+|called\s+)?([A-Za-z0-9][A-Za-z0-9._/-]{0,127})',
                           _strip_payloads(text, keep_quotes=True), re.I)
        if branch and '..' not in branch.group(1):
            git['git.create_branch'] = branch.group(1)
        switch = re.search(r'\b(?:switch|checkout|check out)\s+(?:to\s+)?(?:the\s+)?(?:branch\s+)?([A-Za-z0-9][A-Za-z0-9._/-]{0,127})',
                           _strip_payloads(text, keep_quotes=True), re.I)
        if switch and switch.group(1).casefold() not in {'branch', 'the', 'a', 'to'} and '..' not in switch.group(1):
            git['git.checkout'] = switch.group(1)
        for tool in list(git):
            if tool.split('.')[1].replace('_', ' ') in forbidden or (tool == 'git.checkout' and 'switch' in forbidden):
                git.pop(tool)
        if git:
            capabilities.update(git)
            capabilities.update({'git.status', 'git.diff'})
            bindings['git'] = git
    # Applications/paths explicitly named for open/close.
    open_match = re.search(r'\b(?:open|launch|start)\s+([\w .+-]{1,80}?)(?:\s+(?:app|application))?(?:[.,;]|\s+and\b|\s+then\b|$)',
                           positive)
    if open_match and 'open' not in forbidden:
        capabilities.update({'system.open_application', 'ide.open_workspace', 'ide.open_file', 'system.open_path'})
        bindings['open'] = open_match.group(1).strip()
    close_match = re.search(r'\b(?:close|quit|exit)\s+([\w .+-]{1,80}?)(?:\s+(?:app|application|window))?(?:[.,;]|\s+and\b|\s+then\b|$)',
                            positive)
    if close_match and not forbidden & {'close', 'quit'}:
        capabilities.add('system.close_application')
        bindings['close'] = close_match.group(1).strip()
    if re.search(r'\b(?:running|open)\s+(?:apps|applications|programs|windows)\b', positive):
        capabilities.add('system.list_running_applications')
    # Typed OS controls: explicit volume/mute/Bluetooth power.
    system = {}
    volume = re.search(r'\b(?:set|change|turn)\s+(?:the\s+)?(?:system\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)', positive)
    if volume and 0 <= int(volume.group(1)) <= 100:
        system['system.audio_set_volume'] = int(volume.group(1))
    if re.search(r'\bunmute\b', positive):
        system['system.audio_set_mute'] = False
    elif re.search(r'\bmute\b', positive):
        system['system.audio_set_mute'] = True
    brightness = re.search(r'\b(?:set|change|turn)\s+(?:the\s+)?(?:screen\s+|display\s+)?brightness\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)', positive)
    if brightness and 1 <= int(brightness.group(1)) <= 100:
        system['system.display_set_brightness'] = int(brightness.group(1))
    visible = re.search(r'\bmake\s+(?:the\s+)?bluetooth\s+(discoverable|visible|hidden|invisible|undiscoverable)\b', positive)
    if visible:
        system['system.bluetooth_set_discoverable'] = visible.group(1) in {'discoverable', 'visible'}
    bluetooth = re.search(r'\b(?:turn|switch)\s+(on|off)\s+(?:the\s+)?bluetooth\b|\b(?:turn|switch)\s+(?:the\s+)?bluetooth\s+(on|off)\b|\b(enable|disable)\s+(?:the\s+)?bluetooth\b',
                          positive)
    if bluetooth:
        word = next(g for g in bluetooth.groups() if g)
        system['system.bluetooth_set_power'] = word in {'on', 'enable'}
    if system and not forbidden & {'change', 'set', 'turn', 'make'}:
        capabilities.update(system)
        capabilities.update(SYSTEM_READ)
        bindings['system'] = system
    elif re.search(r'\b(?:volume|audio|bluetooth|brightness|wi-?fi|network)\b', positive) and \
            re.search(r'\b(?:what|show|check|status|is|are)\b', positive):
        capabilities.update(SYSTEM_READ)
    # Ordinary local personal records: one explicit create/update/complete.
    if re.search(r'\b(?:task|tasks|to-?do|event|meeting|appointment|reminder|calendar)\b|\bremind me\b', positive):
        personal = set()
        if re.search(r'\b(?:add|create|make|schedule|book|set|remind)\b', positive):
            personal |= {'tasks.create', 'calendar.create', 'reminders.create', 'tasks.schedule'}
        if re.search(r'\b(?:update|change|move|reschedule|rename|edit)\b', positive):
            personal |= {'tasks.update', 'calendar.update', 'reminders.update'}
        if re.search(r'\b(?:complete|finish|mark\b.*\b(?:done|complete|completed))\b', positive):
            personal.add('tasks.complete')
        if re.search(r'\breopen\b', positive):
            personal.add('tasks.reopen')
        if re.search(r'\bsnooze\b', positive):
            personal.add('reminders.snooze')
        if re.search(r'\bdismiss\b', positive):
            personal.add('reminders.dismiss')
        capabilities.update(t for t in personal if t.split('.')[1] not in forbidden)
    # Mail: local drafts for explicit compose/reply; external submission only to
    # recipient addresses written literally in this request.
    if re.search(r'\b(?:email|e-mail|mail)\b', positive):
        if re.search(r'\b(?:draft|compose|write|reply|prepare)\b', positive) and 'draft' not in forbidden:
            capabilities.update({'mail.save_draft', 'mail.reply', 'mail.prepare'})
        addresses = frozenset(a.casefold() for a in re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', text))
        if addresses and re.search(r'\bsend\b', positive) and 'send' not in forbidden:
            capabilities.update({'mail.prepare', 'mail.send', 'mail.save_draft'})
            quotes = literal_quotes(text)
            bindings['mail'] = {'recipients': addresses, 'body': quotes[0] if len(quotes) == 1 else None}
    # Explicit public web research reads.
    if re.search(r'\b(?:research|search (?:the web|online)|look up|find (?:out|online))\b', positive):
        capabilities.update(RESEARCH_READ)
    return capabilities, bindings


def _strip_payloads(text, keep_quotes=False):
    text = re.sub(r'```[^\n]*\n.*?(?:```|$)', ' ', text, flags=re.S)
    if not keep_quotes:
        text = re.sub(r'([\'"])(?:(?!\1).)*?\1',
                      lambda m: m.group()[1:-1] if re.fullmatch(r'(?:~/|/)[^\n]+', m.group()[1:-1]) else ' ',
                      text, flags=re.S)
    return re.sub(r"\b(?:do not|don't|never)\s+[^.;\n]+", ' ', text, flags=re.I)


def within(path, roots):
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return any(resolved == Path(root) or Path(root) in resolved.parents for root in roots)


def workspace_matches(argument, workspace, workspace_repo=None):
    if not isinstance(argument, str) or not argument or not workspace:
        return False
    try:
        if Path(argument).is_absolute():
            return str(Path(argument).resolve()) == workspace
    except (OSError, RuntimeError, ValueError):
        return False
    if workspace_repo is not None:
        record = workspace_repo.load_all().get(argument)
        return bool(record and str(Path(record.root_path).resolve()) == workspace)
    return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
