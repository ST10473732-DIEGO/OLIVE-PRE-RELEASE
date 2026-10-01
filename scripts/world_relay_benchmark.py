"""OLIVE Connect World: local relay overhead benchmark (loopback only).

Measures, for Direct (LAN TLS) and World (same TLS through a local development
relay): authenticated connection establishment, a small request round trip,
and a 16 MiB olive-chat/1 artifact download in 128 KiB chunks. Loopback numbers
show relay/bridge overhead only; they say nothing about internet performance.

    python scripts/world_relay_benchmark.py [--json out.json]
"""
import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from olive.connect import chat_protocol as cp  # noqa: E402
from olive.connect.contracts import canonical  # noqa: E402
from olive.connect.identity import DeviceKeyStore  # noqa: E402
from olive.connect.service import DesktopDeviceService  # noqa: E402
from olive.connect.world_peer import WorldPeer, provision  # noqa: E402
from tests.fixtures.chat_test_runtime import ChatTestRuntime  # noqa: E402
from tests.test_connect_network import pair, request, until  # noqa: E402
from tests.test_connect_pairing import MemoryVault  # noqa: E402
from tests.world_fixture import RelayThread  # noqa: E402

SIZE = 16 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json')
    parser.add_argument('--rounds', type=int, default=15)  # Connect allows 60 requests a minute per peer.
    args = parser.parse_args()
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    relay = RelayThread().start()
    data = hashlib.sha256(b'bench').digest() * (SIZE // 32)
    runtime = ChatTestRuntime(root / 'artifacts', video=lambda: data)
    desk = DesktopDeviceService(root / 'desk', key_store=DeviceKeyStore(MemoryVault()))
    phone = DesktopDeviceService(root / 'phone', key_store=DeviceKeyStore(MemoryVault()))
    desk.attach_chat(runtime, loop)
    pair(phone, desk)
    nd = desk.enable_network('127.0.0.1', discovery=False)
    phone.enable_network('127.0.0.1', discovery=False)
    desk.set_permission(phone.local_id, 'connect.ping', 'allow')
    desk.set_permission(phone.local_id, 'models.remote', 'allow')
    results = {'note': 'Loopback on one machine: relay and bridge overhead only, not internet performance.'}

    def direct():
        return phone.network.connect(desk.local_id, '127.0.0.1', nd.port)

    def drop(channel):
        phone.network.disconnect(desk.local_id)
        until(lambda: desk.local_id not in phone.network.channels and phone.local_id not in nd.channels, 6)

    def measure(name, connect):
        connects, rtts = [], []
        for _ in range(3):   # Connect's own rate limit allows 12 new channels a minute.
            started = time.perf_counter()
            channel = connect()
            connects.append((time.perf_counter() - started) * 1000)
            drop(channel)
        channel = connect()
        for _ in range(args.rounds):
            started = time.perf_counter()
            channel.request(canonical(request(phone, desk)))
            rtts.append((time.perf_counter() - started) * 1000)
        job = dict(job_id=__import__('uuid').uuid4().__str__(), conversation_id=__import__('uuid').uuid4().__str__(),
                   mode='video', voice=None, messages=[dict(role='user', content='bench')], attachments=[])
        job['input_fingerprint'] = cp.start_fingerprint(job)
        call = lambda op, a: cp.unpack(channel.chat_request(cp.request(phone.local_id, desk.local_id, op, a, now=int(time.time()))))
        call('start', job)
        while True:
            value, _ = call('poll', dict(job_id=job['job_id'], after=0))
            if value['result']['state'] in cp.TERMINAL:
                break
            time.sleep(.05)
        artifact = value['result']['artifacts'][0]
        received, started = 0, time.perf_counter()
        while received < artifact['size']:
            _, chunk = call('artifact_chunk', dict(artifact_id=artifact['artifact_id'], offset=received, length=cp.CHUNK_BYTES))
            received += len(chunk)
        seconds = time.perf_counter() - started
        drop(channel)
        results[name] = dict(connect_ms_median=round(statistics.median(connects), 1),
                             connect_ms_max=round(max(connects), 1),
                             request_rtt_ms_median=round(statistics.median(rtts), 2),
                             request_rtt_ms_p90=round(sorted(rtts)[int(len(rtts) * .9)], 2),
                             download_mib=round(SIZE / 1048576, 1), download_seconds=round(seconds, 2),
                             download_mib_per_s=round(SIZE / 1048576 / seconds, 2))

    measure('direct_world_off', direct)
    desk.world.dev = True
    desk.world.set_relay_url(relay.url)
    desk.world.set_enabled(True)
    channel = direct()
    peer = WorldPeer(phone, desk.local_id, dev=True)
    peer.store(provision(channel, phone, desk.local_id))
    drop(channel)
    until(lambda: desk.world.status()['peers'][phone.local_id]['route'] == 'registered', 6)
    measure('direct_world_on', direct)

    def world():
        for _ in range(40):
            try:
                return peer.connect(wait=3)
            except Exception:
                time.sleep(.1)
        raise RuntimeError('world did not connect')
    measure('world', world)
    peer.close(); phone.close(); desk.close(); relay.stop(); temp.cleanup()
    print(json.dumps(results, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))


if __name__ == '__main__':
    main()
