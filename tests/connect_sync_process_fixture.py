"""Ordinary C3 services, native repositories and owned synthetic subprocesses."""
from pathlib import Path
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.personal.service import PersonalService
from olive.storage.chat_repository import ChatRepository
from olive.models import Chat
from tests.test_connect_pairing import MemoryVault


def worker(pipe, profile, values):
    vault = MemoryVault(); vault.values = values
    path = Path(profile)
    service = DesktopDeviceService(path, key_store=DeviceKeyStore(vault))
    personal = PersonalService(path / 'personal.sqlite3')
    sync = service.attach_sync(personal)
    chats = ChatRepository(path / 'chats.json')
    sync.store.attach_chat(chats)
    try:
        net = service.enable_network('127.0.0.1', discovery=False)
        pipe.send(net.port)
        while True:
            command = pipe.recv(); op, *args = command
            try:
                if op == 'stop':
                    service.close(); pipe.send(True); return
                if op == 'connect':
                    net.connect(args[0], '127.0.0.1', args[1]); result = True
                elif op == 'sync':
                    sync.start(args[0]); sync.worker.join(12); result = sync.status()
                elif op == 'save': result = personal.save(*args)
                elif op == 'get': result = personal.get(*args)
                elif op == 'search': result = personal.search(*args)
                elif op == 'delete': result = personal.delete(*args)
                elif op == 'conflicts': result = sync.store.conflicts()
                elif op == 'resolve': result = sync.store.resolve(*args)
                elif op == 'disconnect': net.disconnect(args[0]); result = True
                elif op == 'revoke': service.revoke(args[0]); result = True
                elif op == 'revision':
                    with personal.store.transaction() as db:
                        sync.store.capture(db); result = sync.store.current(db, args[0]).value()
                elif op == 'chat':
                    chat = Chat(title=args[0]); chat.add_message('user', 'Message one'); chat.add_message('assistant', 'Message two')
                    all_chats = chats.load_all(); all_chats[chat.id] = chat; chats.save_all(all_chats.values()); result = chat.to_dict()
                elif op == 'select': result = sync.store.chat.select(*args)
                elif op == 'chats': result = {k: c.to_dict() for k, c in chats.load_all().items()}
                elif op == 'append':
                    all_chats = chats.load_all(); result = all_chats[args[0]].add_message('user', args[1]).to_dict(); chats.save_all(all_chats.values())
                else: raise ValueError('unknown fixture command')
                pipe.send(result)
            except Exception as error:
                pipe.send({'fixture_error': type(error).__name__ + ':' + str(error)})
    finally:
        service.close(); pipe.close()
