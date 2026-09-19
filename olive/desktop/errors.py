"""Typed failures shared by provider adapters and bounded execution loops."""


class ObservationUnavailable(RuntimeError):
    """An accessibility snapshot disappeared while the provider was reading it."""
