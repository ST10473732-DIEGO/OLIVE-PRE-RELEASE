"""One owned synthetic window, one exact UIA edit, no messaging or user apps."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.desktop.application_discovery import identity
from olive.desktop.owned_launch import OwnedLaunch, canonical
from olive.desktop.owned_window_wait import wait_for_owned_window


async def main():
    import win32gui
    import win32process
    foreground = win32gui.GetForegroundWindow()
    initial_foreground = {'hwnd':foreground,'pid':win32process.GetWindowThreadProcessId(foreground)[1]}
    fixture = Path(__file__).with_name('desktop_test_app.py')
    child = subprocess.Popen([sys.executable, str(fixture)])
    services = None
    approved = set()
    expected_window = {}
    temporary = tempfile.TemporaryDirectory(prefix='olive-owned-control-')
    try:
        if temporary:
            folder = temporary.name
            async def review(request):
                args = request.arguments
                window = args.get('window_identity', {})
                exact = (bool(expected_window) and window == expected_window
                         and child.poll() is None
                         and request.tool_name not in approved)
                if request.tool_name == 'desktop.keyboard_input':
                    exact = exact and args.get('target') == 'Acceptance text' and args.get('text') == 'Hello from OLIVE'
                elif request.tool_name == 'desktop.control_application':
                    exact = exact and args.get('target') == 'Acceptance text' and args.get('action') == 'set_text'
                elif request.tool_name == 'desktop.inspect_application':
                    exact = exact and 'scope' not in args
                else:
                    exact = False
                if exact:
                    approved.add(request.tool_name)
                return ConfirmationResponse(bool(exact))

            services = ServiceContainer(lambda *args: None, review, folder, migrate=False)
            desktop = services.desktop
            desktop.configure({'enabled': True, 'keyboard_policy': 'ask'})
            live = psutil.Process(child.pid)
            app = identity('Owned OLIVE acceptance fixture','executable',sys.executable)
            record = OwnedLaunch(app,child.pid,live.create_time(),canonical(live.exe()),
                                 (sys.executable,str(fixture)),tuple({canonical(sys.executable),canonical(sys._base_executable)}))
            window = await wait_for_owned_window(record,desktop.gateway.check,timeout=15)
            if window['title'] != 'OLIVE Generic Accessibility Acceptance':
                raise RuntimeError('Unexpected owned window title')
            expected_window.update({key: window.get(key) for key in ('hwnd', 'pid', 'process_created', 'title', 'executable')})
            # Read-only inspection is explicit and restricted to the owned window.
            state = await desktop.inspect_target(app,window)
            controls = [row for row in state['observation']['controls']
                        if row['control_type'] == 'Edit' and row['name'] == 'Acceptance text' and row.get('visible')]
            if len(controls) != 1:
                raise RuntimeError('Fixture edit target was not uniquely observed')
            await desktop.provider.call('activate', window, expected_foreground=initial_foreground)
            target = {'runtime_id': controls[0]['runtime_id']}
            result = await desktop.perform('set_text', target, {'text': 'Hello from OLIVE'}, {**target, 'value': 'Hello from OLIVE'})
            if result['session']['status'] != 'completed':
                raise AssertionError('Real target text was not verified')
            print(json.dumps({'classification': 'live local UIA service; owned synthetic window',
                              'verified_text': 'Hello from OLIVE', 'approved_permissions': sorted(approved)}))
            await services.shutdown()
            services = None
    finally:
        try:
            if services:
                await services.shutdown()
        finally:
            if child.poll() is None:
                for descendant in psutil.Process(child.pid).children(recursive=True):
                    descendant.terminate()
                child.terminate()
            child.wait(timeout=10)
            temporary.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
