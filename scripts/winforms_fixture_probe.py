"""Interact only with the exact native App.exe from an isolated designer fixture.

The caller supplies the actual Studio RunSession process identity. The probe
verifies process ancestry and executable path before touching UI controls.
"""
import argparse
import json
from pathlib import Path
import tempfile
import time
import psutil
from pywinauto import Application


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True);parser.add_argument('--pid',required=True,type=int);parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.workspace).resolve();output=Path(args.output).resolve()
    if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not any(p.startswith('olive-designer-') for p in root.parts):
        raise ValueError('Only an isolated olive-designer-* workspace is authorized')
    repo=Path(__file__).resolve().parents[1]
    if not output.is_relative_to(repo/'artifacts/core/functionality/designer'):raise ValueError('Output must stay in the designer evidence directory')
    expected=(root/'bin/Debug/net10.0-windows/App.exe').resolve()
    process=psutil.Process(args.pid);target=None;deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        candidates=[process,*process.children(recursive=True)]
        for candidate in candidates:
            try:
                if Path(candidate.exe()).resolve()==expected:target=candidate;break
            except (psutil.NoSuchProcess,psutil.AccessDenied):continue
        if target:break
        time.sleep(.1)
    if not target:raise RuntimeError('The approved Studio run did not launch the expected native executable')
    application=Application(backend='uia').connect(process=target.pid,timeout=15)
    window=application.window(title='OLIVE Designer Calculator Fixture')
    window.wait('visible',timeout=20)
    if window.process_id()!=target.pid:raise RuntimeError('Unexpected application window owner')
    left=window.child_window(auto_id='leftInput',control_type='Edit')
    right=window.child_window(auto_id='rightInput',control_type='Edit')
    operation=window.child_window(auto_id='operationBox',control_type='ComboBox')
    calculate=window.child_window(auto_id='calculateButton',control_type='Button')
    result=window.child_window(auto_id='resultLabel',control_type='Text')
    observations=[]
    for a,b,op,expected_text in [('2','3','+','5'),('8','2','/','4'),('9','0','/','Cannot divide by zero'),('2','3','*','6')]:
        left.set_edit_text(a);right.set_edit_text(b);operation.select(op);calculate.invoke()
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and result.window_text()!=expected_text:time.sleep(.05)
        actual=result.window_text()
        if actual!=expected_text:raise AssertionError(f'Expected {expected_text}, got {actual}')
        observations.append({'left':a,'right':b,'operation':op,'actual_result':actual})
    output.parent.mkdir(parents=True,exist_ok=True)
    window.capture_as_image().save(output.with_suffix('.png'))
    output.write_text(json.dumps({'classification':'actual native Windows Forms UI; exact approved run process ancestry and executable verified','process_id':target.pid,'results':observations},indent=2),encoding='utf-8')
    window.close()
    print(json.dumps({'verified':True,'results':observations}))


if __name__=='__main__':main()
