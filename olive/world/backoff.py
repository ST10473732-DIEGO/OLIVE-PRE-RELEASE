"""Bounded exponential reconnect with jitter (mirrored by WorldBackoff.swift)."""
import random

DELAYS = (0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
STABLE_AFTER = 30.0  # A connection that lived this long resets the schedule.


class Backoff:
    def __init__(self, delays=DELAYS, *, jitter=0.2, rng=None):
        self.delays, self.jitter = tuple(delays), jitter
        self.attempt = 0
        self.rng = rng or random.Random()

    def next(self):
        base = self.delays[min(self.attempt, len(self.delays) - 1)]
        self.attempt += 1
        # +/- jitter keeps many clients from reconnecting in lockstep after a relay restart.
        return max(0.05, base * (1 + self.rng.uniform(-self.jitter, self.jitter)))

    def reset(self):
        self.attempt = 0

    def settled(self, lived_seconds):
        """Reset only after a stable connection, so a flapping path keeps backing off."""
        if lived_seconds >= STABLE_AFTER:
            self.reset()
