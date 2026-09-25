"""Typed user-session OS controls: audio, Bluetooth, display brightness, radio status.

Each operation is a fixed argv call to a structured user-level API (PipeWire's
wpctl, BlueZ and KDE PowerDevil over D-Bus via busctl, NetworkManager's nmcli)
with validated scalar arguments. No shell, no model-supplied strings, no root,
sudo or Polkit bypass. If the OS requires authentication the call fails with
OS_AUTH_REQUIRED instead of being retried. Every change is read back.
"""
import asyncio
import re
import shutil
import subprocess
import sys

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition

SINK = '@DEFAULT_AUDIO_SINK@'
BLUEZ = ('org.bluez', '/org/bluez/hci0', 'org.bluez.Adapter1')
BRIGHTNESS = ('org.kde.Solid.PowerManagement', '/org/kde/Solid/PowerManagement/Actions/BrightnessControl',
              'org.kde.Solid.PowerManagement.Actions.BrightnessControl')


class OSControlError(RuntimeError):
    pass


def run(argv, timeout=8):
    if sys.platform != 'linux' or not shutil.which(argv[0]):
        raise OSControlError('PLATFORM_LIMITED: this control needs ' + argv[0] + ' on Linux')
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[:300]
        if re.search(r'not authorized|access denied|interactive authentication|polkit', detail, re.I):
            raise OSControlError('OS_AUTH_REQUIRED: the operating system requires authentication for this change')
        raise OSControlError(argv[0] + ' failed: ' + detail)
    return completed.stdout


def audio_status():
    raw = run(['wpctl', 'get-volume', SINK])
    match = re.search(r'Volume:\s*([0-9.]+)', raw)
    if not match:
        raise OSControlError('Unexpected PipeWire volume output')
    description = re.search(r'node\.description = "([^"]{0,200})"', run(['wpctl', 'inspect', SINK]))
    return {'volume_percent': round(float(match.group(1)) * 100), 'muted': '[MUTED]' in raw,
            'device': description.group(1) if description else ''}


def bluez_property(name):
    raw = run(['busctl', '--system', 'get-property', *BLUEZ, name])
    return raw.strip().endswith('true')


def bluetooth_status():
    devices = [line.strip() for line in run(['busctl', '--system', 'tree', 'org.bluez', '--list']).splitlines()
               if re.fullmatch(r'/org/bluez/hci0/dev_[0-9A-F_]{17}', line.strip())]
    connected = 0
    for path in devices[:64]:
        raw = run(['busctl', '--system', 'get-property', 'org.bluez', path, 'org.bluez.Device1', 'Connected'])
        connected += raw.strip().endswith('true')
    return {'adapter': 'hci0', 'powered': bluez_property('Powered'), 'discoverable': bluez_property('Discoverable'),
            'paired_devices': len(devices), 'connected_devices': connected}


def brightness_status():
    value = int(run(['busctl', '--user', 'call', *BRIGHTNESS, 'brightness']).split()[-1])
    maximum = int(run(['busctl', '--user', 'call', *BRIGHTNESS, 'brightnessMax']).split()[-1])
    return {'brightness_percent': round(value * 100 / maximum) if maximum else 0, 'raw': value, 'max': maximum}


def network_status():
    radios = run(['nmcli', '-t', '-f', 'WIFI-HW,WIFI', 'radio']).strip().split(':')
    state = run(['nmcli', '-t', '-f', 'STATE,CONNECTIVITY', 'general']).strip().split(':')
    return {'wifi_hardware': radios[0] if radios else '', 'wifi': radios[1] if len(radios) > 1 else '',
            'state': state[0] if state else '', 'connectivity': state[1] if len(state) > 1 else ''}


class OSControlTool:
    SPECS = {
        'system.audio_status': ({}, ()), 'system.bluetooth_status': ({}, ()),
        'system.display_status': ({}, ()), 'system.network_status': ({}, ()),
        'system.audio_set_volume': ({'percent': int}, ('system.settings',)),
        'system.audio_set_mute': ({'muted': bool}, ('system.settings',)),
        'system.bluetooth_set_power': ({'powered': bool}, ('system.settings',)),
        'system.bluetooth_set_discoverable': ({'discoverable': bool}, ('system.settings',)),
        'system.display_set_brightness': ({'percent': int}, ('system.settings',)),
    }

    def __init__(self, name):
        fields, permissions = self.SPECS[name]
        self.name, self.fields = name, fields
        self.definition = ToolDefinition(name, name.split('.', 1)[1].replace('_', ' ').capitalize(), 'system',
            {'type': 'object', 'required': list(fields)}, risk_level='medium' if permissions else 'low',
            required_permissions=permissions, confirmation_required=bool(permissions), timeout_seconds=20)

    async def execute(self, arguments, context):
        if set(arguments) != set(self.fields) or any(type(arguments[k]) is not t for k, t in self.fields.items()):
            return ToolResult.failure('Invalid system control arguments', 'InvalidArguments')
        try:
            return ToolResult(True, 'System control completed', await asyncio.to_thread(self._execute, arguments))
        except (OSControlError, subprocess.TimeoutExpired, ValueError) as error:
            text = str(error)
            return ToolResult.failure(text, 'OSAuthRequired' if text.startswith('OS_AUTH_REQUIRED') else
                                      'PlatformLimited' if text.startswith('PLATFORM_LIMITED') else 'SystemControlFailed')

    def _execute(self, a):
        name = self.name
        if name == 'system.audio_status':
            return audio_status()
        if name == 'system.bluetooth_status':
            return bluetooth_status()
        if name == 'system.display_status':
            return brightness_status()
        if name == 'system.network_status':
            return network_status()
        if name == 'system.audio_set_volume':
            if not 0 <= a['percent'] <= 100:
                raise ValueError('Volume must be 0-100%')
            run(['wpctl', 'set-volume', SINK, f"{a['percent'] / 100:.2f}"])
            after = audio_status()
            if abs(after['volume_percent'] - a['percent']) > 1:
                raise OSControlError('Volume change was not verified')
            return after
        if name == 'system.audio_set_mute':
            run(['wpctl', 'set-mute', SINK, '1' if a['muted'] else '0'])
            after = audio_status()
            if after['muted'] != a['muted']:
                raise OSControlError('Mute change was not verified')
            return after
        if name in {'system.bluetooth_set_power', 'system.bluetooth_set_discoverable'}:
            prop, value = ('Powered', a['powered']) if name.endswith('power') else ('Discoverable', a['discoverable'])
            run(['busctl', '--system', 'set-property', *BLUEZ, prop, 'b', 'true' if value else 'false'])
            for _ in range(20):
                if bluez_property(prop) == value:
                    return bluetooth_status()
                import time
                time.sleep(.1)
            raise OSControlError('Bluetooth change was not verified')
        if name == 'system.display_set_brightness':
            if not 1 <= a['percent'] <= 100:
                raise ValueError('Brightness must be 1-100%')
            maximum = brightness_status()['max']
            run(['busctl', '--user', 'call', *BRIGHTNESS, 'setBrightnessSilent', 'i', str(round(maximum * a['percent'] / 100))])
            after = brightness_status()
            if abs(after['brightness_percent'] - a['percent']) > 2:
                raise OSControlError('Brightness change was not verified')
            return after
        raise ValueError(name)


def os_control_tools():
    return [OSControlTool(name) for name in OSControlTool.SPECS]
