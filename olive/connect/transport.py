"""Transport seams only. C1 never opens a socket or authenticates a real device."""
from collections import deque
from typing import Protocol

from .contracts import ConnectError, identifier


class ConnectTransport(Protocol):
    def send(self, payload: bytes) -> None: ...
    def receive(self) -> dict | None: ...
    def close(self) -> None: ...
    def status(self) -> str: ...


class DiscoveryProvider(Protocol):
    """Future providers return untrusted hints, never paired device authority."""
    def discover(self) -> list[dict]: ...
    def close(self) -> None: ...


class InProcessFixtureTransport:
    """Explicit synthetic peer binding; not cryptographic authentication."""
    def __init__(self, service, peer_device_id):
        if not service.fixture_mode:
            raise ConnectError('fixtures_disabled')
        self._service = service
        self._peer = identifier(peer_device_id)
        self._responses = deque()
        self._closed = False

    def send(self, payload):
        if self.status() == 'closed':
            raise ConnectError('transport_closed')
        if len(self._responses) >= 32:
            raise ConnectError('transport_queue_full')
        # Service validates byte bounds before JSON parsing and capability logic.
        self._responses.append(self._service.receive_fixture(payload, peer_device_id=self._peer))

    def receive(self):
        if self.status() == 'closed':
            raise ConnectError('transport_closed')
        return self._responses.popleft() if self._responses else None

    def close(self):
        self._closed = True
        self._responses.clear()

    def status(self):
        return 'closed' if self._closed or self._service.closed else 'fixture'
