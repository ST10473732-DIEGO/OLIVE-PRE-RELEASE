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


def ordinary_request(text):
    return file_transfer(text) or directory_request(text) or git_request(text)
