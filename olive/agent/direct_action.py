"""One-use consent for a concrete action invoked by a trusted UI controller.

Never accept this object from model output, tool arguments, or the wire protocol.
It satisfies an ASK, but cannot override a DENY or authorize a changed action.
"""
import hashlib
import json
import time


class DirectAction:
    def __init__(self, task_id, tool, arguments):
        self.task_id = task_id
        self.tool = tool
        self.digest = self._digest(arguments)
        self.expires = time.monotonic() + 30
        self.used = False

    @staticmethod
    def _digest(arguments):
        return hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).digest()

    def consume(self, task_id, tool, arguments):
        if self.used:
            return False
        self.used = True
        return (time.monotonic() <= self.expires and task_id == self.task_id
                and tool == self.tool and self._digest(arguments) == self.digest)
