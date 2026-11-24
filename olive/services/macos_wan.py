"""Native Apple Silicon Wan2.1 MLX short text-to-video for OLIVE.

Fail-closed opt-in after real MP4 acceptance. A fixed-duration, silent 256px
clip is supported on M1 Max; longer/HD/I2V are NOT advertised. Model/output/
cache all live on user's verified external APFS. No shell, remote model, or
inherited network is required.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time

from .media_errors import MediaError

from .macos_workspace import external_root
ROOT=external_root()  # Verified by the packaged app; unset means unavailable.
MODEL=ROOT/'model-store/media/wan21/mlx-q4'
ENGINE=ROOT/'envs/mlx-video/bin/python'
VALIDATOR=ROOT/'bin/olive_validate_wan_mp4.py'
SAMPLE=ROOT/'benchmarks/olive-wan21-1p3b-17f-4steps.mp4'
RECEIPT=ROOT/'benchmarks/WAN21-NATIVE-17FRAME-ACCEPTANCE-20261123.json'
DURATION=1.25

def available():
    if os.environ.get('OLIVE_ENABLE_NATIVE_WAN')!='1' or sys.platform!='darwin':
        return False
    if not ENGINE.is_file() or not os.access(ENGINE,os.X_OK) or not VALIDATOR.is_file():
        return False
    if not all((MODEL/p).is_file() and not (MODEL/p).is_symlink()
               for p in ('model.safetensors','t5_encoder.safetensors','vae.safetensors','config.json')):
        return False
    if not SAMPLE.is_file() or SAMPLE.is_symlink() or not RECEIPT.is_file() or RECEIPT.is_symlink():
        return False
    try:
        info=json.loads(RECEIPT.read_text())
        if info.get('status')!='PASS' or info.get('model')!='Wan-AI/Wan2.1-T2V-1.3B':
            return False
        with SAMPLE.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        return digest==info.get('sha256') and SAMPLE.stat().st_size==info.get('bytes')
    except (OSError,ValueError,TypeError):
        return False

async def _stop(proc):
    if proc.returncode is not None:return
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:await asyncio.wait_for(proc.wait(),timeout=6)
    except asyncio.TimeoutError:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        await proc.wait()

async def generate(media,request,cancel,progress):
    if not available():
        raise MediaError('video_not_configured')
    if request.get('references'):
        raise MediaError('video_image_unsupported')
    prompt=request['prompt']
    if not isinstance(prompt,str) or not 1<=len(prompt)<=4000 or '\x00' in prompt:
        raise MediaError('prompt_required')
    if not media.root.resolve().is_relative_to((ROOT/'data-private').resolve()):
        raise MediaError('generation_failed')
    jobs=media.root/'jobs'
    if jobs.is_symlink():
        raise MediaError('generation_failed')
    jobs.mkdir(mode=0o700,parents=True,exist_ok=True)
    output=jobs/(secrets.token_hex(16)+'.mp4')
    if output.exists():
        raise MediaError('generation_failed')
    env={**os.environ,
         'HF_HOME':str(ROOT/'model-store/media/hf'),
         'HF_HUB_CACHE':str(ROOT/'model-store/media/hf/hub'),
         'HUGGINGFACE_HUB_CACHE':str(ROOT/'model-store/media/hf/hub'),
         'HF_XET_CACHE':str(ROOT/'model-store/media/hf/xet'),
         'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
         'OLLAMA_NO_CLOUD':'1','HF_HUB_DISABLE_TELEMETRY':'1',
         'TMPDIR':str(ROOT/'cache/tmp')+'/',
         'HOME':str(ROOT/'envs/mlx-video-home'),
         'OMP_NUM_THREADS':'6'}
    Path(env['HOME']).mkdir(mode=0o700,parents=True,exist_ok=True)
    seed=secrets.randbelow(2**32)
    argv=[str(ENGINE),'-s','-P','-m','mlx_video.models.wan_2.generate',
          '--model-dir',str(MODEL),'--prompt',prompt,
          '--width','256','--height','256','--num-frames','17',
          '--steps','4','--guide-scale','1.0','--no-negative-prompt',
          '--scheduler','euler','--tiling','aggressive',
          '--seed',str(seed),'--output-path',str(output)]
    progress('Generating a short silent video locally with Wan MLX…')
    began=time.monotonic()
    proc=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.DEVNULL,
       stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,
       env=env,cwd=str(ROOT/'benchmarks'),start_new_session=True)
    finished=asyncio.create_task(proc.wait())
    cancelled=asyncio.create_task(cancel.wait())
    try:
        done,_=await asyncio.wait({finished,cancelled},timeout=360,
                                  return_when=asyncio.FIRST_COMPLETED)
        if cancelled in done:
            await _stop(proc)
            raise asyncio.CancelledError()
        if finished not in done:
            await _stop(proc)
            raise MediaError('timeout')
        if proc.returncode!=0 or not output.is_file() or output.is_symlink():
            raise MediaError('generation_failed')
        verify=await asyncio.create_subprocess_exec(str(ENGINE),'-s','-P',str(VALIDATOR),str(output),
                     stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,
                     stderr=asyncio.subprocess.DEVNULL,env=env,cwd=str(ROOT/'benchmarks'))
        try:
            stdout,_=await asyncio.wait_for(verify.communicate(),timeout=30)
        except asyncio.TimeoutError:
            verify.kill()
            await verify.wait()
            raise MediaError('no_artifact')
        if verify.returncode!=0 or len(stdout)>1000:
            raise MediaError('no_artifact')
        facts=json.loads(stdout)
        raw=output.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=facts['sha256']:
            raise MediaError('no_artifact')
        progress('Saving verified local MP4…')
        return media.save_generated(
            'video',raw,'mp4','video/mp4',mode=request['mode'],
            generator={'provider':'mlx-video','family':'Wan2.1 1.3B','workflow':'native-macos-t2v-q4'},
            parameters={'prompt':prompt,'seed':seed,'steps':4,'width':256,'height':256,
                        'frames_requested':17,'duration_seconds':DURATION,'audio':False,
                        'operation':'text-to-video'},
            extra={'width':facts['width'],'height':facts['height'],
                   'duration_seconds':facts['duration_seconds'],'has_audio':False,
                   'frames':facts['frames'],'fps':facts['fps']},
            provenance={'engine':'mlx-video','model':'Wan-AI/Wan2.1-T2V-1.3B',
                        'quantization':'4bit','no_cloud':True,
                        'elapsed_seconds':round(time.monotonic()-began,1)})
    finally:
        finished.cancel();cancelled.cancel()
        if proc.returncode is None:await _stop(proc)
        if output.is_file() and not output.is_symlink():output.unlink()
