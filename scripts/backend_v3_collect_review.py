"""Collect synthetic compiler/rubric answers for manual review; never execute them.

Raw synthetic answers go only to the explicitly chosen output file. Do not
commit that file; publish content-free reviewed outcomes separately. All models
must already be installed, and any resident runtime work prevents acquisition.
"""
import argparse,asyncio,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from olive.evaluation.backend_benchmark import load_cases
from olive.services.ollama_service import OllamaService
from olive.services.model_residency_service import ModelResidencyService
from olive.services.model_registry import ModelCapabilityRegistry

async def main(models, output):
 service=OllamaService(); registry=ModelCapabilityRegistry(service);await registry.refresh()
 if await service.loaded_models():raise RuntimeError('Resident model is externally owned; stop')
 service.residency=ModelResidencyService(service,lambda:{'keep_alive':60,'contexts':{'general':8192}})
 records=[]
 cases=[c for c in load_cases() if c['kind'] in ('compile_review','human_rubric')]+[c for c in load_cases('held_out') if c['kind']=='human_rubric']
 try:
  for model in models:
   for case in cases:
    options={'num_ctx':8192,'num_predict':1024,'temperature':0,'seed':42}
    if model=='qwen3.8:27b':options['num_gpu']=40
    think='low' if model.startswith('gpt-oss') else True if model.startswith('qwen3.8') else False
    record={'model':model,'digest':registry.get(model).digest,'case':case['id'],'options':options,'think':think}
    start=time.perf_counter()
    try:
     async with asyncio.timeout(120):answer=await service.chat_measured(model,[{'role':'user','content':case['prompt']}],options=options,think=think,stream=True)
     record.update(content=answer['content'],first_visible_ms=answer['first_token_ms'],output_tokens=answer['eval_count'])
    except Exception as error:record['error']=type(error).__name__
    record['completion_ms']=(time.perf_counter()-start)*1000;records.append(record)
    output.write_text(json.dumps(records,indent=2)+'\n')
    print(model,case['id'],record.get('error','collected'),flush=True)
 finally:
  if service.residency.current:await service.unload_model(service.residency.current)
  await service.client._client.aclose()
if __name__ == '__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--models',nargs='+',required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 if args.output.exists():raise SystemExit('Output already exists; preserved')
 asyncio.run(main(args.models,args.output))
