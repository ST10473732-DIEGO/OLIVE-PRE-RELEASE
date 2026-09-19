"""Explicit desktop presentation operations; controller/gateway retain authority."""
import asyncio
import base64
import io
from pathlib import Path

from ..desktop.action_preview import REQUIRED_FIELDS


def status(s):
    d = s.desktop
    value = d.status()
    controllable = bool(d.universal.owner or (d.operation and d.workflow))
    paused = bool(d.universal.paused if d.universal.owner else d.record and d.record.status == 'paused')
    return {**value, 'can_pause': controllable and not paused, 'can_resume': controllable and paused}


def capture_preview(s, capture_id):
    record = s.desktop.screenshots.records.get(capture_id)
    if record is None:
        raise ValueError('Capture is no longer available; request a new authorised capture')
    path = Path(record['path'])
    root = s.desktop.screenshots.root.resolve()
    if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Capture path is outside the owned store')
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Capture exceeds its size limit')
    from PIL import Image
    with Image.open(path) as picture:
        picture.thumbnail((1200, 900))
        output = io.BytesIO()
        picture.convert('RGB').save(output, format='JPEG', quality=75)
        if output.tell() > 600000:
            raise ValueError('Capture preview exceeds the transport limit')
        return {'id': capture_id, 'width': picture.width, 'height': picture.height,
                'original_width': record['width'], 'original_height': record['height'],
                'image': 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')}


def routes(s):
    d = s.desktop
    return {
        'desktop.list_windows': d.list_windows,
        'desktop.inspect': d.inspect,
        'desktop.launch_local': d.launch_local,
        'desktop.attach_launch': d.attach_launch,
        'desktop.launches': d.launch_targets.snapshot,
        'desktop.pause': d.pause,
        'desktop.resume': d.resume,
        'desktop.reset': d.reset,
        'desktop.plan': d.plan,
        'desktop.execute_plan': d.execute_plan,
        'desktop.perform': d.perform,
        'desktop.discover_applications': d.discover_applications,
        'desktop.application_alias': d.application_alias,
        'desktop.open_application': d.open_application,
        'desktop.media_sessions': d.media_sessions,
        'desktop.media_action': d.media_action,
        'desktop.clipboard_action': d.clipboard_action,
        'desktop.consequence': d.consequence,
        'desktop.consequence_fields': lambda: REQUIRED_FIELDS,
        'desktop.screenshot': d.screenshot,
        'desktop.capture_preview': lambda capture_id: asyncio.to_thread(capture_preview, s, capture_id),
        'desktop.vision_observe': d.vision_observe,
        'desktop.vision_verify_label': d.vision_verify_label,
        'desktop.visual_click': d.visual_click,
        'desktop.browser_launch': d.browser_launch,
        'desktop.browser_navigate': d.browser_navigate,
        'desktop.browser_observe': d.browser_observe,
        'desktop.browser_action': d.browser_action,
        'desktop.browser_tab': d.browser_tab,
        'desktop.browser_dialog': d.browser_dialog,
        'desktop.browser_send': d.browser_send,
        'desktop.browser_upload': d.browser_upload,
        'desktop.browser_download': d.browser_download,
        'desktop.save_download': d.save_download,
    }
