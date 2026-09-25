"""Lossless optional fast paths. Authority still belongs to the normal broker."""
import re


def file_transfer(text):
    write = re.fullmatch(r'(Create (?:a (?:[\w#+]+ )?)?file(?: at)?|Edit) ((?:/|~/)[^\s\x00]+) (?:containing|to contain|saying) ([\'\"])(.*?)\3', text.strip(), re.I|re.S)
    if write:
        verb,path,_,content = write.groups()
        if '\x00' in content or len(content)>80000:return None
        return {'confidence':1, 'clarification':'', 'steps':[
            {'intent':'filesystem.edit_file' if verb.casefold()=='edit' else 'filesystem.create_file',
             'entities':{'path':path,'text':content},'references':{}}]}
    trash = re.fullmatch(r'(?:Delete|Trash) ((?:/|~/)[^\s\x00]+)', text.strip(), re.I)
    if trash:
        return {'confidence':1, 'clarification':'', 'steps':[
            {'intent':'filesystem.trash','entities':{'path':trash.group(1)},'references':{}}]}
    found = re.fullmatch(r'(?:Find|Locate) ([\w][\w.-]{0,200}) in ((?:/|~/)[^\s\x00]+) and (copy|move) it (?:to|into) ((?:/|~/)[^\s\x00]+?)[.]?',
                         text.strip(), re.I)
    if found:
        name, folder, verb, destination = found.groups()
        # A literal filename in a named folder: search that folder, then transfer
        # the single verified result (never the folder itself).
        return {'confidence': 1, 'clarification': '', 'steps': [
            {'intent': 'filesystem.search', 'entities': {'query': name, 'path': folder}, 'references': {}},
            {'intent': 'filesystem.' + verb.lower(), 'entities': {'destination': destination},
             'references': {'path': 'path'}}]}
    # Unquoted absolute paths without spaces are unambiguous. Other phrasing,
    # relative references and quoted filenames use the existing interpreter.
    match = re.fullmatch(r'(Copy|Move) ((?:/|~/)[^\s\x00]+) (?:to|into) ((?:/|~/)[^\s\x00]+)', text.strip(), re.I)
    if not match:
        return None
    verb, source, destination = match.groups()
    return {'confidence':1, 'clarification':'', 'steps':[
        {'intent':'filesystem.'+verb.lower(), 'entities':{'path':source,'destination':destination}, 'references':{}}]}


PATH = r'((?:/|~/)[^\s\x00]+?)'


def _step(intent, **entities):
    return {'confidence': 1, 'clarification': '', 'steps': [{'intent': intent, 'entities': entities, 'references': {}}]}


def directory_request(text):
    """Explicit folder creation/listing/rename with unambiguous absolute paths."""
    value = re.sub(r'^(?:please\s+)', '', text.strip(), flags=re.I)
    match = re.fullmatch(r'(?:Create|Make) (?:a |an |the )?(?:new )?(?:folder|directory)(?: (?:at|called|named))? '
                         + PATH + r'[.]?', value, re.I)
    if match:
        return _step('filesystem.create_directory', path=match.group(1))
    match = re.fullmatch(r'(?:List|Show)(?: me)? (?:the |all )?(?:files|contents|items|entries)(?: (?:in|of|inside))? '
                         + PATH + r'[.]?', value, re.I)
    if match:
        return _step('filesystem.list', path=match.group(1))
    match = re.fullmatch(r'Rename ' + PATH + r' (?:to|as) ([\'"]?)([^\s/\x00\'"]{1,255})\2[.]?', value, re.I)
    if match and match.group(3) not in {'.', '..'}:
        from pathlib import Path
        source = match.group(1)
        return {'confidence': 1, 'clarification': '', 'steps': [{'intent': 'filesystem.move', 'entities': {
            'path': source, 'destination': str(Path(source).expanduser().parent / match.group(3))}, 'references': {}}]}
    return None


GIT_READ = {'status': 'status', 'diff': 'diff', 'log': 'log', 'history': 'log', 'branches': 'branch_list'}


