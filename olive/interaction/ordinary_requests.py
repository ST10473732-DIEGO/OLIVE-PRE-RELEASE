"""Lossless optional fast paths. Authority still belongs to the normal broker."""
import re


def file_transfer(text):
    # Unquoted absolute paths without spaces are unambiguous. Other phrasing,
    # relative references and quoted filenames use the existing interpreter.
    match = re.fullmatch(r'(Copy|Move) ((?:/|~/)[^\s\x00]+) (?:to|into) ((?:/|~/)[^\s\x00]+)', text.strip(), re.I)
    if not match:
        return None
    verb, source, destination = match.groups()
    return {'confidence':1, 'clarification':'', 'steps':[
        {'intent':'filesystem.'+verb.lower(), 'entities':{'path':source,'destination':destination}, 'references':{}}]}
