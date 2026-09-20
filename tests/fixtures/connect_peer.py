"""Private stdin fixture peer. Not imported or reachable by production OLIVE."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from olive.connect.service import DesktopDeviceService
from olive.connect.identity import DeviceKeyStore
from olive.connect.contracts import canonical
from olive.connect.workspace import DevicesWorkspace
import time
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import request

service = DesktopDeviceService(Path(sys.argv[1]), key_store=DeviceKeyStore(MemoryVault()))
from olive.personal.service import PersonalService
personal = PersonalService(Path(sys.argv[1]) / 'personal.sqlite3')
service.attach_sync(personal)
workspace = DevicesWorkspace(service)
service.rename(service.local_id, 'Paired device')
channel = None
requests = {}
try:
    for line in sys.stdin:
        data = json.loads(line)
        command = data['command']
        try:
            if command == 'create':
                if service.network is None:
                    service.enable_network('127.0.0.1', discovery=False)
                value = workspace.create_pairing()
            elif command == 'cancel':
                service.pairing_transport.cancel(data['sid']); value = True
            elif command == 'accept':
                if service.network is None:
                    service.enable_network('127.0.0.1', discovery=False)
                value = workspace.accept_pairing(data['offer'])
            elif command == 'exchange':
                value = service.pairing.exchange(data['sid'], bytes.fromhex(data['incoming'])).hex()
            elif command == 'preview':
                value = service.pairing.preview(data['sid'])['comparison']
            elif command == 'confirm':
                service.pairing.confirm(data['sid'], data['comparison']); value = True
            elif command == 'complete':
                deadline = time.monotonic() + 5
                while workspace.pairing_status(data['sid'])['state'] != 'completed':
                    if time.monotonic() > deadline:
                        raise RuntimeError('Pairing completion timeout')
                    time.sleep(.03)
                record = service.paired_devices()[0]
                service.set_permission(record['device_id'], 'connect.ping', 'allow')
                value = service.local_id
            elif command == 'connect':
                network = service.network or service.enable_network('127.0.0.1', discovery=False)
                channel = network.connect(data['peer'], '127.0.0.1', data['port'])
                value = dict(id=service.local_id,port=network.port)
            elif command == 'file_send':
                service.set_permission(data['peer'], 'files.send', 'allow')
                path = Path(sys.argv[1]) / 'RaceDay.bin'
                path.write_bytes(bytes(range(256)) * 8192)
                value = service.files.prepare(data['peer'], path)
                service.files.start(value['transfer_id'])
            elif command == 'file_list':
                value = service.files.list()
            elif command == 'file_receive_allow':
                service.set_permission(data['peer'], 'files.receive', 'allow'); value = True
            elif command == 'sync_setup':
                service.set_permission(data['peer'], 'sync.tasks', 'allow')
                value = personal.save('task', {'title': 'C5 synthetic task'})
            elif command == 'sync_edit':
                task = personal.search('task')['items'][0]
                value = personal.save('task', {**personal.store.body(task), 'title': 'Peer changed task'}, task['id'], task['revision'])
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
