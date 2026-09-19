"""Capture only the supplied OLIVE Electron fixture process window."""
import argparse
from pathlib import Path
import psutil
from pywinauto import Application

parser=argparse.ArgumentParser();parser.add_argument('--pid',type=int,required=True);parser.add_argument('--output',required=True)
args=parser.parse_args();repo=Path(__file__).resolve().parents[1];output=Path(args.output).resolve()
if not output.is_relative_to(repo/'artifacts/core/functionality/browser'):raise ValueError('Only Browser fixture evidence output is allowed')
process=psutil.Process(args.pid)
if Path(process.exe()).resolve()!=(repo/'desktop/node_modules/electron/dist/electron.exe').resolve():raise ValueError('Unexpected fixture executable')
if not any(Path(arg).resolve()==repo/'desktop' for arg in process.cmdline()[1:] if not arg.startswith('-')):raise ValueError('Expected OLIVE desktop fixture command')
window=Application(backend='uia').connect(process=args.pid).window(title='OLIVE')
window.wait('visible',timeout=10)
if window.process_id()!=args.pid:raise ValueError('Unexpected window owner')
window.capture_as_image().save(output)
