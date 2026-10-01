"""One logical peer over two paths: Direct (LAN) preferred, World as fallback.

A pure, deterministic state machine (mirrored by WorldPathSelector.swift). Every
attempt carries a generation; events from a retired attempt are ignored, so a
late callback from a dead Direct or World transport can never overwrite the
current state. Callers perform the returned actions.
"""
from dataclasses import dataclass, field

DIRECT, WORLD = 'direct', 'world'
STATES = ('offline', 'discovering', 'direct_connecting', 'direct', 'world_connecting', 'world',
          'switching', 'revoked', 'error')
WORLD_FALLBACK_DELAY = 1.5  # Seconds of Direct-only before World starts when the LAN looks usable.


@dataclass
class PathSelector:
    world_available: bool = False      # Provisioned, enabled and supported by this computer.
    direct_allowed: bool = True        # False in explicit test-only "force World" mode.
    world_allowed: bool = True         # False in diagnostics "Direct only" mode.
    state: str = 'offline'
    active: str | None = None
    active_generation: int = 0
    generation: int = 0
    attempts: dict = field(default_factory=dict)  # path -> generation of its in-flight attempt

    def _new(self, path):
        self.generation += 1
        self.attempts[path] = self.generation
        return self.generation

    def start(self, *, lan_usable):
        """Begin a connection cycle. Returns [(action, path, generation, delay)]."""
        if self.state == 'revoked':
            return []
        actions = []
        self.state = 'discovering'
        if self.direct_allowed:
            actions.append(('connect', DIRECT, self._new(DIRECT), 0.0))
            self.state = 'direct_connecting'
        if self.world_allowed and self.world_available:
            delay = WORLD_FALLBACK_DELAY if (self.direct_allowed and lan_usable) else 0.0
            actions.append(('connect', WORLD, self._new(WORLD), delay))
            if not self.direct_allowed:
                self.state = 'world_connecting'
        if not actions:
            self.state = 'offline'
        return actions

    def authenticated(self, path, generation):
        """An OLIVE-authenticated channel exists on ``path``. Returns actions."""
        if self.state == 'revoked' or self.attempts.get(path) != generation:
            return [('close', path, generation, 0.0)]  # Stale or unwanted: retire it.
        self.attempts.pop(path, None)
        if self.active == DIRECT and path == WORLD:
            return [('close', WORLD, generation, 0.0)]  # Direct already wins.
        actions = []
        if self.active is not None and self.active != path:
            actions.append(('close', self.active, self.active_generation, 0.0))
            self.state = 'switching'
        if path == DIRECT:
            pending = self.attempts.pop(WORLD, None)
            if pending is not None:
                actions.append(('cancel', WORLD, pending, 0.0))
        self.active, self.active_generation, self.state = path, generation, path
        return actions

    def failed(self, path, generation):
        """An attempt or an active path ended. Returns actions (possibly a fallback)."""
        if self.state == 'revoked':
            return []
        if self.attempts.get(path) == generation:
            self.attempts.pop(path)
        elif not (self.active == path and self.active_generation == generation):
            return []  # A retired generation: ignore.
        if self.active == path and self.active_generation == generation:
            self.active = None
        actions = []
        if self.active is None:
            if path == DIRECT and self.world_allowed and self.world_available and WORLD not in self.attempts:
                actions.append(('connect', WORLD, self._new(WORLD), 0.0))  # Direct died: World takes over now.
                self.state = 'world_connecting'
            elif self.attempts:
                self.state = 'world_connecting' if WORLD in self.attempts else 'direct_connecting'
            else:
                self.state = 'offline'
        return actions

    def direct_candidate(self):
        """On World with the LAN back (path change / discovery): try Direct alongside."""
        if self.state != WORLD or not self.direct_allowed or DIRECT in self.attempts:
            return []
        return [('connect', DIRECT, self._new(DIRECT), 0.0)]

    def revoke(self):
        actions = [('close', p, g, 0.0) for p, g in self.attempts.items()]
        if self.active is not None:
            actions.append(('close', self.active, self.active_generation, 0.0))
        self.attempts.clear()
        self.active, self.state = None, 'revoked'
        return actions
