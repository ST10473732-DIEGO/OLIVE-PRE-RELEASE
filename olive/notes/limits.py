"""The one wire/document definition shared with the renderer and phone engine."""
import json
from pathlib import Path

SPEC = json.loads((Path(__file__).with_name('protocol_v1.json')).read_text(encoding='utf-8'))
PROTOCOL = SPEC['protocol']
CAPABILITY = SPEC['capability']
LIMITS = SPEC['limits']
BODY = SPEC['document']['body']
META = SPEC['document']['meta']
META_KEYS = frozenset(SPEC['document']['meta_keys'])
DOCUMENT_SCHEMA = SPEC['document']['schema']
