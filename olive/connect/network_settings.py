"""Opt-in local listener preferences. No trust, keys or firewall privileges."""
from dataclasses import asdict
import ipaddress
import json
import os
import tempfile

from .contracts import ConnectError


class NetworkSettingsStore:
    def __init__(self, profile):
        self.path = profile / 'connect' / 'network-v1.json'

    @staticmethod
    def validate(value):
        keys = {'version', 'enabled', 'interface', 'port', 'pairing_port', 'discovery'}
        def require(condition):
            if not condition:
                raise ValueError()
        try:
            require(type(value) is dict and set(value) == keys)
            require(type(value['version']) is int and value['version'] == 1)
            require(type(value['enabled']) is bool and type(value['discovery']) is bool)
            interface = value['interface']
            require(type(interface) is dict and set(interface) == {'name', 'address', 'network'})
            require(type(interface['name']) is str and 0 < len(interface['name']) <= 128)
            address = ipaddress.ip_address(interface['address'])
            network = ipaddress.ip_network(interface['network'])
            require(not address.is_unspecified and not address.is_multicast and address in network)
            for key in ('port', 'pairing_port'):
                require(type(value[key]) is int and 1024 <= value[key] <= 65535)
            require(value['port'] != value['pairing_port'])
        except (ValueError, TypeError, KeyError):
            raise ConnectError('network_settings_invalid') from None
        return value

    def load(self):
        try:
            with self.path.open('rb') as source:
                raw = source.read(2049)
            if len(raw) > 2048:
                raise ValueError()
            return self.validate(json.loads(raw))
        except FileNotFoundError:
            return None  # Existing installations retain session-only/off startup.
        except (OSError, ValueError, UnicodeError):
            raise ConnectError('network_settings_invalid') from None

    def save(self, value):
        self.validate(value)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')
        if len(raw) > 2048:
            raise ConnectError('network_settings_invalid')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.network-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def disable(self):
        value = self.load()
        if value:
            self.save({**value, 'enabled': False})

    @staticmethod
    def matches(value, interface):
        return value['interface'] == asdict(interface)
