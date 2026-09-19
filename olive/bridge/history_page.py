"""Bound transport without making older persisted history inaccessible."""


def summary_page(records, keys, query_key, query='', offset=0):
    if not 0 <= offset <= 1_000_000:
        raise ValueError('Invalid history offset')
    query = query.casefold()
    matching = (record for record in records if query in str(record.get(query_key, '')).casefold())
    from itertools import islice
    return [{key: record.get(key) for key in keys} for record in islice(matching, offset, offset + 100)]
