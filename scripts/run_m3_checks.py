"""Run selected M3 checks with project tools and retained, distinct local logs."""
import argparse,ctypes,json,os,subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('checks',nargs='+',choices=['forms','workflows','backup','language','python','frontend','electron','compile','harness']);parser.add_argument('--label',required=True)
args=parser.parse_args()
if os.name=='nt' and ctypes.windll.shell32.IsUserAnAdmin():raise SystemExit('Run checks as the normal Windows user, not administrator')
if not args.label.replace('-','').replace('_','').isalnum():raise SystemExit('Use a simple evidence label')
out=root/'artifacts/ui-review/M3'/args.label;out.mkdir(parents=True,exist_ok=False)
node=root/'.toolchains/node-v24.21.0-win-x64/node.exe';python=root/'.venv/Scripts/python.exe'
env=dict(os.environ,PATH=str(node.parent)+os.pathsep+os.environ['PATH'])
env['OLIVE_M3_EVIDENCE']=str(out/'screens')
if 'language' in args.checks:env['OLIVE_M3_LIVE_LANGUAGE']='1'
commands={
 'backup':([str(node),'node_modules/@playwright/test/cli.js','test','m3-backup.spec.ts'],root/'desktop'),
 'workflows':([str(node),'node_modules/@playwright/test/cli.js','test','m3-workflows.spec.ts'],root/'desktop'),
 'language':([str(node),'node_modules/@playwright/test/cli.js','test','m3-language-live.spec.ts'],root/'desktop'),
 'forms':([str(node),'node_modules/@playwright/test/cli.js','test','m3-personal.spec.ts'],root/'desktop'),
 'electron':([str(node),'node_modules/@playwright/test/cli.js','test'],root/'desktop'),
 'python':([str(python),'-m','unittest','discover','-s','tests','-v'],root),
 'frontend':([str(python),'scripts/check_frontend.py','--output',str(out/'frontend')],root),
 'compile':([str(python),'-m','compileall','-q','.'],root),
 'harness':([str(node),'--test','scripts/m2_input_approval.test.cjs','scripts/desktop_attach_outcome.test.cjs'],root)}
results={}
for name in args.checks:
 command,cwd=commands[name]
 with (out/(name+'.log')).open('wb') as log:result=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
 results[name]=result.returncode;print(name,result.returncode,flush=True)
 (out/'results.json').write_text(json.dumps(results,indent=2))
raise SystemExit(any(results.values()))
