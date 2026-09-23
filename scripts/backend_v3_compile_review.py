"""Linux-only compiler smoke harness for exactly reviewed arithmetic definitions.

Inspect collected synthetic answers and supply a JSON map of model/case to
SHA-256 under --reviewed-hashes. This also independently requires each source
to match a fixed addition-only definition. No arbitrary generated code is run.
Use repository-local SDK/JDK/Node installations; package sources are cleared.
"""
import argparse,hashlib,json,os,platform,subprocess,tempfile
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--answers',type=Path,required=True)
parser.add_argument('--reviewed-hashes',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if platform.system()!='Linux':raise SystemExit('This local compiler harness is Linux-only; no cross-platform acceptance is implied.')
if args.output.exists():raise SystemExit('Output exists; preserved')
root=Path(__file__).resolve().parents[1]
records=json.loads(args.answers.read_text());approvals=json.loads(args.reviewed_hashes.read_text())
expected={'compile_python':'defadd(a,b):returna+b','compile_csharp':'publicstaticintAdd(inta,intb){returna+b;}','compile_java':'publicstaticintadd(inta,intb){returna+b;}','compile_typescript':'functionadd(a:number,b:number):number{returna+b;}'}
results=[]
for r in records:
 if not r['case'].startswith('compile_'):continue
 source=r.get('content','');key=r['model']+'/'+r['case']
 if hashlib.sha256(source.encode()).hexdigest()!=approvals[key]:raise ValueError('Source differs from reviewed hash')
 normalized=False
 if r['model']=='qwen3-coder:30b' and r['case'] in ('compile_java','compile_csharp'):
  lines=source.splitlines()
  if lines[0] not in ('```java','```csharp') or lines[-1]!='```':raise ValueError('Unexpected fenced source')
  source='\n'.join(lines[1:-1]);normalized=True
 wanted=expected[r['case']]
 if r['model']=='gpt-oss:20b' and r['case']=='compile_java':wanted='publicclassMathUtils{'+wanted+'}'
 if ''.join(source.split())!=wanted:raise ValueError('Only the fixed arithmetic definition is permitted')
 with tempfile.TemporaryDirectory(prefix='olive-compiler-') as d:
  p=Path(d);env=dict(os.environ,DOTNET_ROOT=str(root/'.toolchains/dotnet'),DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_HOME=d);commands=[]
  if r['case']=='compile_python':
   (p/'main.py').write_text(source+'\nassert add(2,3)==5\nassert add(-2,2)==0\nassert add(0,0)==0\n')
   commands=[[str(root/'.venv/bin/python'),'-m','py_compile','main.py'],[str(root/'.venv/bin/python'),'main.py']]
  elif r['case']=='compile_csharp':
   (p/'Fixture.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType></PropertyGroup></Project>')
   (p/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
   (p/'Program.cs').write_text('public class Program {\n'+source+'\npublic static void Main() { if(Add(2,3)!=5 || Add(-2,2)!=0 || Add(0,0)!=0) throw new System.Exception("wrong"); } }')
   commands=[[str(root/'.toolchains/dotnet/dotnet'),'build','--nologo','-v','quiet'],[str(root/'.toolchains/dotnet/dotnet'),'bin/Debug/net10.0/Fixture.dll']]
  elif r['case']=='compile_java':
   call='add'
   if r['model']=='gpt-oss:20b':(p/'MathUtils.java').write_text(source);source='';call='MathUtils.add'
   (p/'Main.java').write_text('public class Main {\n'+source+'\npublic static void main(String[] args) { if('+call+'(2,3)!=5 || '+call+'(-2,2)!=0 || '+call+'(0,0)!=0) throw new AssertionError("wrong"); } }')
   commands=[[str(root/'.toolchains/jdk/bin/javac'),*(['MathUtils.java'] if call!='add' else []),'Main.java'],[str(root/'.toolchains/jdk/bin/java'),'-cp',d,'Main']]
  else:
   (p/'main.ts').write_text(source+'\nif(add(2,3)!==5 || add(-2,2)!==0 || add(0,0)!==0) throw new Error("wrong");\n')
   commands=[[str(root/'.toolchains/node/bin/node'),str(root/'desktop/node_modules/typescript/bin/tsc'),'main.ts','--target','ES2022','--skipLibCheck'],[str(root/'.toolchains/node/bin/node'),'main.js']]
  codes=[]
  for command in commands:
   run=subprocess.run(command,cwd=p,env=env,capture_output=True,text=True,timeout=60);codes.append(run.returncode)
   if run.returncode:print(key,run.stdout,run.stderr);break
  results.append({'model':r['model'],'case':r['case'],'n':1,'source_sha256':approvals[key],'compiler_exit':codes[0],'run_exit':codes[1] if len(codes)>1 else None,'assertions':3,'markdown_removed_after_review':normalized,'raw_format_compliant':not normalized,'passed':codes==[0,0]})
  print(key,codes,flush=True)
args.output.write_text(json.dumps(results,indent=2)+'\n')
