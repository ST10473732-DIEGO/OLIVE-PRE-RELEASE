"""Presentation schema for existing settings; unknown persisted fields stay private."""
from copy import deepcopy
import math

from ..services.model_policy import DEFAULT_EMBEDDING_MODEL


def field(key, label, category, kind, default, minimum=None, maximum=None, choices=None, target='settings'):
    return dict(key=key, label=label, category=category, kind=kind, default=default,
                minimum=minimum, maximum=maximum, choices=choices, target=target)


FIELDS = [
    field('owner_mode', 'Owner Mode — ordinary explicit local tasks', 'Permissions', 'bool', False),
    field('preferred_name', 'Preferred name', 'General', 'text', 'Diego'),
    field('embedding_model', 'Embedding model', 'Models', 'text', DEFAULT_EMBEDDING_MODEL),
    field('auto_rag', 'Retrieve relevant documents automatically', 'Knowledge', 'bool', True),
    field('rag_semantic_weight', 'Semantic retrieval weight', 'Knowledge', 'number', .65, 0, 1),
    field('rag_lexical_weight', 'Lexical retrieval weight', 'Knowledge', 'number', .35, 0, 1),
    field('rag_minimum_score', 'Minimum retrieval score', 'Knowledge', 'number', .08, 0, 1),
    field('max_indexing_workers', 'Concurrent indexing jobs', 'Knowledge', 'integer', 1, 1, 3),
    field('ocr_executable', 'OCR executable', 'OCR', 'text', ''),
    field('automatic_memory_suggestions', 'Suggest useful memories', 'Memory', 'bool', True),
    field('memory_model_extraction', 'Use the local model to extract suggestions', 'Memory', 'bool', False),
    field('auto_memory_approval', 'Automatically approve memory suggestions', 'Memory', 'bool', False),
    field('editor_font', 'Editor font family', 'Studio', 'text', 'Consolas'),
    field('editor_size', 'Editor font size', 'Studio', 'integer', 13, 9, 28),
    field('editor_tab_width', 'Editor tab width', 'Studio', 'integer', 4, 2, 8),
]
for key, label, default, low, high, kind in [
    ('temperature', 'Temperature', .7, 0, 2, 'number'),
    ('top_p', 'Top P', .9, .01, 1, 'number'),
    ('repeat_penalty', 'Repetition penalty', 1.08, 0, 2, 'number'),
    ('max_tokens', 'Maximum output tokens', 4096, 64, 131072, 'integer'),
    ('history_messages', 'Messages in context', 36, 0, 1000, 'integer'),
    ('rag_top_k', 'Retrieved chunks', 6, 1, 50, 'integer'),
]:
    FIELDS.append(field(key, label, 'Chat', kind, default, low, high, target='params'))
for key, label, default, low, high in [
    ('max_searches', 'Search limit', 4, 1, 10), ('max_pages', 'Page limit', 12, 1, 30),
    ('max_link_depth', 'Link depth', 1, 0, 3), ('timeout', 'Research timeout (seconds)', 180, 15, 900),
    ('page_concurrency', 'Concurrent pages', 2, 1, 4), ('page_timeout', 'Page timeout (seconds)', 20, 5, 60),
    ('cache_lifetime', 'Cache lifetime (seconds)', 3600, 0, 604800),
]:
    FIELDS.append(field(key, label, 'Research', 'integer', default, low, high, target='research'))
FIELDS.extend([
    field('browser_provider', 'Research browser provider', 'Research', 'choice', 'auto', choices=['auto', 'http', 'playwright'], target='research'),
    field('search_provider', 'Search provider', 'Research', 'choice', 'ddgs', choices=['ddgs', 'searxng'], target='research'),
    field('search_endpoint', 'Search endpoint', 'Research', 'text', '', target='research'),
    field('depth', 'Default research depth', 'Research', 'choice', 'Standard', choices=['Quick', 'Standard', 'Deep'], target='research'),
    field('default_save_to_knowledge', 'Prefer saving research to Knowledge (permission still required)', 'Research', 'bool', False, target='research'),
])
from ..research.settings import ResearchSettings
_research_defaults = ResearchSettings().to_dict()
for _field in FIELDS:
    if _field['target'] == 'research':
        _field['default'] = _research_defaults[_field['key']]


def schema():
    from ..config import PROMPT_PRESETS
    return {'fields': deepcopy(FIELDS), 'presets': dict(PROMPT_PRESETS)}


def visible(value):
    result = {k: deepcopy(value[k]) for k in ('chat_id', 'model', 'alias', 'system_prompt') if k in value}
    result.update(settings={}, params={})
    for f in FIELDS:
        target = f['target']
        source = value.get('params', {}) if target == 'params' else value.get('settings', {})
        destination = result['params'] if target == 'params' else result['settings']
        if target == 'research':
            source = source.get('research', {})
            destination = destination.setdefault('research', {})
        destination[f['key']] = deepcopy(source.get(f['key'], f['default']))
    return result


def save(services, chat_id, settings, params, system_prompt, alias=''):
    groups = {'settings': dict(settings), 'params': dict(params), 'research': settings.get('research', {})}
    groups['settings'].pop('research', None)
    for target, values in groups.items():
        allowed = {f['key']: f for f in FIELDS if f['target'] == target}
        if not isinstance(values, dict) or set(values) - allowed.keys():
            raise ValueError('Unknown settings field')
        for key, value in values.items():
            f = allowed[key]
            if key == 'preferred_name' and (not isinstance(value, str) or len(value) > 120):
                raise ValueError('Preferred name must be at most 120 characters')
            kind = f['kind']
            valid = (type(value) is bool) if kind == 'bool' else (
                isinstance(value, str) and len(value) <= 4096 if kind in {'text', 'choice'} else
                type(value) in (int, float) and math.isfinite(value) and f['minimum'] <= value <= f['maximum']
                and (kind != 'integer' or value == int(value)))
            if not valid or (f['choices'] and value not in f['choices']):
                raise ValueError(f"Invalid {f['label']}")
    if settings.get('owner_mode') is False:
        owner = getattr(services, 'owner_policy', None)
        if owner and owner.enabled():
            owner.revoke()
            # Stop is independent of the following settings/history write.
            services.desktop.stop()
    return visible(services.data.save_settings(chat_id, settings, params, system_prompt, alias))
