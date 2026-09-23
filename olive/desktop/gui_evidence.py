"""Conservative app-neutral postconditions from scoped native semantics.

Missing account/header/delivery semantics cause handoff. Model prose is not an
input to these predicates. A UI delivery indicator is reported as UI evidence,
not a protocol-level exactly-once guarantee.
"""
from urllib.parse import urlsplit, parse_qs


def messaging_destination(scope, observation):
    controls = observation['controls']
    accounts = [c for c in controls if c['name'] == 'Account: ' + scope.account
                and c['role'] in {'label', 'heading', 'push button'}]
    headers = [c for c in controls if c['name'] == scope.destination and c['role'] == 'heading']
    servers = [c for c in controls if c['name'] == scope.server and c.get('selected')]
    if len(accounts) == 1 and len(headers) == 1 and (not scope.server or len(servers) == 1):
        return {'account': scope.account, 'destination': scope.destination, 'server': scope.server}
    return None


def delivery(scope, observation):
    if messaging_destination(scope, observation) is None:
        return False
    controls = observation['controls']
    # Require a single outgoing row, exact text and a non-pending delivery status
    # within that same semantic container. Local composer echo is insufficient.
    rows = [c for c in controls if c['role'] == 'list item' and c['name'] == 'Outgoing message']
    verified = []
    for row in rows:
        children = [c for c in controls if c.get('parent') == row['id']]
        content = [c for c in children if c['role'] in {'label', 'text'} and
                   (c['name'] == scope.content or c.get('value') == scope.content)]
        status = [c for c in children if c['role'] in {'label', 'status bar'} and c['name'] in {'Sent', 'Delivered'}]
        if len(content) == 1 and len(status) == 1:
            verified.append(row['id'])
    return len(verified) == 1


def search_result(scope, observation):
    documents = observation.get('documents', [])
    if len(documents) != 1 or not documents[0]['name']:
        return False
    url = urlsplit(documents[0]['uri'])
    query = parse_qs(url.query)
    # Navigation to a real results URL plus visible matching heading evidence.
    return url.scheme in {'https', 'http'} and any(query.get(key) == [scope.content] for key in ('q', 'query', 'search')) and any(
        scope.content.casefold() in c['name'].casefold() and c['role'] == 'heading'
        for c in observation['controls'])
