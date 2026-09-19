"""Local raster artifacts and opt-in fixed ComfyUI workflows; originals stay intact."""
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import uuid
from PIL import Image, ImageOps
from ..storage.json_store import JsonStore
from ..agent.permission_service import PermissionDecision
from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult
from .media_comfy import ComfyImages, endpoint

class MediaTool:
    def __init__(self,service,operation):
        self.service,self.operation=service,operation
        self.internal_only=True  # Exact jobs originate in the validated media UI service.
        self.definition=ToolDefinition('media.'+operation,'Import an original image' if operation=='import' else 'Create a new local media artifact',
            'media',{'required':['path'] if operation=='import' else ['job_id','request']},
            required_permissions=('filesystem.read','filesystem.write'),confirmation_required=True,timeout_seconds=700)
    async def execute(self,args,context):
        value=await self.service.import_image(args['path']) if self.operation=='import' else await self.service.render(args['job_id'],args['request'],context)
        return ToolResult(True,'Media artifact saved',value)

class MediaService:
    def __init__(self,services):
        self.s=services;self.root=Path(services.data_dir)/'media';self.store=JsonStore(self.root/'records.json');self.config=JsonStore(self.root/'engine.json')
        self.jobs={};self.tasks={};self.cancel_events={};self.lock=asyncio.Lock()
        if services.ollama.residency is not None:
            services.ollama.residency.external_guard=self.release_engine_for_chat
        for operation in ('import','render'):services.tool_registry.register(MediaTool(self,operation))
    async def release_engine_for_chat(self):
        config=self.config.read({})
        if config.get('endpoint'):
            self.guard(config['endpoint'],'network.read')
            try:await ComfyImages(config['endpoint']).release_idle()
            except Exception as error:
                raise RuntimeError('Cannot verify media GPU release. Reconnect the configured engine, or disconnect it in Media tools while it is running and idle, before retrying Chat.') from error
    def records(self):return self.store.read({'version':1,'artifacts':[]})
    def save_record(self,record):
        data=self.records();data['artifacts'].append(record);self.store.write(data);return record
    def guard(self,path,permission):
        if self.s.permissions.evaluate(permission,str(path)).decision==PermissionDecision.DENY:raise PermissionError('Media file access denied')
    def status(self):
        config=self.config.read({})
        return {'image_editing':'Ready','image_generation':'Configured; check engine' if config.get('endpoint') else 'Needs setup',
                'video_editing':'Needs setup: FFmpeg is not integrated','generative_video':'Unsupported: no configured video model/workflow',
                'engine':config,'artifacts':self.records()['artifacts'][-50:],'jobs':list(self.jobs.values())[-20:]}
    async def configure(self,url):
        self.guard(url,'network.read')
        self.guard(self.root,'filesystem.write')
        engine=ComfyImages(endpoint(url));info=await engine.inspect()
        self.config.write({'endpoint':engine.url,'version':info['version'],'checkpoints':info['checkpoints']})
        return self.status()
    async def disconnect(self):
        self.guard(self.root,'filesystem.write')
        if any(job['state'] in {'queued','running'} for job in self.jobs.values()):
            raise ValueError('Cancel or finish media jobs before disconnecting the engine')
        async with self.s.ollama.residency.lock:
            await self.release_engine_for_chat()
            self.config.write({})
        return self.status()
    async def load(self,path):
        return await self.s.agent.tool('media.import',{'path':path},'Preserve this selected original image for local editing',direct_user_action=True)
    async def import_image(self,path):
        source=Path(path).resolve(strict=True);self.guard(source,'filesystem.read');self.guard(self.root,'filesystem.write')
        if not source.is_file() or source.stat().st_size>64_000_000:raise ValueError('Choose an image smaller than 64 MB')
        raw=await asyncio.to_thread(source.read_bytes)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>24_000_000 or image.format not in {'PNG','JPEG','WEBP','BMP'}:raise ValueError('Use a PNG/JPEG/WebP/BMP image up to 24 megapixels')
            image.verify()
        artifact=uuid.uuid4().hex;target=self.root/'inputs'/(artifact+'.original');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        return self.save_record({'id':artifact,'name':source.name,'kind':'original','path':str(target),'sha256':hashlib.sha256(raw).hexdigest(),'source_id':'','provenance':{'operation':'preserved original'}})
    def source(self,identity):
        record=next((r for r in self.records()['artifacts'] if r['id']==identity),None)
        if not record:raise ValueError('Select an imported image')
        path=Path(record['path']).resolve()
        if not path.is_relative_to(self.root.resolve()):raise PermissionError('Media artifact escaped its storage root')
        self.guard(path,'filesystem.read');raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('The media input changed; import the intended version again')
        return raw,record
    @staticmethod
    def validate(request):
        allowed={'operation','source_id','width','height','left','top','prompt','checkpoint','seed','steps','cfg'}
        if not isinstance(request,dict) or set(request)-allowed:raise ValueError('Unsupported media request')
        value={'source_id':'','width':512,'height':512,'left':0,'top':0,'prompt':'','checkpoint':'','seed':0,'steps':20,'cfg':7.0,**request}
        if value.get('operation') not in {'resize','crop','generate','image-to-image'}:raise ValueError('Unsupported media operation')
        for key,low,high in [('width',16,2048),('height',16,2048),('left',0,20000),('top',0,20000),('seed',0,2**53-1),('steps',1,50)]:
            if type(value[key]) is not int or not low<=value[key]<=high:raise ValueError('Media dimensions/settings exceed supported bounds')
        if type(value['cfg']) not in (int,float) or not 0<=value['cfg']<=20:raise ValueError('Invalid guidance setting')
        for key,limit in [('source_id',64),('prompt',4000),('checkpoint',300)]:
            if not isinstance(value[key],str) or len(value[key])>limit or '\0' in value[key]:raise ValueError('Invalid media text')
        if value['operation']!='generate' and not value['source_id']:raise ValueError('Select an original image')
        if value['operation'] in {'generate','image-to-image'} and (not value['prompt'].strip() or value['width']%8 or value['height']%8):raise ValueError('Generation needs a prompt and dimensions divisible by eight')
        return value
    async def start(self,request):
        request=self.validate(request);job_id=uuid.uuid4().hex;cancel=asyncio.Event();self.cancel_events[job_id]=cancel
        job={'id':job_id,'state':'queued','progress':'Waiting for local media','artifact':None,'error':''};self.jobs[job_id]=job
        async def work():
            try:
                result=await self.s.agent.tool('media.render',{'job_id':job_id,'request':request},'Create a new '+request['operation']+' media artifact',direct_user_action=True)
                job.update(state='completed',artifact=result,progress='Output artifact verified')
            except asyncio.CancelledError:job.update(state='cancelled',progress='Cancelled; original preserved')
            except Exception as error:job.update(state='failed',error=str(error)[:500],progress='Media operation failed; no completion claimed')
            finally:self.s.publish('media.progress',job)
        self.tasks[job_id]=asyncio.create_task(work());return job
    def cancel(self,job_id):
        if job_id not in self.cancel_events:raise ValueError('Unknown media job')
        self.cancel_events[job_id].set();return {'cancel_requested':True}
    async def render(self,job_id,request,context):
        async with self.lock:
            job=self.jobs[job_id];cancel=self.cancel_events[job_id]
            def check():
                if cancel.is_set() or context.cancellation_event and context.cancellation_event.is_set():raise asyncio.CancelledError()
                self.guard(self.root,'filesystem.write')
            def progress(text):job.update(state='running',progress=text);self.s.publish('media.progress',job)
            check();progress('Reading preserved image')
            raw,source=self.source(request['source_id']) if request['source_id'] else (None,None)
            provenance={'engine':'Pillow','operation':request['operation'],'settings':request}
            if request['operation'] in {'resize','crop'}:
                def edit():
                    with Image.open(io.BytesIO(raw)) as original:
                        image=ImageOps.exif_transpose(original).convert('RGBA')
                        if request['operation']=='resize':image=image.resize((request['width'],request['height']),Image.Resampling.LANCZOS)
                        else:
                            x,y,w,h=(request[k] for k in ('left','top','width','height'))
                            if x+w>image.width or y+h>image.height:raise ValueError('Crop rectangle extends beyond the original image')
                            image=image.crop((x,y,x+w,y+h))
                        output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()
                result=await asyncio.to_thread(edit)
            else:
                config=self.config.read({})
                if not config.get('endpoint'):raise ValueError('Needs setup: configure a dedicated local ComfyUI engine and installed checkpoint. No image was generated.')
                engine=ComfyImages(config['endpoint']);residency=self.s.ollama.residency
                self.guard(config['endpoint'],'network.read')
                async with residency.lock:
                    check();progress('Coordinating GPU residency')
                    if residency.current:await self.s.ollama.unload_model(residency.current);residency.current=None
                    loaded=await self.s.ollama.loaded_models()
                    if loaded:raise ValueError('Another Ollama client has resident models. Release them before starting media generation.')
                    if raw:
                        with Image.open(io.BytesIO(raw)) as original:
                            image=ImageOps.exif_transpose(original).convert('RGB').resize((request['width'],request['height']))
                            buffer=io.BytesIO();image.save(buffer,format='PNG');raw=buffer.getvalue()
                    result,provenance=await engine.render(request,raw,job_id,cancel,progress)
            check()
            with Image.open(io.BytesIO(result)) as image:
                image.verify()
            target=self.root/'outputs'/(job_id+'.png');target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(result)
            return self.save_record({'id':job_id,'name':request['operation']+'.png','kind':'image','path':str(target),
                'sha256':hashlib.sha256(result).hexdigest(),'source_id':source['id'] if source else '', 'provenance':provenance})
    def preview(self,artifact_id):
        raw,_=self.source(artifact_id)
        with Image.open(io.BytesIO(raw)) as image:
            image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((640,640));buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=85)
        return {'image':'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode()}
    def export(self,artifact_id,path):
        raw,record=self.source(artifact_id);target=Path(path).resolve();self.guard(target,'filesystem.write')
        with target.open('xb') as stream:stream.write(raw)
        return {'path':str(target),'sha256':record['sha256']}
    async def shutdown(self):
        for event in self.cancel_events.values():event.set()
        await asyncio.gather(*self.tasks.values(),return_exceptions=True)
