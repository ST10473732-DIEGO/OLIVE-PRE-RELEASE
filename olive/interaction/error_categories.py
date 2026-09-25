"""Exact, concise failure categories for user-facing task results.

Messages already carrying a category keep it. Otherwise a conservative keyword
map assigns one; unknown failures stay uncategorized rather than mislabelled.
No private traces, observation text or model output are added.
"""
import re

CATEGORIES = ('TARGET_NOT_VISIBLE', 'TARGET_AMBIGUOUS', 'DESTINATION_UNVERIFIED', 'COMPOSER_UNVERIFIED',
              'ACCOUNT_UNVERIFIED', 'WINDOW_CHANGED', 'STALE_OBSERVATION', 'OWNER_DENY', 'OS_AUTH_REQUIRED',
              'MODEL_RESOURCE_BUSY', 'MODEL_OUTPUT_BUDGET', 'PLAN_INCOMPLETE', 'PLAN_SCOPE_EXPANSION',
              'RESULT_PROVENANCE_INVALID', 'APP_CRASHED_DURING_OBSERVATION', 'CANCELLED', 'READY_TO_SEND',
              'NEEDS_USER_CLARIFICATION', 'MESSAGING_ACCOUNT_UNVERIFIED', 'COMPOSER_SEMANTICS_UNVERIFIED',
              'MESSAGING_VISUAL_CONTEXT_UNVERIFIED', 'ACCESSIBILITY_BUS_ERROR')
RULES = (
    (r'ambiguous|not unique|several|multiple windows|choose the intended', 'TARGET_AMBIGUOUS'),
    (r'missing or disabled|not visible|not found|no visible|could not be resolved|not uniquely visible', 'TARGET_NOT_VISIBLE'),
    (r'focus or geometry|lost focus|geometry changed|window was replaced|focus changed', 'WINDOW_CHANGED'),
    (r'stale|observe again|changed while', 'STALE_OBSERVATION'),
    (r'permission denied|\bdeny\b|denied', 'OWNER_DENY'),
    (r'polkit|authentication is required|not authorized', 'OS_AUTH_REQUIRED'),
    (r'gpu release|model .*busy|resource busy|insufficient (?:gpu|memory)', 'MODEL_RESOURCE_BUSY'),
    (r'answer budget|output limit|budget exhausted', 'MODEL_OUTPUT_BUDGET'),
    (r'destination is unresolved|destination changed|recipient', 'DESTINATION_UNVERIFIED'),
    (r'composer', 'COMPOSER_UNVERIFIED'),
    (r'\baccount\b', 'ACCOUNT_UNVERIFIED'),
    (r'stopped|cancelled|canceled', 'CANCELLED'),
)


def categorize(message):
    text = str(message or '').strip()
    prefix = re.match(r'([A-Z][A-Z_]{5,})\b', text)
    if prefix and prefix.group(1) in CATEGORIES:
        return prefix.group(1)
    lowered = text.casefold()
    for pattern, category in RULES:
        if re.search(pattern, lowered):
            return category
    return ''


def labelled(message):
    category = categorize(message)
    text = str(message or '').strip()
    return text if not category or text.startswith(category) else category + ': ' + text
