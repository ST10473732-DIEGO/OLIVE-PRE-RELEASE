"""Choose an app window only when no existing document/account is the target."""


def choose_window(windows, purpose='exact'):
    if purpose not in {'exact', 'open', 'new_document'}:
        raise ValueError('Unsupported window activation purpose')
    if len(windows) <= 1:
        return windows[0] if windows else None
    if purpose == 'exact' or any(w.get('dialog') for w in windows):
        raise ValueError('Multiple windows match the requested application')
    candidates = [w for w in windows if w.get('normal') and type(w.get('stacking')) is int]
    if len(candidates) != len(windows):
        raise ValueError('Window stacking identity is unavailable')
    top = max(w['stacking'] for w in candidates)
    matches = [w for w in candidates if w['stacking'] == top]
    if len(matches) != 1:
        raise ValueError('Window stacking identity is ambiguous')
    return matches[0]
