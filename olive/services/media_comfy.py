"""Fixed built-in ComfyUI image workflows. No arbitrary nodes or workflow upload."""
import asyncio
import json
import re
import time
from urllib.parse import urlsplit
import httpx

NODES={'CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','SaveImage','LoadImage','VAEEncode'}

def endpoint(value):
    url=urlsplit(value)
    if url.scheme!='http' or url.hostname not in {'127.0.0.1','::1'} or not url.port or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:
        raise ValueError('Use a loopback-only ComfyUI address such as http://127.0.0.1:8188')
    return value.rstrip('/')

class ComfyImages:
    def __init__(self,url):self.url=endpoint(url)
    async def request(self,method,path,**kwargs):
        async with httpx.AsyncClient(base_url=self.url,timeout=30,follow_redirects=False,trust_env=False) as client:
            async with client.stream(method,path,**kwargs) as response:
                response.raise_for_status();data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>64_000_000:raise ValueError('Media response exceeded its bound')
                if path.startswith('/view?'):return bytes(data)
                # ComfyUI acknowledges these commands with an empty HTTP 200.
                if not data and method=='POST' and path in {'/free','/interrupt','/queue'}:return {}
                return json.loads(data)
    async def inspect(self):
        stats=await self.request('GET','/system_stats');nodes=await self.request('GET','/object_info')
        if not stats.get('system',{}).get('comfyui_version'):raise ValueError('The endpoint is not an identifiable ComfyUI runtime')
        version=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)',stats['system']['comfyui_version'])
        if not version or tuple(map(int,version.groups()))<(0,35,0):
            raise ValueError('ComfyUI 0.35.0 or newer is required for identity-bound cancellation')
        if any('cudaMallocAsync' in d.get('name','') for d in stats.get('devices',[])):
            raise ValueError('Start ComfyUI with --disable-cuda-malloc so GPU release can be measured')
        if '--disable-dynamic-vram' not in stats['system'].get('argv',[]):
            raise ValueError('Start ComfyUI with --disable-dynamic-vram so all model VRAM uses the measured allocator')
        for name in NODES:
            if nodes.get(name,{}).get('python_module')!='nodes':raise ValueError('The configured engine does not expose the required trusted built-in node set')
        models=nodes['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]
        return {'version':stats['system']['comfyui_version'],'checkpoints':models[:100],'devices':stats.get('devices',[])[:4]}
    async def release_idle(self):
        queue=await self.request('GET','/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise RuntimeError('The configured media engine is still busy; local chat must wait for GPU release')
        await self.request('POST','/free',json={'unload_models':True,'free_memory':True})
        # /free only sets worker flags. Wait for actual CUDA allocator release,
        # not just an empty queue or the HTTP acknowledgement.
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            queue=await self.request('GET','/queue')
            if queue.get('queue_running') or queue.get('queue_pending'):
                raise RuntimeError('The media engine became busy during GPU release')
            stats=await self.request('GET','/system_stats')
            devices=stats.get('devices',[])
            if '--disable-dynamic-vram' not in stats.get('system',{}).get('argv',[]):
                raise RuntimeError('Media GPU release requires --disable-dynamic-vram')
            if devices and all(d.get('type')=='cpu' or
                d.get('type')=='cuda' and 'cudaMallocAsync' not in d.get('name','') and isinstance(d.get('torch_vram_total'),int) and
                0<=d['torch_vram_total']<=256*1024*1024 for d in devices):return
            await asyncio.sleep(.25)
        raise RuntimeError('The media engine did not confirm GPU memory release within 30 seconds')
    async def render(self,request,source,job_id,cancel,publish):
        metadata=await self.inspect();checkpoint=request['checkpoint']
        if checkpoint not in metadata['checkpoints']:raise ValueError('Select an installed checkpoint from this engine')
        queue=await self.request('GET','/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('ComfyUI is busy with another job; wait before starting OLIVE media')
        workflow={
          '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':checkpoint}},
          '2':{'class_type':'CLIPTextEncode','inputs':{'text':request['prompt'],'clip':['1',1]}},
          '3':{'class_type':'CLIPTextEncode','inputs':{'text':'','clip':['1',1]}},
          '4':{'class_type':'EmptyLatentImage','inputs':{'width':request['width'],'height':request['height'],'batch_size':1}},
          '5':{'class_type':'KSampler','inputs':{'seed':request['seed'],'steps':request['steps'],'cfg':request['cfg'],'sampler_name':'euler','scheduler':'normal','denoise':1.0,'model':['1',0],'positive':['2',0],'negative':['3',0],'latent_image':['4',0]}},
          '6':{'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
          '7':{'class_type':'SaveImage','inputs':{'images':['6',0],'filename_prefix':'OLIVE/'+job_id}},
        }
        if source:
            uploaded=await self.request('POST','/upload/image',files={'image':(job_id+'.png',source,'image/png')},data={'overwrite':'false','type':'input'})
            name=uploaded.get('name','')
            if name!=job_id+'.png':raise ValueError('Unexpected imported-image identity')
            workflow['4']={'class_type':'LoadImage','inputs':{'image':name}}
            workflow['8']={'class_type':'VAEEncode','inputs':{'pixels':['4',0],'vae':['1',2]}}
            workflow['5']['inputs'].update(latent_image=['8',0],denoise=.65)
        if cancel.is_set():raise asyncio.CancelledError()
        queued=await self.request('POST','/prompt',json={'prompt':workflow,'client_id':job_id})
        prompt_id=queued.get('prompt_id')
        if not isinstance(prompt_id,str) or not re.fullmatch(r'[a-fA-F0-9-]{32,36}',prompt_id):raise ValueError('ComfyUI did not return a prompt identity')
        deadline=time.monotonic()+600
        completed=False
        try:
            while time.monotonic()<deadline:
                if cancel.is_set():raise asyncio.CancelledError()
                history=await self.request('GET','/history/'+prompt_id)
                result=history.get(prompt_id)
                if result:
                    if result.get('status',{}).get('status_str')=='error':raise ValueError('The ComfyUI workflow failed; inspect the local engine log')
                    images=result.get('outputs',{}).get('7',{}).get('images',[])
                    if not images:raise ValueError('The engine finished without an image artifact')
                    image=images[0]
                    if image.get('type')!='output' or image.get('subfolder')!='OLIVE' or not str(image.get('filename','')).startswith(job_id):raise ValueError('Engine output provenance did not match this job')
                    from urllib.parse import urlencode
                    data=await self.request('GET','/view?'+urlencode({'filename':image['filename'],'subfolder':'OLIVE','type':'output'}))
                    completed=True
                    return data,{'engine':'ComfyUI','version':metadata['version'],'checkpoint':checkpoint,'workflow':workflow,'prompt_id':prompt_id}
                publish('Generating with ComfyUI; waiting for this prompt output')
                await asyncio.sleep(.5)
            raise TimeoutError('Media generation exceeded ten minutes')
        finally:
            if not completed:
                # v0.35.0 supports identity-bound interruption; never use the
                # global interrupt, which can race with another client's job.
                await self.request('POST','/queue',json={'delete':[prompt_id]})
                await self.request('POST','/interrupt',json={'prompt_id':prompt_id})
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    queue=await self.request('GET','/queue')
                    if not any(item[1]==prompt_id for item in queue.get('queue_running',[])+queue.get('queue_pending',[])):break
                    await asyncio.sleep(.25)
                else:raise RuntimeError('The cancelled media prompt did not stop within 30 seconds')
            await self.release_idle()


class ComfyWorkflows(ComfyImages):
    """Runs one reviewed OLIVE graph from media_workflows on a loopback engine."""
    # Queue identities, node ids and paths stay internal; Chat sees progress text.

    @property
    def port(self):
        return urlsplit(self.url).port

    async def inventory(self, workflows):
        from .media_workflows import engine_inventory
        stats = await self.request('GET', '/system_stats')
        version = stats.get('system', {}).get('comfyui_version')
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('The endpoint is not an identifiable ComfyUI runtime')
        nodes = await self.request('GET', '/object_info')
        return engine_inventory(version, nodes, workflows)

    async def busy(self):
        queue = await self.request('GET', '/queue')
        return bool(queue.get('queue_running') or queue.get('queue_pending'))

    async def upload(self, name, data):
        uploaded = await self.request('POST', '/upload/image', files={'image': (name, data, 'image/png')},
                                      data={'overwrite': 'false', 'type': 'input'})
        if uploaded.get('name') != name or uploaded.get('subfolder', '') != '':
            raise ValueError('Unexpected imported-image identity')
        return name

    @staticmethod
    def measurable(stats):
        devices = stats.get('devices', [])
        return ('--disable-dynamic-vram' in stats.get('system', {}).get('argv', [])
                and not any('cudaMallocAsync' in d.get('name', '') for d in devices))

    async def released(self, stats):
        devices = stats.get('devices', [])
        if devices and all(d.get('type') == 'cpu' for d in devices):
            return True
        if self.measurable(stats):
            return bool(devices) and all(d.get('type') == 'cpu' or d.get('type') == 'cuda' and isinstance(d.get('torch_vram_total'), int)
                                         and 0 <= d['torch_vram_total'] <= 256 * 1024 * 1024 for d in devices)
        # cudaMallocAsync/dynamic VRAM hide allocator totals; observe the process.
        from .gpu_probe import RELEASED_MIB, listening_pid, process_gpu_mib
        used = await process_gpu_mib(await asyncio.to_thread(listening_pid, self.port))
        if used is None:
            raise RuntimeError('Media GPU release cannot be observed for this engine')
        return used <= RELEASED_MIB

    async def release_idle(self):
        if await self.busy():
            raise RuntimeError('The configured media engine is still busy; local chat must wait for GPU release')
        await self.request('POST', '/free', json={'unload_models': True, 'free_memory': True})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if await self.busy():
                raise RuntimeError('The media engine became busy during GPU release')
            if await self.released(await self.request('GET', '/system_stats')):
                return
            await asyncio.sleep(.25)
        raise RuntimeError('The media engine did not confirm GPU memory release within 30 seconds')

    async def run(self, graph, job_id, cancel, progress, *, kind, timeout):
        """Queue one graph, wait for its own output, and always release after."""
        if await self.busy():
            raise RuntimeError('engine_busy')
        if cancel.is_set():
            raise asyncio.CancelledError()
        queued = await self.request('POST', '/prompt', json={'prompt': graph, 'client_id': job_id})
        prompt_id = queued.get('prompt_id')
        if queued.get('node_errors') or not isinstance(prompt_id, str) or not re.fullmatch(r'[a-fA-F0-9-]{32,36}', prompt_id):
            raise RuntimeError('workflow_rejected')
        completed = False
        started = time.monotonic()
        noun = 'video' if kind == 'video' else 'image'
        try:
            while time.monotonic() - started < timeout:
                if cancel.is_set():
                    raise asyncio.CancelledError()
                history = (await self.request('GET', '/history/' + prompt_id)).get(prompt_id)
                if history:
                    if history.get('status', {}).get('status_str') == 'error':
                        raise RuntimeError('workflow_failed')
                    items = history.get('outputs', {}).get('save', {}).get('images', [])
                    if not items:
                        raise RuntimeError('no_artifact')
                    item = items[0]
                    name = str(item.get('filename', ''))
                    if (item.get('type') != 'output' or item.get('subfolder') != 'OLIVE' or not name.startswith(job_id)
                            or '/' in name or '\\' in name):
                        raise RuntimeError('Engine output provenance did not match this job')
                    progress('Saving ' + noun + '…')
                    from urllib.parse import urlencode
                    data = await self.request('GET', '/view?' + urlencode({'filename': name, 'subfolder': 'OLIVE', 'type': 'output'}))
                    completed = True
                    return data, name, prompt_id
                queue = await self.request('GET', '/queue')
                running = any(len(row) > 1 and row[1] == prompt_id for row in queue.get('queue_running', []))
                progress(f'Generating {noun}…' if running else 'Waiting for the local engine…')
                await asyncio.sleep(.5)
            raise TimeoutError('timeout')
        finally:
            if not completed:
                try:
                    await self.request('POST', '/queue', json={'delete': [prompt_id]})
                    await self.request('POST', '/interrupt', json={'prompt_id': prompt_id})
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        queue = await self.request('GET', '/queue')
                        if not any(len(row) > 1 and row[1] == prompt_id
                                   for row in queue.get('queue_running', []) + queue.get('queue_pending', [])):
                            break
                        await asyncio.sleep(.25)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Media prompt cleanup failed')
