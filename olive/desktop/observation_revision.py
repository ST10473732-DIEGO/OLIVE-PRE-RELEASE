"""Observation revisions: every action names the observation it was planned against.

An observation captures the bound window's identity, geometry, monitor, any
open dialog and a digest of the semantic controls. Before input the executor
observes again; any difference makes the planned action stale. A stale action
is never "adjusted": it is discarded, the UI is re-observed and the next step is
planned from the new observation. Coordinates planned against an old geometry
therefore expire when the window moves, resizes or changes monitor.
"""
from dataclasses import dataclass
import hashlib
import itertools
import json
import time


class StaleObservation(ValueError):
    def __init__(self, reason):
        super().__init__('STALE_OBSERVATION: ' + reason + '; the planned action was discarded and nothing was sent')
        self.reason = reason


CONTROL_KEYS = ('id', 'name', 'role', 'enabled', 'focused', 'selected', 'editable', 'bounds', 'value', 'parent')


def controls_digest(controls):
    """Digest of the semantic state that planning used (never stored as text)."""
    rows = [{k: c.get(k) for k in CONTROL_KEYS} for c in (controls or [])]
    raw = json.dumps(rows, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()


@dataclass(frozen=True)
class Observation:
    revision: str
    window_id: str
    pid: int
    app_id: str
    bounds: tuple
    output: str
    dialog: str          # window id of a dialog attached to the bound window, '' when none
    content: str         # controls digest
    title: str = ''
    taken_at: float = 0.0


class Revisions:
    """Monotonic revision source for one desktop task."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.counter = itertools.count(1)
        self.latest = None

    def observe(self, window, controls=(), dialog=''):
        observation = Observation(f'r{next(self.counter)}', window.window_id, window.pid, window.app_id,
                                  tuple(window.bounds), window.output, dialog, controls_digest(controls),
                                  window.title, self.clock())
        self.latest = observation
        return observation

    def invalidate(self):
        """After any input or Stop: nothing planned earlier may run."""
        self.latest = None


def stale_reason(planned, current, *, content=True):
    """Why an action planned against `planned` must not run on `current` ('' when fresh)."""
    if current is None or planned is None:
        return 'no current observation'
    if current.window_id != planned.window_id or current.pid != planned.pid or current.app_id != planned.app_id:
        return 'the window changed'
    if current.output != planned.output:
        return 'the window moved to another monitor'
    if tuple(current.bounds) != tuple(planned.bounds):
        if planned.bounds and current.bounds and tuple(current.bounds[2:]) == tuple(planned.bounds[2:]):
            return 'the window moved'
        return 'the window was resized'
    if current.dialog != planned.dialog:
        return 'a dialog appeared' if current.dialog else 'a dialog closed'
    if content and current.content != planned.content:
        return 'the controls changed'
    return ''


def require_fresh(action_revision, planned, current, *, content=True):
    """Gate for input: the action's revision must be the latest and still match the UI."""
    if planned is None or action_revision != planned.revision:
        raise StaleObservation('the action was planned against an older observation')
    reason = stale_reason(planned, current, content=content)
    if reason:
        raise StaleObservation(reason)
    return current


@dataclass(frozen=True)
class CoordinateTarget:
    """Tightly scoped coordinate fallback: valid only for one window geometry and revision."""
    window_id: str
    revision: str
    bounds: tuple        # window bounds when the point was planned
    point: tuple         # global logical point inside those bounds
    label: str = ''

    def check(self, observation):
        if observation is None or observation.revision != self.revision:
            raise StaleObservation('the coordinate target belongs to an older observation')
        if observation.window_id != self.window_id or tuple(observation.bounds) != tuple(self.bounds):
            raise StaleObservation('the window moved or changed, so the coordinates expired')
        x, y = self.point
        bx, by, bw, bh = self.bounds
        if not (bx <= x < bx + bw and by <= y < by + bh):
            raise StaleObservation('the coordinate target is outside the bound window')
        return self.point
