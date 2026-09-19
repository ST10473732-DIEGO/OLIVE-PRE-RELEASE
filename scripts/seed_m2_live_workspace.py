"""Empty isolated acceptance profile, real test files; no injected task results."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('profile')
    profile = Path(parser.parse_args().profile).resolve()
    if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()) or any(profile.iterdir()):
        raise ValueError('Use an empty temporary acceptance profile')
    os.environ['OLIVE_DATA_DIR'] = str(profile)
    from olive.application.service_container import ServiceContainer
    services = ServiceContainer(lambda *args: None, None, data_dir=profile, migrate=False)
    folder = profile / 'local-acceptance'
    folder.mkdir()
    (folder / 'tests').mkdir()
    (folder / 'main.py').write_text('def add(a, b):\n    return a + b\n', encoding='utf-8')
    (folder / 'tests/test_main.py').write_text('import unittest\nfrom main import add\n\nclass LocalAcceptance(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n', encoding='utf-8')
    services.data.create_workspace('Isolated live acceptance', str(folder))
    services.settings['research'] = {'max_pages': 1, 'max_searches': 1, 'max_link_depth': 0,
        'depth': 'Quick', 'timeout': 180, 'browser_provider': 'http'}
    services.settings_repo.save(services.settings)
