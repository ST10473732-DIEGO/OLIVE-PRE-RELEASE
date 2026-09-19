from .identity import normalize_environment
normalize_environment()
from .config import APP_NAME, APP_VERSION

__all__ = ["APP_NAME", "APP_VERSION"]
