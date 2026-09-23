"""Run with explicit OLIVE_DATA_DIR and private stdin/stdout pipes."""
import asyncio
import json
import os
from pathlib import Path
import queue
import sys
import threading

from .contracts import decode, MAX_FRAME, VERSION
from .host import Host
from .public_errors import public_error
from ..runtime.profile_lock import ProfileLock
from ..runtime.request_diagnostics import RequestDiagnostic, current


def stop_from_frame(host, raw):
    """Only validated Stop on the existing private pipe bypasses async dispatch."""
    try:
        request = decode(raw)
    except (ValueError, TypeError):
        return
    if request['method'] == 'desktop.stop':
        host.emergency_stop()
    elif request['method'] == 'interaction.cancel' and host.services:
        native = getattr(host.services.desktop, 'linux', None)
        if native and native.owner is not None and native.owner is host.services.interaction.active.get(request['args']['chat_id']):
            host.emergency_stop()


async def serve():
    directory = os.environ.get('OLIVE_DATA_DIR')
    if not directory or not Path(directory).is_absolute():
        raise RuntimeError('An explicit absolute profile directory is required')
    output = sys.stdout.buffer
    sys.stdout = sys.stderr  # Domain diagnostics cannot corrupt protocol stdout.
    loop = asyncio.get_running_loop()
    incoming = asyncio.Queue(maxsize=64)
    outgoing = queue.Queue(maxsize=256)
    disconnected = threading.Event()
    def send(value):
        frame = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n'
        if len(frame) > MAX_FRAME:
            raise ValueError('Response exceeds protocol bounds')
        try:
            outgoing.put_nowait(frame)
        except queue.Full:
            disconnected.set()
            host.emergency_stop()
            raise RuntimeError('Frontend is not consuming events; control stopped')
    host = Host(send)
    def writer():
        try:
            while (frame := outgoing.get()) is not None:
                output.write(frame)
                output.flush()
        except (BrokenPipeError, OSError):
            disconnected.set()
            host.emergency_stop()
    def reader():
        try:
            while not disconnected.is_set():
                raw = sys.stdin.buffer.readline(MAX_FRAME + 1)
                if not raw or len(raw) > MAX_FRAME:
                    break
                stop_from_frame(host, raw)
                future = asyncio.run_coroutine_threadsafe(incoming.put(raw), loop)
                future.result(timeout=10)
        except Exception:
            pass  # No payload or private content in diagnostics.
        finally:
            disconnected.set()
            host.emergency_stop()
    with ProfileLock(directory):
        await host.start(directory)
        if os.environ.get('OLIVE_UI_PROCESS_ID'):
            from ..runtime.ui_owner import supervisor_owner
            owner = supervisor_owner(int(os.environ['OLIVE_UI_PROCESS_ID']))
            host.services.desktop.gateway.ui_owner = owner
            host.services.desktop.browser.focus.ui_owner = owner
        threading.Thread(target=writer, daemon=True, name='olive-protocol-writer').start()
        threading.Thread(target=reader, daemon=True, name='olive-protocol-reader').start()
        tasks = set()
        async def process(raw):
            identity = None
            diagnostic = None
            token = None
            try:
                request = decode(raw)
                identity = request['id']
                diagnostic = RequestDiagnostic(identity, request['method'])
                diagnostic.identify(request['args'])
                token = current.set(diagnostic)
                result = await host.handle(request)
                send(dict(v=VERSION, kind='response', id=identity, ok=True, result=result))
            except asyncio.CancelledError:
                send(dict(v=VERSION, kind='response', id=identity, ok=False,
                          error={'code': 'Cancelled', 'message': 'The operation was cancelled. Inspect task state for any earlier completed work.'}))
            except Exception as error:
                # Error types are safe; detailed exception text can contain private data.
                public = public_error(error)
                if diagnostic is not None:
                    detail = diagnostic.failure(error, directory)
                    host.publish('request.failure', detail)
                    public.update(request_id=identity, method=request['method'], context_ids=detail['context_ids'], feature=request['method'].split('.')[0],
                                  category=detail['category'], stage=detail['stage'],
                                  recoverable=not isinstance(error, PermissionError))
                    public['message'] += ' Error ID: ' + detail['error_id']
                send(dict(v=VERSION, kind='response', id=identity, ok=False,
                          error=public))
            finally:
                if token is not None:
                    current.reset(token)
        try:
            while not disconnected.is_set() and not host.closed:
                try:
                    raw = await asyncio.wait_for(incoming.get(), .1)
                except TimeoutError:
                    continue
                if len(tasks) >= 32:
                    disconnected.set()
                    break
                task = asyncio.create_task(process(raw))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        finally:
            await host.shutdown()
            await asyncio.gather(*tasks, return_exceptions=True)
            outgoing.put_nowait(None)


if __name__ == '__main__':
    asyncio.run(serve())