def git_request(text):
    """Typed Git operations for the selected workspace; never a command string."""
    value = re.sub(r'^(?:please\s+)', '', text.strip(), flags=re.I).rstrip('.')
    # An explicit reference to the selected project is scope, not an operation.
    value = re.sub(r'\s+(?:in|of|for|to) (?:my|the|this|selected) (?:project|repository|repo|workspace)\b', '', value,
                   flags=re.I)
    reads = re.fullmatch(r'(?:show|check|read|inspect|list|display)(?: me)?(?: the)? git '
                         r'(status|diff|log|history|branches)(?:\s+(?:and|,)\s+(?:the\s+)?(?:git\s+)?(status|diff|log|history|branches))?'
                         r'(?: (?:for|of|in) (?:my|the|this|selected) (?:project|repository|repo|workspace))?', value, re.I)
    if reads:
        operations = [GIT_READ[w.lower()] for w in reads.groups() if w]
        return {'confidence': 1, 'clarification': '', 'steps': [
            {'intent': 'code.git', 'entities': {'operation': op}, 'references': {}} for op in operations]}
    quoted = r'(["\'“])(.{1,200}?)["\'”]'
    match = re.fullmatch(r'(stage (?:all|my) changes and commit(?: them)?|stage and commit (?:all|my) changes|'
                         r'commit (?:all|every)(?: of)?(?: my| the)? changes|commit the staged changes|commit)'
                         r' with (?:the )?(?:commit )?message ' + quoted, value, re.I | re.S)
    if match:
        steps = []
        if not match.group(1).lower().startswith('commit the staged') and match.group(1).lower() != 'commit':
            steps.append({'intent': 'code.git', 'entities': {'operation': 'add', 'files': '.'}, 'references': {}})
        steps.append({'intent': 'code.git', 'entities': {'operation': 'commit', 'message': match.group(3)},
                      'references': {}})
        return {'confidence': 1, 'clarification': '', 'steps': steps}
    match = re.fullmatch(r'create (?:a )?(?:new )?(?:git )?branch (?:named |called )?([A-Za-z0-9][A-Za-z0-9._/-]{0,127})', value, re.I)
    if match and '..' not in match.group(1):
        return _step('code.git', operation='create_branch', target=match.group(1))
    match = re.fullmatch(r'(?:switch|check out|checkout) (?:to )?(?:the )?(?:git )?branch ([A-Za-z0-9][A-Za-z0-9._/-]{0,127})', value, re.I)
    if match and '..' not in match.group(1):
        return _step('code.git', operation='checkout', target=match.group(1))
    return None


def system_request(text):
    """Explicit typed OS settings; a value outside the literal request is never used."""
    value = re.sub(r'^(?:please\s+)', '', text.strip(), flags=re.I).rstrip('.!?').casefold()
    patterns = (
        (r'(?:set|change|turn) (?:the )?(?:system )?volume (?:to )?(\d{1,3}) ?(?:%|percent)', 'audio_set_volume', int),
        (r'(?:set|change|turn) (?:the )?(?:screen |display )?brightness (?:to )?(\d{1,3}) ?(?:%|percent)', 'display_set_brightness', int),
        (r'(mute|unmute)(?: the)?(?: audio| sound| volume)?', 'audio_set_mute', lambda w: w == 'mute'),
        (r'(?:turn|switch) (on|off) (?:the )?bluetooth|(?:turn|switch) (?:the )?bluetooth (on|off)|(enable|disable) (?:the )?bluetooth',
         'bluetooth_set_power', lambda w: w in {'on', 'enable'}),
        (r'make (?:the )?bluetooth (discoverable|visible|hidden|invisible|undiscoverable)', 'bluetooth_set_discoverable',
         lambda w: w in {'discoverable', 'visible'}),
        (r"(?:what(?:'s| is) the (?:current )?volume|show (?:the )?audio status|is (?:the )?audio muted)", 'audio_status', None),
        (r"(?:is bluetooth (?:on|off|enabled)|show (?:the )?bluetooth status|what(?:'s| is) the bluetooth status)", 'bluetooth_status', None),
        (r"(?:what(?:'s| is) the (?:screen |display )?brightness|show (?:the )?(?:display|brightness) status)", 'display_status', None),
        (r"(?:is wi-?fi (?:on|enabled)|show (?:the )?(?:network|wi-?fi) status|am i online)", 'network_status', None),
    )
    for pattern, operation, convert in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            word = next((g for g in match.groups() if g), '')
            entities = {'operation': operation}
            if convert is int:
                entities['value'] = word
            elif convert is not None:
                entities['value'] = 'true' if convert(word) else 'false'
            return _step('system.control', **entities)
    return None


def personal_request(text):
    """'Create a task to/called X' is a task; the title is the user's literal words."""
    match = re.fullmatch(r'(?:please\s+)?(?:create|add|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|to-?do)\s+'
                         r'(?:to\s+|called\s+|named\s+|titled\s+)?([^\n]{1,160}?)[.!]?', text.strip(), re.I)
    if not match or re.search(r'\b(?:tomorrow|today|at \d|on \w+day|due|remind|every)\b', match.group(1), re.I):
        return None  # Dates, recurrence and reminders keep the full semantic interpretation.
    title = match.group(1).strip().strip('"\'')
    return _step('tasks.create', title=title[:1].upper() + title[1:])


def ordinary_request(text):
    return (file_transfer(text) or directory_request(text) or git_request(text) or system_request(text)
            or personal_request(text))
