"""Presentation roles never replace account-scoped provider mailbox identities."""
import json

FOLDERS = ('Inbox', 'Drafts', 'Outbox', 'Sent', 'Archive', 'Spam', 'Trash')
SPECIAL_USE = {'\\sent': 'Sent', '\\drafts': 'Drafts', '\\archive': 'Archive',
               '\\junk': 'Spam', '\\trash': 'Trash', '\\all': 'All messages'}


def role(name, flags=()):
    if isinstance(flags, str):
        flags = json.loads(flags)
    if (name or '').casefold() == 'inbox':
        return 'Inbox'
    roles = {SPECIAL_USE[f.casefold()] for f in (flags or ()) if f.casefold() in SPECIAL_USE}
    return next(iter(roles)) if len(roles) == 1 else name


def resolve(requested, advertised):
    exact = [f['name'] for f in advertised if f['name'] == requested]
    matches = exact or [f['name'] for f in advertised if role(f['name'], f.get('flags', ())) == requested]
    if len(matches) != 1:
        raise ValueError('Select one actual server mailbox; this folder role is unavailable or ambiguous')
    return matches[0]


# Correlated lookup also interprets old cached records without rewriting them.
# Local folder annotations keep their local role until an explicit remote move.
ROLE_SQL = """mail_folder_role(json_extract(records.body,'$.folder'),
 CASE WHEN json_extract(records.body,'$.folder')=json_extract(records.body,'$.remote.mailbox')
 THEN (SELECT json_extract(f.body,'$.flags') FROM records f WHERE f.kind='folder'
 AND json_extract(f.body,'$.connection_id')=json_extract(records.body,'$.connection_id')
 AND json_extract(f.body,'$.name')=json_extract(records.body,'$.folder') LIMIT 1)
 ELSE NULL END)"""

def match_sql():
    return """((COALESCE(json_extract(records.body,'$.remote_state'),'') NOT IN
    ('moved_on_server','missing_on_server','uidvalidity_reset')
    OR json_extract(records.body,'$.folder')!=json_extract(records.body,'$.remote.mailbox'))
    AND (json_extract(records.body,'$.folder')=? OR """+ROLE_SQL+"""=?) OR EXISTS (
    SELECT 1 FROM json_each(json_extract(records.body,'$.remote_locations')) location
    WHERE COALESCE(json_extract(location.value,'$.state'),'present')='present'
    AND (json_extract(location.value,'$.mailbox')=? OR mail_folder_role(
    json_extract(location.value,'$.mailbox'),(SELECT json_extract(f.body,'$.flags')
    FROM records f WHERE f.kind='folder'
    AND json_extract(f.body,'$.connection_id')=json_extract(records.body,'$.connection_id')
    AND json_extract(f.body,'$.name')=json_extract(location.value,'$.mailbox') LIMIT 1))=?)))"""
