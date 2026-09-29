"""Deterministic keyboard allowlist.

Key actions come only from this table; a model or an observation cannot invent
a sequence. Each entry names the Linux evdev codes pressed (in order) and the
contexts where the key has an established meaning. Callers pass the context
they verified (for example `browser` after binding a web-browser window).
"""

# name: (evdev codes, allowed contexts)
KEYS = {
    'Enter': ((28,), {'any'}),
    'Escape': ((1,), {'any'}),
    'Tab': ((15,), {'any'}),
    'Shift+Tab': ((42, 15), {'any'}),
    'Up': ((103,), {'any'}),
    'Down': ((108,), {'any'}),
    'Left': ((105,), {'any'}),
    'Right': ((106,), {'any'}),
    'PageUp': ((104,), {'any'}),
    'PageDown': ((109,), {'any'}),
    'Home': ((102,), {'any'}),
    'End': ((107,), {'any'}),
    'Space': ((57,), {'any'}),
    'Ctrl+L': ((29, 38), {'browser', 'file_manager'}),   # address / location bar
    'Ctrl+F': ((29, 33), {'browser', 'editor', 'file_manager'}),
    'Ctrl+T': ((29, 20), {'browser', 'terminal'}),         # new tab
    'Ctrl+W': ((29, 17), {'browser', 'editor'}),           # close tab (explicit request only)
    'Ctrl+Shift+T': ((29, 42, 20), {'browser'}),           # reopen the most recently closed tab
    'Ctrl+R': ((29, 19), {'browser'}),                     # reload
    'Ctrl+PageDown': ((29, 109), {'browser', 'editor'}),   # next tab
    'Ctrl+PageUp': ((29, 104), {'browser', 'editor'}),     # previous tab
    'Alt+Left': ((56, 105), {'browser', 'file_manager'}),  # back
    'Alt+Right': ((56, 106), {'browser', 'file_manager'}),  # forward
    'Ctrl+K': ((29, 37), {'messaging'}),                   # messaging quick switcher
    'Ctrl+A': ((29, 30), {'field'}),                       # select a verified focused field's own text
}

# Keys that can submit or send; never allowed as a navigation key into a composer.
SUBMITTING = {'Enter'}
# Keys that close something the user owns: explicit request only.
CLOSING = {'Ctrl+W'}


def key_codes(name, context='any'):
    """Evdev codes for an allowlisted key in a verified context; raises otherwise."""
    if not isinstance(name, str) or name not in KEYS:
        raise PermissionError('INPUT_REFUSED: key is not in the allowlist')
    codes, contexts = KEYS[name]
    if 'any' not in contexts and context not in contexts:
        raise PermissionError('INPUT_REFUSED: this key has no verified meaning in the current application')
    return list(codes)


def canonical(name):
    """Accept common spellings ('ctrl+l', 'Alt+left') and return the table key."""
    if not isinstance(name, str) or len(name) > 24:
        return None
    wanted = name.replace(' ', '').casefold()
    return next((key for key in KEYS if key.casefold() == wanted), None)
