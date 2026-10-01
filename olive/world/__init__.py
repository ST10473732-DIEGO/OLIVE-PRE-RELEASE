"""OLIVE Connect World: an outbound relay path beneath OLIVE Connect.

This package is standard-library only so the relay (``olive.world_relay``) can be
deployed without the desktop application. The relay only ever sees the opaque
bytes of the paired devices' existing TLS 1.3 session.
"""
