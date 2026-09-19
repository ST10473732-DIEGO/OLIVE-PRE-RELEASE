"""Authorise a local preview only for a listener owned by an active RunSession."""
from ..services.local_preview import authorize  # Stable bridge compatibility entry.

__all__ = ['authorize']
