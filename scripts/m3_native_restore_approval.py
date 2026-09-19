"""Activate one real OLIVE restore confirmation under delegated M3 fixture consent.

This is test-app UI automation, not a production permission provider. It never
reads other applications or changes permission state. Only a verified isolated
Electron process and its owned native dialog are inspected.
"""
import argparse,json,os,sys,time
from pathlib import Path
sys.coinit_flags=0
import psutil
import win32gui,win32process,win32con
from pywinauto import Desktop

parser=argparse.ArgumentParser()
parser.add_argument('--pid',type=int,required=True)
parser.add_argument('--window',type=int,required=True)
parser.add_argument('--profile',type=Path,required=True)
parser.add_argument('--archive',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
expected=(root/'desktop/node_modules/electron/dist/electron.exe').resolve()
process=psutil.Process(args.pid);created=process.create_time()
assert Path(process.exe()).resolve()==expected,'Unexpected executable'
assert Path(process.environ()['OLIVE_DATA_DIR']).resolve()==args.profile.resolve(),'Not the isolated profile'
assert args.profile.name.startswith('olive-m3-'),'Not an M3 fixture profile'
assert args.archive.resolve().parent==args.profile.resolve(),'Archive outside fixture directory'
assert args.archive.is_file(),'Missing fixture archive'
assert win32process.GetWindowThreadProcessId(args.window)[1]==args.pid,'Main window ownership changed'
deadline=time.monotonic()+15
while time.monotonic()<deadline:
 assert process.is_running() and process.create_time()==created,'Owned process exited or changed'
 candidates=[]
 def candidate(handle,unused):
  # PID and ownership precede any title/text/accessibility access.
  if win32process.GetWindowThreadProcessId(handle)[1]!=args.pid:return True
  if not win32gui.IsWindowVisible(handle) or win32gui.GetWindow(handle,win32con.GW_OWNER)!=args.window:return True
  candidates.append(handle);return True
 win32gui.EnumWindows(candidate,None)
 if len(candidates)>1:raise RuntimeError('Multiple owned modal windows; no approval exercised')
 if not candidates:
  time.sleep(.05);continue
 handle=candidates[0]
 if win32gui.GetForegroundWindow()!=handle:
  print(json.dumps({'stage':'modal_focus_preflight','foreground_is_owned_main':win32gui.GetForegroundWindow()==args.window,'candidate_count':len(candidates),'approval_exercised':False}),flush=True)
  raise RuntimeError('Restore dialog lost focus; no approval exercised')
 dialog=Desktop(backend='uia').window(handle=handle).wrapper_object()
 controls=dialog.descendants()
 if len(controls)>100:raise RuntimeError('Unexpected dialog structure')
 names=[control.element_info.name for control in controls]
 text='\n'.join(names)
 assert 'Restore this OLIVE backup?' in text and str(args.archive) in text,'Unexpected confirmation scope'
 buttons=[control for control in controls if control.element_info.control_type=='Button' and control.element_info.name=='Restore']
 assert len(buttons)==1 and buttons[0].is_enabled(),'Restore button is unresolved'
 assert win32gui.GetForegroundWindow()==handle,'Focus changed before approval'
 assert process.create_time()==created,'Process identity changed'
 buttons[0].iface_invoke.Invoke()
 print(json.dumps({'decision':'Restore once under explicit M3 delegated synthetic-operation consent','pid':args.pid,'window':handle,'archive':str(args.archive),'observed_controls':names,'invoked':'Restore'}))
 break
else:raise TimeoutError('No owned restore confirmation appeared; no approval exercised')
