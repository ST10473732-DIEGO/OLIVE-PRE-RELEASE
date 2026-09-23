"""Dependency-only inspection for distribution Python; no portal session or UI."""
import ctypes
import json


def inspect():
    result = {}
    try:
        import gi
        result['pygobject'] = {'available': True, 'version': gi.__version__}
        for namespace, version in (('Gio', '2.0'), ('Atspi', '2.0'), ('Gst', '1.0'), ('GstApp', '1.0'), ('GstVideo', '1.0')):
            try:
                gi.require_version(namespace, version)
                module = __import__('gi.repository', fromlist=[namespace])
                getattr(module, namespace)
                result[namespace] = {'available': True, 'api': version}
            except (ImportError, ValueError):
                result[namespace] = {'available': False}
        if result.get('Gst', {}).get('available'):
            from gi.repository import Gst
            Gst.init(None)
            result['gstreamer'] = {'available': True, 'version': Gst.version_string()}
            for factory in ('pipewiresrc', 'videorate', 'videoconvert', 'videoscale', 'appsink'):
                result[factory] = {'available': Gst.ElementFactory.find(factory) is not None}
    except ImportError:
        result['pygobject'] = {'available': False}
    try:
        import PIL
        from PIL import Image
        Image.init()
        result['pillow_png'] = {'available': 'PNG' in Image.SAVE, 'version': PIL.__version__}
    except ImportError:
        result['pillow_png'] = {'available': False}
    try:
        library = ctypes.CDLL('libei.so.1')
        # Required region identity is an actual symbol check, not package presence.
        for symbol in ('ei_new_sender', 'ei_setup_backend_fd', 'ei_region_get_mapping_id'):
            getattr(library, symbol)
        result['libei'] = {'available': True, 'abi': 'libei.so.1'}
    except (OSError, AttributeError):
        result['libei'] = {'available': False}
    return result


if __name__ == '__main__':
    print(json.dumps(inspect(), sort_keys=True))
