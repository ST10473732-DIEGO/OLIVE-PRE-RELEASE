"""Qt transport for UI-neutral controller operations; no widgets in workers."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
import uuid

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from ..agent.confirmation_service import ConfirmationResponse

log = logging.getLogger(__name__)


class RuntimeThread(QThread):
    event = Signal(str, object)
    result = Signal(str, object, str)
    ready = Signal()
    confirmation = Signal(object)

    def __init__(self, factory=None):
        super().__init__()
        self.factory = factory
        self.loop = None
        self.services = None
        self.pending_confirmations = {}
        self.operations = set()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            from ..application.service_container import ServiceContainer

            self.services = (self.factory or ServiceContainer)(self.event.emit, self.ask_confirmation)
            self.ready.emit()
            self.loop.create_task(self.services.initialize())
            self.loop.run_forever()
        except Exception:
            log.exception("OLIVE runtime failed")
            self.event.emit("fatal", "OLIVE could not initialize. See the local log for details.")
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()

    async def ask_confirmation(self, request):
        future = self.loop.create_future()
        self.pending_confirmations[request.id] = future
        self.confirmation.emit(deepcopy(request))
        try:
            return await future
        finally:
            self.pending_confirmations.pop(request.id, None)

    def answer(self, request_id, response):
        def resolve():
            future = self.pending_confirmations.get(request_id)
            if future and not future.done():
                future.set_result(response)

        # A dialog may finish while shutdown has already denied its request.
        # Late UI callbacks cannot revive or approve an action after loop teardown.
        if self.loop is not None and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(resolve)
            except RuntimeError:
                if not self.loop.is_closed():
                    raise

    async def invoke(self, request_id, operation, arguments):
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            value = await self.services.dispatch(operation, arguments)
            self.result.emit(request_id, value, "")
        except asyncio.CancelledError:
            self.result.emit(request_id, None, "Operation cancelled")
        except Exception as exc:
            log.exception("Application operation failed: %s", operation)
            self.result.emit(request_id, None, str(exc) or type(exc).__name__)
        finally:
            self.operations.discard(task)

    async def shutdown(self):
        for future in list(self.pending_confirmations.values()):
            if not future.done():
                future.set_result(ConfirmationResponse(False, cancel_task=True))
        await self.services.shutdown()
        active = list(self.operations)
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        self.loop.call_soon(self.loop.stop)


class BackendBridge(QObject):
    """All outward signals and callback delivery occur on this QObject's GUI thread."""

    event = Signal(str, object)
    ready = Signal()
    confirmation = Signal(object)
    stopped = Signal()

    def __init__(self, factory=None):
        super().__init__()
        self.worker = RuntimeThread(factory)
        self.callbacks = {}
        self.queue = []
        self.is_ready = False
        self.closing = False
        self.worker.ready.connect(self._ready, Qt.ConnectionType.QueuedConnection)
        self.worker.event.connect(self._event, Qt.ConnectionType.QueuedConnection)
        self.worker.result.connect(self._result, Qt.ConnectionType.QueuedConnection)
        self.worker.confirmation.connect(self._confirmation, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.stopped)

    def start(self):
        self.worker.start()

    def stop_control(self):
        services = self.worker.services
        if services and hasattr(services, "desktop"):
            services.desktop.stop_event.set()
        self.call("desktop.stop")

    @Slot()
    def _ready(self):
        self.is_ready = True
        if not self.closing:
            for request in self.queue:
                self._submit(*request)
        self.queue.clear()
        self.ready.emit()

    @Slot(str, object)
    def _event(self, topic, value):
        self.event.emit(topic, value)

    @Slot(object)
    def _confirmation(self, request):
        self.confirmation.emit(request)

    @Slot(str, object, str)
    def _result(self, request_id, value, error):
        callback = self.callbacks.pop(request_id, None)
        if error:
            self.event.emit("notification", {"kind": "error", "message": error})
        if callback:
            callback(value, error)

    def call(self, operation, callback=None, **arguments):
        if self.closing:
            return None
        request_id = str(uuid.uuid4())
        if callback:
            self.callbacks[request_id] = callback
        request = (request_id, operation, deepcopy(arguments))
        if self.is_ready:
            self._submit(*request)
        else:
            self.queue.append(request)
        return request_id

    def _submit(self, request_id, operation, arguments):
        asyncio.run_coroutine_threadsafe(
            self.worker.invoke(request_id, operation, arguments), self.worker.loop
        )

    def answer(self, request_id, response):
        self.worker.answer(request_id, response)

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        if not self.worker.isRunning():
            self.queue.clear()
            self.callbacks.clear()
            self.stopped.emit()
            return
        if self.is_ready:
            future = asyncio.run_coroutine_threadsafe(self.worker.shutdown(), self.worker.loop)

            def report(future):
                if future.exception():
                    log.error("Runtime shutdown failed", exc_info=future.exception())
                    self.worker.event.emit("fatal", "Shutdown failed; inspect local logs before exiting.")

            future.add_done_callback(report)
        else:
            self.worker.ready.connect(self._shutdown_when_ready, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _shutdown_when_ready(self):
        asyncio.run_coroutine_threadsafe(self.worker.shutdown(), self.worker.loop)
