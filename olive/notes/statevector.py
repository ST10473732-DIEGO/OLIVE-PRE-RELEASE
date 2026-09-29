"""Yjs state vectors: varuint count, then (client, clock) varuint pairs.

Only used to compare coverage. Deletions are not represented in a state
vector, so coverage never replaces sending the delete set.
"""
from .limits import LIMITS


class StateVectorError(ValueError):
    pass


def _varuint(data, offset):
    value = shift = 0
    while True:
        if offset >= len(data) or shift > 63:
            raise StateVectorError('invalid_state_vector')
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def decode(data):
    if type(data) is not bytes or len(data) > LIMITS['max_state_vector_bytes']:
        raise StateVectorError('invalid_state_vector')
    if not data:
        return {}
    count, offset = _varuint(data, 0)
    if count > 512:
        raise StateVectorError('invalid_state_vector')
    result = {}
    for _ in range(count):
        client, offset = _varuint(data, offset)
        clock, offset = _varuint(data, offset)
        if client in result:
            raise StateVectorError('invalid_state_vector')
        result[client] = clock
    if offset != len(data):
        raise StateVectorError('invalid_state_vector')
    return result


def covers(remote, local):
    """True when every struct in `local` is also in `remote` (both decoded)."""
    return all(remote.get(client, 0) >= clock for client, clock in local.items())
