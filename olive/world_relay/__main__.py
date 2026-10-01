"""python -m olive.world_relay --host 127.0.0.1 --port 8765 --dev"""
import argparse
import asyncio
import ipaddress
import logging
import os
import signal
import ssl
import sys

from ..world.wire import is_loopback, is_private
from .server import Limits, Relay, VERSION


def options(argv=None, environ=os.environ):
    env = lambda name, default=None: environ.get('OLIVE_WORLD_RELAY_' + name, default)
    parser = argparse.ArgumentParser(prog='python -m olive.world_relay',
                                     description='OLIVE Connect World relay (blind, stateless).')
    parser.add_argument('--host', default=env('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(env('PORT', '8765')))
    parser.add_argument('--dev', action='store_true', default=env('DEV') == '1',
                        help='Development: plaintext ws:// on a loopback address only.')
    parser.add_argument('--test-lan', action='store_true', default=env('TEST_LAN') == '1',
                        help='TEST ONLY: plaintext ws:// on a private LAN address (Mac physical-iPhone test host).')
    parser.add_argument('--behind-proxy', action='store_true', default=env('BEHIND_PROXY') == '1',
                        help='Plaintext listener behind a TLS-terminating reverse proxy.')
    parser.add_argument('--tls-cert', default=env('TLS_CERT'))
    parser.add_argument('--tls-key', default=env('TLS_KEY'))
    parser.add_argument('--trusted-proxy', action='append',
                        default=[p for p in (env('TRUSTED_PROXIES') or '').split(',') if p.strip()],
                        help='Address of a reverse proxy allowed to set X-Forwarded-For (repeatable).')
    parser.add_argument('--max-connections', type=int, default=int(env('MAX_CONNECTIONS', '2048')))
    parser.add_argument('--per-ip-connections', type=int, default=int(env('PER_IP_CONNECTIONS', '64')))
    parser.add_argument('--log-level', default=env('LOG_LEVEL', 'INFO'))
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args(argv)
    for proxy in args.trusted_proxy:
        ipaddress.ip_address(proxy.strip())
    tls = bool(args.tls_cert or args.tls_key)
    if tls and not (args.tls_cert and args.tls_key):
        parser.error('--tls-cert and --tls-key go together')
    if not tls:
        if args.dev and not is_loopback(args.host):
            parser.error('--dev serves plaintext only on a loopback address')
        if args.test_lan and not is_private(args.host):
            parser.error('--test-lan serves plaintext only on a private LAN address')
        if not args.dev and not args.test_lan and not args.behind_proxy:
            parser.error('production needs TLS (--tls-cert/--tls-key) or --behind-proxy with a TLS reverse proxy')
    return args


async def run(args):
    context = None
    if args.tls_cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tls_cert, args.tls_key)
    relay = Relay(Limits(max_connections=args.max_connections, per_ip_connections=args.per_ip_connections),
                  trusted_proxies=[p.strip() for p in args.trusted_proxy])
    port = await relay.start(args.host, args.port, ssl=context)
    logging.getLogger('olive.world_relay').info(
        'event=listening version=%s port=%d tls=%s dev=%s', VERSION, port, bool(context), args.dev)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ('SIGINT', 'SIGTERM'):
        if hasattr(signal, name):
            try:
                loop.add_signal_handler(getattr(signal, name), stop.set)
            except (NotImplementedError, RuntimeError):
                pass  # Windows: Ctrl+C raises KeyboardInterrupt instead.
    try:
        await stop.wait()
    finally:
        await relay.shutdown()
        logging.getLogger('olive.world_relay').info('event=stopped')


def main(argv=None):
    args = options(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(name)s %(message)s', stream=sys.stdout)
    # asyncio's own debug/exception logs could otherwise print tracebacks with peer state.
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
