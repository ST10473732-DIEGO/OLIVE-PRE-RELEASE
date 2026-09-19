"""Bounded validation for the explicit existing-feature protocol surface."""
import math
from .m2_contracts import SPEC, MAIN_ONLY


def bounded(value, depth=0):
    if depth > 8:
        return False
    if isinstance(value, str):
        return len(value) <= 32000 and '\0' not in value
    if type(value) in (int, float):
        return math.isfinite(value)
    if value is None or type(value) is bool:
        return True
    if isinstance(value, list):
        return len(value) <= 200 and all(bounded(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return len(value) <= 200 and all(isinstance(k, str) and len(k) <= 200 and k not in {'__proto__', 'constructor', 'prototype'} and bounded(v, depth + 1) for k, v in value.items())
    return False


def validate_arguments(method, args):
    spec = (SPEC | MAIN_ONLY)[method]
    required, optional = spec['required'], spec['optional']
    if type(args) is not dict or not set(required) <= set(args) or set(args) - (required.keys() | optional.keys()):
        raise ValueError('Invalid method arguments')
    for key, value in args.items():
        kind = (required | optional)[key]
        if '|' in kind:
            valid = isinstance(value, str) and value in kind.split('|')
        elif kind in {'s', 't'}:
            valid = isinstance(value, str) and len(value) <= (4096 if kind == 's' else 32000) and '\0' not in value
        elif kind == 'i':
            valid = type(value) is int and -1000000 <= value <= 1000000
        elif kind == 'b':
            valid = type(value) is bool
        else:
            valid = type(value) is (list if kind == 'a' else dict) and bounded(value)
        if not valid:
            raise ValueError(f'Invalid {key}')
