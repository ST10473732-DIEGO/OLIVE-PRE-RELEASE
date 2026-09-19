import logging
import tempfile
import unittest
from pathlib import Path

from olive.logging_config import configure_logging


class LoggingConfigTests(unittest.TestCase):
    def test_creates_rotating_local_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = logging.getLogger("olive")
            original_handlers = list(logger.handlers)
            path = configure_logging(Path(tmp) / "logs")
            logging.getLogger("olive.test").error("diagnostic without conversation content")
            for handler in logger.handlers:
                handler.flush()
            self.assertTrue(path.exists())
            self.assertIn("diagnostic without conversation content", path.read_text(encoding="utf-8"))
            for handler in list(logger.handlers):
                if handler not in original_handlers:
                    logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
