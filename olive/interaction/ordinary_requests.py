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
