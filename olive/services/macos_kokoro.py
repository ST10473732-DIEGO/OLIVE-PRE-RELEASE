"""Native offline Kokoro speech adapter for macOS OLIVE AUDIO mode.
Only usable following native WAV acceptance. No arbitrary command execution.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import wave

from .media_errors import MediaError

from .macos_workspace import external_root
ROOT=external_root()  # Verified by the packaged app; unset means unavailable.
EXECUTABLE=ROOT/'envs/kokoro/bin/python'
WORKER=ROOT/'bin/olive_kokoro_worker.py'
RECEIPT=ROOT/'benchmarks/KOKORO-NATIVE-TTS-ACCEPTANCE-20261123.json'
SAMPLE=ROOT/'benchmarks/olive-kokoro-82m-test.wav'

def available():
    if os.environ.get('OLIVE_ENABLE_NATIVE_KOKORO')!='1':
        return False
    if sys.platform!='darwin' or not EXECUTABLE.is_file() or not WORKER.is_file():
        return False
    if not os.access(EXECUTABLE,os.X_OK) or not RECEIPT.is_file() or not SAMPLE.is_file():
        return False
    if RECEIPT.is_symlink() or SAMPLE.is_symlink() or WORKER.is_symlink():
        return False
    try:
        x=json.loads(RECEIPT.read_text())
        if x.get('status')!='PASS' or x.get('model')!='mlx-community/Kokoro-82M-bf16':
            return False
        with SAMPLE.open('rb') as f:
            digest=hashlib.file_digest(f,'sha256').hexdigest()
        return digest==x.get('wav_sha256') and SAMPLE.stat().st_size==x.get('bytes')
    except (OSError,ValueError,TypeError):
        return False

async def _stop(proc):
    if proc.returncode is not None:return
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:await asyncio.wait_for(proc.wait(),timeout=5)
    except asyncio.TimeoutError:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        await proc.wait()

async def generate(media,request,cancel,progress):
    if not available():
        raise MediaError('audio_not_configured')
    text=request.get('speech')
    if not isinstance(text,str) or not 1<=len(text)<=4000:
        raise MediaError('speech_text_required')
    if request.get('voice','default') not in ('default','af_heart'):
        raise MediaError('audio_unsupported')
    assert media.root.resolve().is_relative_to(ROOT.resolve())
    jobs=media.root/'jobs'
    assert not jobs.is_symlink()
    jobs.mkdir(parents=True,exist_ok=True)
    target=jobs/(secrets.token_hex(16)+'.wav')
    assert not target.exists()
    env={**os.environ,
         'HF_HOME':str(ROOT/'model-store/media/hf'),
         'HF_HUB_CACHE':str(ROOT/'model-store/media/hf/hub'),
         'HUGGINGFACE_HUB_CACHE':str(ROOT/'model-store/media/hf/hub'),
         'HF_XET_CACHE':str(ROOT/'model-store/media/hf/xet'),
         'HF_HUB_OFFLINE':'1',
         'TRANSFORMERS_OFFLINE':'1',
         'HF_HUB_DISABLE_TELEMETRY':'1',
         'OLLAMA_NO_CLOUD':'1',
         'TMPDIR':str(ROOT/'cache/tmp')+'/',
         'HOME':str(ROOT/'envs/kokoro-home')}
    if not Path(env['HOME']).is_dir():
        Path(env['HOME']).mkdir(mode=0o700,parents=True,exist_ok=True)
    progress('Generating local speech with Kokoro MLX…')
    data=json.dumps({'text':text,'voice':'af_heart','output':str(target)}).encode()
    proc=await asyncio.create_subprocess_exec(
        str(EXECUTABLE),'-s','-P',str(WORKER),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,env=env,
        cwd=str(ROOT/'benchmarks'),start_new_session=True)
    finished=asyncio.create_task(proc.communicate(data))
    cancelled=asyncio.create_task(cancel.wait())
    try:
        done,_=await asyncio.wait({finished,cancelled},timeout=180,
                                 return_when=asyncio.FIRST_COMPLETED)
        if cancelled in done:
            await _stop(proc)
            raise asyncio.CancelledError()
        if finished not in done:
            await _stop(proc)
            raise MediaError('timeout')
        if proc.returncode!=0 or not target.is_file() or target.is_symlink():
            raise MediaError('generation_failed')
        with wave.open(str(target),'rb') as f:
            assert f.getnframes()>3000 and f.getframerate()==24000
            seconds=f.getnframes()/f.getframerate()
        wav=target.read_bytes()
        progress('Saving speech artifact…')
        return media.save_generated(
            'audio',wav,'wav','audio/wav',mode=request['mode'],
            generator={'provider':'Kokoro MLX','family':'Kokoro 82M','engine':'native-macos'},
            parameters={'text':text,'voice':'af_heart','style':request.get('style','')},
            extra={'duration_seconds':round(seconds,3)},
            provenance={'engine':'kokoro-mlx','offline':True,'sample_rate':24000})
    finally:
        finished.cancel()
        cancelled.cancel()
        if proc.returncode is None: await _stop(proc)
        if target.is_file() and not target.is_symlink():target.unlink()
