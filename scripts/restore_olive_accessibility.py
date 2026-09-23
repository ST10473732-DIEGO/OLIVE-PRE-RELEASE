"""Restore only the accessibility flags changed by the owner's recorded setup."""
import argparse
import json
from pathlib import Path
import subprocess


def restore(receipt):
    saved = json.loads(receipt.read_text())
    for name in ('IsEnabled', 'ScreenReaderEnabled'):
        if name not in saved.get('changed', []):
            continue
        current = subprocess.check_output(['busctl','--user','get-property','org.a11y.Bus',
            '/org/a11y/bus','org.a11y.Status',name], text=True).strip()
        if current != 'b true':
            raise ValueError('Accessibility state changed since setup; refusing replacement')
    for name in ('IsEnabled', 'ScreenReaderEnabled'):
        if name in saved.get('changed', []):
            previous = saved[name]
            subprocess.run(['busctl','--user','set-property','org.a11y.Bus','/org/a11y/bus',
                'org.a11y.Status',name,'b',str(previous).lower()], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    restore(parser.parse_args().receipt)
