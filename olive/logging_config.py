from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LOGS_DIR


def configure_logging(logs_dir: Path = LOGS_DIR) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "olive.log"
    logger = logging.getLogger("olive")
    logger.setLevel(logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(path.resolve())
               for handler in logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return path
