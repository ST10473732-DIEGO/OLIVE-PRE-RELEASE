"""Private stdin fixture peer. Not imported or reachable by production OLIVE."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from olive.connect.service import DesktopDeviceService
from olive.connect.identity import DeviceKeyStore
from olive.connect.contracts import canonical
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import request

service = DesktopDeviceService(Path(sys.argv[1]), key_store=DeviceKeyStore(MemoryVault()))
channel = None
requests = {}
try:
    for line in sys.stdin:
        data = json.loads(line)
        command = data['command']
        try:
            if command == 'accept':
                value = service.pairing.accept_offer(data['offer'].encode()).decode()
            elif command == 'exchange':
                value = service.pairing.exchange(data['sid'], bytes.fromhex(data['incoming'])).hex()
            elif command == 'preview':
                value = service.pairing.preview(data['sid'])['comparison']
            elif command == 'confirm':
                service.pairing.confirm(data['sid'], data['comparison']); value = True
            elif command == 'complete':
                record = service.pairing.complete(data['sid'])
                service.set_permission(record['device_id'], 'connect.ping', 'allow')
                value = service.local_id
            elif command == 'connect':
                network = service.enable_network('127.0.0.1', discovery=False)
                channel = network.connect(data['peer'], '127.0.0.1', data['port'])
                value = dict(id=service.local_id,port=network.port)
            elif command == 'status':
                value = service.network.status(data['peer'])
            elif command == 'stop_reconnect':
                with service.network.lock:
                    service.network.targets.clear()
                value = True
            elif command == 'request':
                key = data['key']
                if key not in requests:
                    class Target: local_id = data['peer']
                    requests[key] = request(service, Target)
                value = channel.request(canonical(requests[key]))
            elif command == 'close':
                break
            else:
                raise ValueError('Unknown fixture command')
            print(json.dumps(dict(ok=True,value=value)),flush=True)
        except Exception as error:
            print(json.dumps(dict(ok=False,error=str(error))),flush=True)
finally:
    service.close()
