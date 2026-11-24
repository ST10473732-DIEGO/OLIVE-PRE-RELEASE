"""Native external-SSD macOS MFLUX image backend for OLIVE.

No shell, network service, external providers, or custom CLI paths. This module
does not auto-enable an engine: a real verified PNG acceptance receipt is needed.
Works only on macOS, and never reads original restored Linux identity.
"""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time
from PIL import Image,ImageOps

from .media_errors import MediaError

from .macos_workspace import external_root
ROOT=external_root()  # Verified by the packaged app; unset means unavailable.
EXECUTABLE=ROOT/"envs/mflux/bin/mflux-generate-flux2"
EDIT_EXECUTABLE=ROOT/"envs/mflux/bin/mflux-generate-flux2-edit"
RECEIPT=ROOT/"model-store/media/flux2-klein-4b-acceptance.json"
SAMPLE=ROOT/"benchmarks/olive-flux2-klein-4b-512.png"
EDIT_RECEIPT=ROOT/"model-store/media/flux2-klein-4b-edit-acceptance.json"
EDIT_SAMPLE=ROOT/"benchmarks/olive-flux2-klein-4b-edit-512.png"

def available():
    # Opt in only from OLIVE's validated native macOS launcher or a scoped test.
    if os.environ.get('OLIVE_ENABLE_NATIVE_MFLUX')!='1':
        return False
    if sys.platform!='darwin' or not EXECUTABLE.is_file() or not os.access(EXECUTABLE,os.X_OK):
        return False
    if not RECEIPT.is_file() or RECEIPT.is_symlink() or not SAMPLE.is_file() or SAMPLE.is_symlink():
        return False
    try:
        x=json.loads(RECEIPT.read_text())
        if x.get('status')!='PASS' or x.get('model')!='flux2-klein-4b':
            return False
        with SAMPLE.open('rb') as f:
            actual=hashlib.file_digest(f,'sha256').hexdigest()
        return actual==x.get('png_sha256') and SAMPLE.stat().st_size==x.get('bytes')
    except (OSError,ValueError,TypeError):
        return False

def edit_available():
    if not available() or not EDIT_EXECUTABLE.is_file() or not os.access(EDIT_EXECUTABLE,os.X_OK):
        return False
    if not EDIT_RECEIPT.is_file() or EDIT_RECEIPT.is_symlink() or not EDIT_SAMPLE.is_file() or EDIT_SAMPLE.is_symlink():
        return False
    try:
        record=json.loads(EDIT_RECEIPT.read_text())
        if record.get('status')!='PASS' or record.get('model')!='flux2-klein-4b' or record.get('operation')!='single-image-edit':
            return False
        with EDIT_SAMPLE.open('rb') as sample:
            digest=hashlib.file_digest(sample,'sha256').hexdigest()
        return digest==record.get('png_sha256') and EDIT_SAMPLE.stat().st_size==record.get('bytes')
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
        raise MediaError('image_not_configured')
    references=request.get('references') or []
    if len(references)>1:
        raise MediaError('too_many_references')
    if references and not edit_available():
        raise MediaError('attachment_unsupported_mode')
    prompt=request['prompt']
    if not isinstance(prompt,str) or not 1<=len(prompt)<=4000:
        raise MediaError('prompt_required')
    assert media.root.resolve().is_relative_to(ROOT.resolve())
    jobs=media.root/'jobs'
    if jobs.is_symlink():
        raise MediaError('generation_failed')
    jobs.mkdir(parents=True,exist_ok=True)
    job=secrets.token_hex(16)
    outfile=jobs/(job+'.png')
    input_path=jobs/(job+'-source.png')
    assert not outfile.exists() and not input_path.exists()
    if references:
        try:
            with Image.open(io.BytesIO(references[0][1])) as img:
                if img.width*img.height>24_000_000:
                    raise MediaError('unsupported_attachment')
                normalized=ImageOps.pad(ImageOps.exif_transpose(img).convert('RGB'),(512,512),color=(250,250,250))
                normalized.save(input_path,format='PNG')
                input_path.chmod(0o600)
        except MediaError:
            raise
        except Exception:
            raise MediaError('unsupported_attachment') from None
    env={**os.environ,
      'HF_HOME':str(ROOT/'model-store/media/hf'),
      'HF_HUB_CACHE':str(ROOT/'model-store/media/hf/hub'),
      'HUGGINGFACE_HUB_CACHE':str(ROOT/'model-store/media/hf/hub'),
      'HF_XET_CACHE':str(ROOT/'model-store/media/hf/xet'),
      'HF_HUB_OFFLINE':'1',
      'HF_HUB_DISABLE_TELEMETRY':'1',
      'TRANSFORMERS_OFFLINE':'1',
      'TMPDIR':str(ROOT/'cache/tmp')+'/',
      'HOME':str(ROOT/'envs/mflux-home')}
    if not Path(env['HOME']).is_dir():
        Path(env['HOME']).mkdir(mode=0o700,parents=True,exist_ok=True)
    seed=secrets.randbelow(2**32)
    argv=[str(EDIT_EXECUTABLE if references else EXECUTABLE),'--model','flux2-klein-4b',
          '--small-text-encoder','--quantize','4','--steps','4',
          '--seed',str(seed),'--width','512','--height','512']
    if references:
        argv+=['--image-paths',str(input_path)]
    argv+=['--prompt',prompt,'--output',str(outfile)]
    progress('Editing image with MLX…' if references else 'Generating image locally with MLX…')
    began=time.monotonic()
    proc=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.DEVNULL,
             stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,
             env=env,cwd=str(ROOT/'benchmarks'),start_new_session=True)
    finished=asyncio.create_task(proc.wait())
    cancelled=asyncio.create_task(cancel.wait())
    try:
        done,_=await asyncio.wait({finished,cancelled},timeout=600,
                                  return_when=asyncio.FIRST_COMPLETED)
        if cancelled in done:
            await _stop(proc)
            raise asyncio.CancelledError()
        if finished not in done:
            await _stop(proc)
            raise MediaError('timeout')
        if proc.returncode!=0 or not outfile.is_file() or outfile.is_symlink():
            raise MediaError('generation_failed')
        raw=outfile.read_bytes()
        if raw[:8]!=b'\x89PNG\r\n\x1a\n':
            raise MediaError('no_artifact')
        progress('Saving MLX image…')
        return media.save_generated('image',raw,'png','image/png',mode=request['mode'],
           generator={'provider':'MFLUX','family':'FLUX.2 Klein 4B','workflow':'macos-mlx-4bit'},
           parameters={'prompt':prompt,'seed':seed,'steps':4,'width':512,'height':512,
                       'operation':'edit' if references else 'generate',
                       'reference_count':len(references)},
           provenance={'engine':'MFLUX','model':'flux2-klein-4b',
                       'quantization':'4bit','seconds':round(time.monotonic()-began,1),
                       'offline_generation':True})
    finally:
        finished.cancel()
        cancelled.cancel()
        if proc.returncode is None:await _stop(proc)
        if outfile.is_file() and not outfile.is_symlink():outfile.unlink()
        if input_path.is_file() and not input_path.is_symlink():input_path.unlink()
