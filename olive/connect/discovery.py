"""Untrusted DNS-SD directory. No discovery value can write a pairing record."""
from dataclasses import dataclass
import ipaddress
import os
import socket
import threading
import time
import uuid

import psutil

from .contracts import ConnectError

SERVICE = '_olive-connect._tcp.local.'


@dataclass(frozen=True)
class Interface:
    name: str
    address: str
    network: str

    def permits(self, address):
        try:
            ip = ipaddress.ip_address(address)
            return ip in ipaddress.ip_network(self.network) and not ip.is_multicast and not ip.is_unspecified
        except ValueError:
            return False


def interfaces():
    """Candidates only: selection is always an explicit local developer action."""
    result = []
    stats = psutil.net_if_stats()
    excluded = ('docker', 'veth', 'virbr', 'br-', 'tun', 'tap', 'wg', 'tailscale',
                'vpn', 'virtual', 'vmware', 'vbox', 'hyper-v', 'zt')
    for name, addresses in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup or any(x in name.lower() for x in excluded):
            continue
        for entry in addresses:
            if entry.family not in (socket.AF_INET, socket.AF_INET6) or '%' in entry.address:
                continue
            ip = ipaddress.ip_address(entry.address)
            # Only RFC1918, loopback and IPv6 ULA. Scoped link-local needs a later adapter.
            allowed = ip.is_loopback or any(ip in ipaddress.ip_network(n) for n in
                (('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16') if ip.version == 4 else ('fc00::/7',)))
            if not allowed or not entry.netmask:
                continue
            mask = ipaddress.ip_address(entry.netmask)
            bits = bin(int(mask))[2:].zfill(mask.max_prefixlen)
            if '01' in bits:
                continue
            network = ipaddress.ip_network(f'{ip}/{bits.count("1")}', strict=False)
            result.append(Interface(name, str(ip), str(network)))
    return result


DEVELOPER_LOOPBACK = 'OLIVE_CONNECT_DEVELOPER_LOOPBACK'


def pairing_interfaces(environ=None):
    """The networks Devices and first-run setup offer for pairing. Loopback cannot reach an
    iPhone, so it is not a normal choice; it stays available to tests and developer tooling
    (enable_network still accepts it) and is listed only when the developer variable is 1."""
    environ = os.environ if environ is None else environ
    developer = environ.get(DEVELOPER_LOOPBACK) == '1'
    return [i for i in interfaces() if developer or not ipaddress.ip_address(i.address).is_loopback]


class LocalDiscovery:
    def __init__(self, interface, port):
        from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, Zeroconf
        self.interface = interface
        self.lock = threading.Lock()
        self.entries = {}
        self.closed = False
        instance = uuid.uuid4().hex
        self.name = instance + '.' + SERVICE
        self.zc = Zeroconf(interfaces=[interface.address], ip_version=(
            IPVersion.V4Only if ipaddress.ip_address(interface.address).version == 4 else IPVersion.V6Only))
        self.info = ServiceInfo(SERVICE, self.name, port=port,
            addresses=[ipaddress.ip_address(interface.address).packed],
            properties={'product': 'OLIVE', 'version': '1'}, server=instance + '.local.',
            host_ttl=30, other_ttl=30)
        try:
            self.zc.register_service(self.info)
            self.browser = ServiceBrowser(self.zc, SERVICE, self)
        except BaseException:
            self.zc.close()
            raise

    def add_service(self, zc, type_, name):
        if self.closed or name == self.name or len(name) > 128:
            return
        with self.lock:
            if len(self.entries) >= 64 and name not in self.entries:
                return
        info = zc.get_service_info(type_, name, timeout=500)
        if (not info or info.properties != {b'product': b'OLIVE', b'version': b'1'}
                or not 1 <= info.port <= 65535):
            return
        addresses = [a for a in info.parsed_addresses() if self.interface.permits(a)]
        if not addresses:
            return
        with self.lock:
            if not self.closed and (len(self.entries) < 64 or name in self.entries):
                self.entries[name] = dict(instance=name, address=addresses[0], port=info.port,
                                          state='discovered', seen=time.monotonic())

    update_service = add_service

    def remove_service(self, zc, type_, name):
        with self.lock:
            self.entries.pop(name, None)

    def nearby(self):
        with self.lock:
            # Zeroconf removes expired records; unchanged TTL refreshes need not
            # generate update callbacks, so do not expire from callback time.
            return [dict(v) for v in self.entries.values()]

    def close(self):
        self.closed = True
        self.browser.cancel()
        self.zc.unregister_service(self.info)
        self.zc.close()
        with self.lock:
            self.entries.clear()
