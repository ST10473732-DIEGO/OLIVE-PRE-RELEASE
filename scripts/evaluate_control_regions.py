"""Held-out raster controls: raw GUI model versus independent region admission.

Synthetic screens only. No input dispatched. This is not end-to-end acceptance.
The development seed/cases from evaluate_gui_owl are deliberately not reused.
"""
import argparse
import asyncio
import base64
import io
import json
from pathlib import Path
import random
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from olive.desktop.visual_targets import evidence,validate_point
from olive.desktop.target_region import TargetState
from olive.services.gui_model_service import GuiModelService,MODEL
from olive.services.model_residency_service import ModelResidencyService


def cases():
    rng=random.Random(73140851)
    labels=['Save copy','Open folder','Next page','New note','Zoom in','View details','Refresh','Previous','Cancel','Search']
    for i in range(90):
        category='present' if i<50 else 'missing' if i<75 else ['ambiguous','disabled','occluded'][(i-75)//5]
        w,h=rng.choice([(1024,720),(1280,800),(900,960),(1120,700)])
        dark=i%2==0
        image=Image.new('RGB',(w,h),'#242831' if dark else '#f3f5f8')
        draw=ImageDraw.Draw(image);font=ImageFont.truetype('DejaVuSans.ttf',rng.choice([20,22,26]))
        draw.rectangle((0,0,w,48),fill='#404856');draw.text((20,9),'Owned browser' if i%3 else 'Owned native editor',font=font,fill='white')
        draw.text((24,68),'Workspace controls',font=font,fill='white' if dark else '#151d28')
        chosen=rng.sample(labels,6);target_index=rng.randrange(6);target=chosen[target_index]
        if category=='missing':target='Export calendar'
        if category=='ambiguous':chosen[(target_index+1)%6]=target
        expected=None
        for n,label in enumerate(chosen):
            x=28+(n%2)*(w//2)+rng.randrange(0,14);y=140+(n//2)*(h-180)//3+rng.randrange(0,12)
            bw=w//2-rng.randrange(60,100);bh=rng.choice([58,68,76])
            rect=(x,y,x+bw,y+bh)
            color=('#287ca9' if i%4 else '#366cae') if dark else ('#c5deed' if i%4 else '#b9d9e5')
            if n==target_index and category=='disabled':color='#656565' if dark else '#d0d0d0'
            draw.rounded_rectangle(rect,radius=6,fill=color,outline='#7894aa',width=2)
            tw=draw.textlength(label,font=font)
            tx=x+14 if i%3 else x+(bw-tw)/2
            draw.text((tx,y+(bh-28)//2),label,font=font,fill='white' if dark else '#121b25')
            if n==target_index:
                expected=rect if category=='present' else None
                if category=='occluded':
                    draw.rectangle((x+4,y+4,x+bw-4,y+bh-4),fill='#4b505a')
                    draw.text((x+12,y+18),'Overlay panel',font=font,fill='white')
        yield i,category,image,target,expected


async def evaluate(output,without_model=False):
    class NoOtherModels:
        async def unload_model(self,name):raise RuntimeError('Isolated evaluation cannot unload another owner')
    model=GuiModelService(ModelResidencyService(NoOtherModels()))
    rows=[]
    try:
        for i,category,img,target,expected in cases():
            data=io.BytesIO();img.save(data,format='PNG')
            frame={'png':base64.b64encode(data.getvalue()).decode(),'width':img.width,'height':img.height}
            started=time.monotonic();ev=await asyncio.to_thread(evidence,frame,target)
            row={'case':i,'category':category,'verifier_state':ev.state,'verifier_seconds':time.monotonic()-started,
                 'verifier_correct': bool(ev.bounds and expected and expected[0]<=ev.bounds[0]<ev.bounds[2]<=expected[2]+1 and expected[1]<=ev.bounds[1]<ev.bounds[3]<=expected[3]+1) if expected else ev.bounds is None,
                 'actual_actions':0}
            if not without_model:
                try:
                    action=await model.action(frame,'Click '+target+'. If absent, ambiguous, disabled or occluded, use interact.')
                    row['raw_action']=action;row['model_seconds']=model.metrics[-1]['seconds']
                    xy=action.get('coordinate',[-1000,-1000]);x,y=xy[0]*img.width/1000,xy[1]*img.height/1000
                    row['raw_correct']=bool(action['action']=='left_click' and expected[0]<=x<=expected[2] and expected[1]<=y<=expected[3]) if expected else action['action']=='interact' or action=={'action':'terminate','status':'failure'}
                    admitted=False
                    if ev.state==TargetState.FOUND:
                        try:validate_point(action,frame,ev.bounds);admitted=True
                        except ValueError:pass
                    row['combined_admitted']=admitted
                    row['combined_correct']=admitted and row['raw_correct'] if expected else not admitted
                except Exception as error:
                    row.update(error=type(error).__name__,raw_correct=False,combined_admitted=False,combined_correct=not bool(expected))
            rows.append(row);print(json.dumps(row),flush=True)
            summary={'classification':'synthetic raster, zero input','model':None if without_model else MODEL,'seed':73140851,'cases':rows}
            output.write_text(json.dumps(summary,indent=2))
        return summary
    finally:await model.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--without-model',action='store_true');a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    asyncio.run(evaluate(a.output,a.without_model))
