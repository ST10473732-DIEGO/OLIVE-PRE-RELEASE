"""Local raster artifacts and opt-in fixed ComfyUI workflows; originals stay intact."""
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import uuid
import re
import shutil
import subprocess
from datetime import datetime
from PIL import Image, ImageOps
from ..storage.json_store import JsonStore
from ..agent.permission_service import PermissionDecision
from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult
from .media_comfy import ComfyImages, endpoint

def probe_video(data):
    """Optional ffprobe facts (size, duration, audio track) for the chat card."""
    executable=shutil.which('ffprobe')
    if not executable:return {}
    try:
        done=subprocess.run([executable,'-v','error','-show_entries','stream=codec_type,width,height,duration','-of','json','-'],
                            input=data,capture_output=True,timeout=10,check=False)
        streams=json.loads(done.stdout or b'{}').get('streams',[])
    except (OSError,subprocess.SubprocessError,ValueError):return {}
    video=next((s for s in streams if s.get('codec_type')=='video'),{})
    result={'has_audio':any(s.get('codec_type')=='audio' for s in streams)}
    if isinstance(video.get('width'),int):result.update(width=video['width'],height=video['height'])
    try:result['duration_seconds']=round(float(video.get('duration')),2)
    except (TypeError,ValueError):pass
    return result

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
        from .media_engines import MediaEngines
        self.s=services;self.root=Path(services.data_dir)/'media';self.store=JsonStore(self.root/'records.json');self.config=JsonStore(self.root/'engine.json')
        # One process manager per runtime: Media tools and Chat share the image engine.
        self.engines=MediaEngines(self.root/'engines');self.runtime=self.engines.image.runtime
        self.engines.image.legacy=lambda:self.config.read({}).get('endpoint')==self.engines.image.endpoint
        self.file_checks={}
        self.jobs={};self.tasks={};self.cancel_events={};self.lock=asyncio.Lock()
        if services.ollama.residency is not None:
            services.ollama.residency.external_guard=self.release_engine_for_chat
        for operation in ('import','render'):services.tool_registry.register(MediaTool(self,operation))
    async def release_engine_for_chat(self):
        # Text inference may load only after every OLIVE media engine is idle and
        # released. A port with no listener holds no engine; a bound but silent
        # port is not proof of free GPU memory. Engines are never started here.
        from .media_errors import MediaError
        config=self.config.read({})
        if config.get('endpoint'):self.guard(config['endpoint'],'network.read')
        try:
            await self.engines.release_others()
            legacy=config.get('endpoint')
            if legacy and legacy not in {e.endpoint for e in self.engines.all()}:
                from .gpu_probe import port_bound
                from urllib.parse import urlsplit
                if port_bound(urlsplit(legacy).port):await ComfyImages(legacy).release_idle()
        except (MediaError,RuntimeError,OSError,ValueError) as error:
            raise RuntimeError('Cannot verify media GPU release. Reconnect the configured engine, or disconnect it in Media tools while it is running and idle, before retrying Chat.') from error
    def records(self):return self.store.read({'version':1,'artifacts':[]})
    def save_record(self,record):
        data=self.records();data['artifacts'].append(record);self.store.write(data);return record
    def guard(self,path,permission):
        if self.s.permissions.evaluate(permission,str(path)).decision==PermissionDecision.DENY:raise PermissionError('Media file access denied')
    def status(self):
        config=self.config.read({})
        video=self.engines.video.status()
        return {'image_editing':'Ready','image_generation':'Configured; check engine' if config.get('endpoint') else 'Needs setup',
                'video_editing':'Needs setup: FFmpeg is not integrated',
                'generative_video':'Chat VIDEO: '+video['state'] if video['ready_workflows'] else 'Needs setup: no validated local video workflow',
                'engine':config,'artifacts':self.records()['artifacts'][-50:],'jobs':list(self.jobs.values())[-20:]}
    async def configure(self,url):
        self.guard(url,'network.read')
        self.guard(self.root,'filesystem.write')
        engine=ComfyImages(endpoint(url))
        await self.runtime.start_for(engine.url)
        info=await engine.inspect()
        self.config.write({'endpoint':engine.url,'version':info['version'],'checkpoints':info['checkpoints']})
        return self.status()
    async def disconnect(self):
        self.guard(self.root,'filesystem.write')
        if any(job['state'] in {'queued','running'} for job in self.jobs.values()):
            raise ValueError('Cancel or finish media jobs before disconnecting the engine')
        async with self.s.ollama.residency.lock:
            await self.release_engine_for_chat()
            self.config.write({})
            await self.runtime.close()
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
                    await self.engines.release_others(keep=self.engines.image)
                    await self.runtime.start_for(engine.url)
                    check()
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
    MIME={'image':('png','image/png'),'audio':('wav','audio/wav'),'video':('mp4','video/mp4')}
    def save_generated(self,kind,data,extension,mime,*,mode,generator,parameters,source_ids=(),extra=None,provenance=None):
        """Verify and persist one generated file; return (record, chat artifact)."""
        from .media_errors import MediaError
        if (kind,(extension,mime))not in {(k,v)for k,v in self.MIME.items()} or not data:raise MediaError('no_artifact',kind)
        info=dict(extra or {})
        try:
            if kind=='image':
                with Image.open(io.BytesIO(data)) as image:
                    info.update(width=image.width,height=image.height);image.verify()
            elif kind=='video' and data[4:8]!=b'ftyp':raise ValueError('not an MP4 container')
            elif kind=='audio' and (data[:4]!=b'RIFF' or data[8:12]!=b'WAVE'):raise ValueError('not a WAV file')
        except Exception as error:raise MediaError('no_artifact',str(error)) from None
        if kind=='video':info.update(probe_video(data))
        self.guard(self.root,'filesystem.write')
        identity=uuid.uuid4().hex;target=self.root/'outputs'/(identity+'.'+extension);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(data)
        created=datetime.now().isoformat(timespec='seconds');digest=hashlib.sha256(data).hexdigest()
        filename=f'olive-{mode}-{created[:10]}-{identity[:6]}.{extension}'
        artifact={'id':identity,'kind':kind,'filename':filename,'mime_type':mime,'created_at':created,'mode':mode,
                  'generator':generator,'parameters':parameters,'source_ids':list(source_ids),'completion_state':'complete',
                  'size_bytes':len(data),'sha256':digest,**info}
        record=self.save_record({'id':identity,'name':filename,'kind':kind,'path':str(target),'sha256':digest,
                                 'source_id':source_ids[0] if source_ids else '','mime_type':mime,'created_at':created,
                                 'mode':mode,'chat_artifact':artifact,'provenance':provenance or {}})
        return record,artifact
    def preserve_bytes(self,name,raw):
        """Keep an attached reference as its own immutable original record."""
        self.guard(self.root,'filesystem.write')
        digest=hashlib.sha256(raw).hexdigest()
        existing=next((r for r in self.records()['artifacts'] if r.get('kind')=='original' and r.get('sha256')==digest and Path(r['path']).is_file()),None)
        if existing:return existing
        identity=uuid.uuid4().hex;target=self.root/'inputs'/(identity+'.original');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        return self.save_record({'id':identity,'name':Path(name).name[:200],'kind':'original','path':str(target),'sha256':digest,
                                 'source_id':'','provenance':{'operation':'preserved chat attachment'}})
    def artifact_file(self,artifact_id):
        """Main-process-only resolution for inline playback; the renderer never sees paths."""
        from .media_errors import MediaError
        if not isinstance(artifact_id,str) or not re.fullmatch(r'[0-9a-f]{32}',artifact_id):raise MediaError('artifact_missing')
        record=next((r for r in self.records()['artifacts'] if r['id']==artifact_id and r.get('kind') in self.MIME),None)
        if not record:raise MediaError('artifact_missing')
        path=Path(record['path']).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():raise MediaError('artifact_missing')
        self.guard(path,'filesystem.read')
        stat=path.stat();key=(artifact_id,stat.st_size,stat.st_mtime_ns)
        if key not in self.file_checks:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise MediaError('artifact_missing')
            self.file_checks[key]=True
        return {'path':str(path),'mime_type':self.MIME[record['kind']][1],'size':stat.st_size,'filename':record['name']}
    def available_ids(self,ids):
        """Artifacts whose file still exists; missing files are reported, never faked."""
        return {r['id'] for r in self.records()['artifacts'] if r['id'] in ids and Path(r['path']).is_file()}
    def reuse(self,chat_id,artifact_id):
        """Attach a generated image to the conversation as the next reference."""
        from .media_errors import MediaError
        record=next((r for r in self.records()['artifacts'] if r['id']==artifact_id and r.get('kind')=='image'),None)
        if not record or chat_id not in self.s.chats:raise MediaError('artifact_missing')
        raw,_=self.source(artifact_id)
        images=self.s.chat.images.setdefault(chat_id,[])
        if len(images)>=4:raise ValueError('Remove an attached image before adding another reference')
        images.append((record['name'],base64.b64encode(raw).decode('ascii')))
        self.s.publish('chat',self.s.chat.get(chat_id))
        return self.s.chat.get(chat_id)
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
        try:
            await asyncio.gather(*self.tasks.values(),return_exceptions=True)
        finally:
            await self.engines.close()
            chat_media = getattr(self.s, 'chat_media', None)
            if chat_media:
                await chat_media.voice.close()  # Only an OLIVE-started VoiceStudio.
