"""Chat-native REIMAGINE, AUDIO and VIDEO generation.

ChatController -> media preset -> ChatMediaService -> engine provider
(ComfyUI image/video or VoiceStudio speech) -> MediaService artifact ->
assistant message with structured artifact metadata.

One engine and one workflow per request. The user's text is sent verbatim
(no prompt enhancement). Heavy work is serialized with local text inference
through the model residency lock, and the engine is released afterwards.
"""
import asyncio
import base64
from datetime import datetime
import io
import logging
import os
import re
import secrets
import time

from PIL import Image, ImageOps

from .media_engines import MediaEngines
from .media_errors import MediaError
from .media_workflows import image_graph, route, video_graph
from .voicestudio import VoiceStudio

log = logging.getLogger(__name__)

MEDIA_PRESETS = {'reimagine': 'image', 'audio': 'audio', 'video': 'video'}
LABELS = {'image': 'IMAGE', 'audio': 'SPEECH', 'video': 'LTX'}
SPEECH = re.compile(r'''^(?P<prefix>.*?)\b(?:say|says|saying|speak|speaking|read(?:\s+(?:out|aloud))?|narrat(?:e|ing))\b\s*[:,-]?\s*(?P<text>.+)$''', re.I | re.S)
INSTRUCTION = re.compile(r'^\s*(?:please\s+)?(?:create|make|generate|produce|write|compose|record)\b', re.I)
# Only speech is installed and validated; these must not be read aloud instead.
UNSUPPORTED_AUDIO = re.compile(r'^\s*(?:please\s+)?(?:sing|hum|rap)\b|\b(?:song|singing|music|melody|instrumental|beat|soundtrack|'
                               r'sound effects?|sfx|jingle|clone (?:my|a|this) voice|voice clon\w*)\b', re.I)
TONES = ('calm', 'warm', 'soft', 'gentle', 'friendly', 'cheerful', 'energetic', 'excited', 'serious', 'slow',
         'fast', 'whisper', 'whispering', 'low', 'deep', 'high', 'bright', 'professional', 'soothing')


def speech_request(text):
    """Split an AUDIO request into the exact words to speak and a tone hint."""
    value = text.strip()
    quoted = re.search(r'["“]([^"”]{1,4000})["”]', value)
    match = SPEECH.match(value)
    if match and match.group('text').strip():
        words = match.group('text').strip()
        prefix = match.group('prefix')
    elif quoted:
        words, prefix = quoted.group(1), value[:quoted.start()]
    elif INSTRUCTION.match(value):
        raise MediaError('speech_text_required')
    else:
        words, prefix = value, ''
    inner = re.fullmatch(r'["“](.+)["”][.!?]?', words.strip(), re.S)
    words = (inner.group(1) if inner else words).strip()
    if not re.search(r'\w', words):  # "Say:" alone, or punctuation only.
        raise MediaError('speech_text_required')
    if len(words) > 4000:
        raise MediaError('speech_too_long')
    tones = [tone for tone in TONES if re.search(rf'\b{tone}\b', prefix, re.I)]
    return words, ', '.join(tones)


class ChatMediaService:
    TIMEOUTS = {'image': 600, 'video': 1200}

    def __init__(self, services):
        self.s = services
        self.media = services.media
        self.engines = self.media.engines
        self.voice = VoiceStudio(os.environ.get('OLIVE_VOICESTUDIO_URL', ''), os.environ.get('OLIVE_VOICESTUDIO_ROOT', ''))
        self.progress = {}
        self.lock = asyncio.Lock()  # One Chat media generation at a time.

    # ------------------------------------------------------------------ status
    def status(self, preset):
        kind = MEDIA_PRESETS[preset]
        if kind == 'audio':
            last = self.voice.last
            state = last.get('state', 'unknown')
            ready = state == 'ready'
            ready = state in {'ready', 'stopped'}
            text = {'ready': 'Ready', 'stopped': 'Ready · speech service starts on request', 'not configured': 'Needs setup',
                    'unreachable': 'Needs setup · service not running', 'needs setup': 'Needs setup · no voice model installed',
                    'exposed': 'Needs setup · speech service is exposed on the network',
                    'unverified': 'Needs setup · cannot verify the speech service is local-only'}.get(state, 'Checking')
            return {'available': ready, 'status': text, 'runtime': 'VoiceStudio (local service)',
                    'capabilities': list(last.get('capabilities', [])), 'engine_state': state}
        engine = self.engines.get(kind)
        info = engine.status()
        state = info['state']
        ready = state in {'available', 'ready', 'busy', 'starting'}
        text = {'available': 'Ready · engine starts on request', 'ready': 'Ready', 'busy': 'Busy', 'starting': 'Starting',
                'not installed': 'Needs setup', 'needs setup': 'Needs setup · model or workflow missing',
                'failed': 'Engine failed · retry to restart'}.get(state, 'Checking')
        capabilities = []
        if 'flux2-klein-9b' in info['ready_workflows'] or 'qwen-image-2.1' in info['ready_workflows']:
            capabilities = ['text-to-image', 'image-edit']
        elif 'sdxl-base' in info['ready_workflows']:
            capabilities = ['text-to-image']
        if 'ltx-2.3-t2av' in info['ready_workflows']:
            capabilities = ['text-to-video', 'video-audio']
        return {'available': ready or state == 'failed', 'status': text, 'engine_state': state,
                'runtime': 'Local ComfyUI · ' + ('image' if kind == 'image' else 'video') + ' engine',
                'capabilities': capabilities}

    def diagnostics(self):
        """Advanced-only view: exact workflow states, never shown in normal Chat."""
        return {'image': self.engines.image.status(), 'video': self.engines.video.status(),
                'audio': dict(self.voice.last), 'image_endpoint': self.engines.image.endpoint,
                'video_endpoint': self.engines.video.endpoint, 'audio_endpoint': self.voice.url}

    async def refresh(self):
        for engine in self.engines.all():
            try:
                await engine.probe()
            except Exception:
                log.exception('Media engine probe failed')
        await self.voice.status()
        return self.diagnostics()

    async def voices(self):
        """Voices the local service lists, only once it is verified local-only.
        Opening AUDIO may start OLIVE's own loopback service (no model load)."""
        selected = self.s.settings.get('media_audio_voice', 'default')
        status = await self.voice.status()
        if status['state'] == 'stopped':
            try:
                await self.voice.runtime.start()
            except Exception:
                log.exception('VoiceStudio start for voice listing failed')
            status = await self.voice.status()
        if status['state'] != 'ready':
            return {'selected': selected, 'voices': []}
        return {'selected': selected, 'voices': await self.voice.voices()}

    async def select_voice(self, voice):
        voices = (await self.voices())['voices']
        if voice not in {v['id'] for v in voices}:
            raise ValueError('Choose a voice the local speech service lists')
        self.s.settings['media_audio_voice'] = voice
        self.s.settings_repo.save(self.s.settings)
        return await self.voices()

    # ------------------------------------------------------------------ plan
    def plan(self, chat, text, images):
        """Validate a request before any user-visible generation starts."""
        kind = MEDIA_PRESETS[chat.preset]
        text = text.strip()
        if not text:
            raise MediaError('prompt_required')
        if len(text) > 4000:
            raise MediaError('prompt_too_long')
        if chat.documents:
            raise MediaError('attachment_unsupported_mode')
        request = {'kind': kind, 'mode': chat.preset, 'prompt': text, 'references': []}
        # Fail fast, before the text model is unloaded, when nothing is set up.
        if kind == 'audio' and not self.voice.url:
            raise MediaError('audio_not_configured')
        if kind != 'audio' and not self.engines.get(kind).configured():
            raise MediaError(f'{kind}_not_configured')
        if kind == 'audio':
            if images:
                raise MediaError('attachment_unsupported_mode')
            if re.match(r'\s*(?:please\s+)?(?:sing|hum|rap)\b', text, re.I):
                raise MediaError('audio_unsupported')
            try:
                request['speech'], request['style'] = speech_request(text)
            except MediaError:
                if UNSUPPORTED_AUDIO.search(text):
                    raise MediaError('audio_unsupported') from None
                raise
            # Only the instruction is checked; the words to speak may mention anything.
            if UNSUPPORTED_AUDIO.search(text.replace(request['speech'], ' ', 1)):
                raise MediaError('audio_unsupported')
            request['voice'] = self.s.settings.get('media_audio_voice', 'default')
            return request
        if kind == 'video' and images:
            # The validated LTX workflow is text-to-video only (image input bypassed).
            raise MediaError('attachment_unsupported_mode')
        if len(images) > 1:
            raise MediaError('too_many_references')
        for name, data in images:
            try:
                raw = base64.b64decode(data, validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in {'PNG', 'JPEG', 'WEBP', 'BMP'} or image.width * image.height > 24_000_000:
                        raise MediaError('unsupported_attachment')
                    image.verify()
            except MediaError:
                raise
            except Exception:
                raise MediaError('unsupported_attachment') from None
            request['references'].append((name, raw))
        return request

    # ------------------------------------------------------------------ GPU
    def managed_models(self):
        from .presets import PRESETS
        names = {p['model'] for p in PRESETS.values() if p['model']}
        router = getattr(self.s, 'uncensored_router', None)
        if router:
            try:
                names.update(router.available_models())
            except Exception:
                pass
        names.update(chat.model for chat in self.s.chats.values() if chat.model)
        residency = self.s.ollama.residency
        names.update(residency.recent)
        return names

    async def _take_gpu(self, keep, progress):
        """Called with the residency lock held: text model out, other engines idle."""
        residency = self.s.ollama.residency
        if residency.current:
            progress('Releasing the text model…')
            current = residency.current
            try:
                if current in residency.providers:
                    await residency.providers[current][1]()
                else:
                    await self.s.ollama.unload_model(current)
            except Exception as error:
                if getattr(error, 'status_code', None) != 404:
                    raise MediaError('gpu_release_unverified', type(error).__name__) from None
            residency.current = None
            residency.switches += 1
        managed = self.managed_models()
        requested = set()
        for _ in range(40):  # keep_alive=0 unloads asynchronously.
            try:
                loaded = await self.s.ollama.loaded_models()
            except Exception:
                loaded = []  # No reachable Ollama server holds no GPU memory for OLIVE.
            if not loaded:
                break
            # A model OLIVE's own presets/chats use (e.g. still resident from before
            # a restart) is OLIVE's to unload; any other client's model blocks.
            foreign = [m['name'] for m in loaded if m['name'] not in managed]
            if foreign:
                raise MediaError('gpu_busy', ','.join(foreign)[:200])
            for model in {m['name'] for m in loaded} - requested:
                requested.add(model)
                progress('Releasing the text model…')
                try:
                    await self.s.ollama.unload_model(model)
                except Exception as error:
                    if getattr(error, 'status_code', None) != 404:
                        raise MediaError('gpu_release_unverified', type(error).__name__) from None
            await asyncio.sleep(.25)
        else:
            raise MediaError('gpu_busy', ','.join(m['name'] for m in loaded)[:200])
        await self.engines.release_others(keep=keep)
        if keep is not None:
            await self._release_owned_voice(progress)

    async def _release_owned_voice(self, progress):
        """VoiceStudio keeps ~2 GiB allocated after unloading its model. When
        OLIVE owns that process, stop it before a heavy image/video engine needs
        the GPU; it restarts on the next AUDIO request. A service someone else
        started is never stopped."""
        runtime = self.voice.runtime
        if not runtime or not runtime.owned():
            return
        from .gpu_probe import RELEASED_MIB, process_gpu_mib
        used = await process_gpu_mib(runtime.owned_process.process.pid)
        # CUDA context alone stays under the release bound; more is held weights.
        if used is None or used > RELEASED_MIB // 4:
            progress('Releasing the audio engine…')
            await runtime.close()

    # ------------------------------------------------------------------ run
    async def generate(self, chat_id, request, cancel):
        def progress(text):
            if self.progress.get(chat_id) != text:
                self.progress[chat_id] = text
                self.s.publish('chat', self.s.chat.get(chat_id))
        kind = request['kind']
        progress({'image': 'Preparing image engine…', 'video': 'Preparing video engine…', 'audio': 'Preparing audio engine…'}[kind])
        residency = self.s.ollama.residency
        try:
            async with self.lock:
                await residency.lock.acquire()
                try:
                    residency.active = 'media:' + kind
                    if kind == 'audio':
                        return await self._audio(request, cancel, progress)
                    return await self._comfy(kind, request, cancel, progress)
                finally:
                    residency.active = None
                    residency.lock.release()
        finally:
            self.progress.pop(chat_id, None)

    async def _audio(self, request, cancel, progress):
        if not self.voice.url:
            raise MediaError('audio_not_configured')
        await self._take_gpu(None, progress)
        progress('Generating speech…')
        started = time.monotonic()
        try:
            data, info = await self.voice.speech(request['speech'], request['voice'], request['style'], cancel, progress)
        finally:
            try:
                await self.voice.release()
            except Exception:
                log.exception('VoiceStudio model release failed')
        progress('Saving audio…')
        return self.media.save_generated(
            'audio', data, 'wav', 'audio/wav', mode=request['mode'],
            generator={'provider': 'VoiceStudio', 'family': 'Speech', 'engine': info['engine'][:80]},
            parameters={'text': request['speech'], 'voice': request['voice'], 'style': request['style']},
            extra={'duration_seconds': info['duration_seconds']},
            provenance={'engine': 'VoiceStudio', 'service_version': info['service_version'], 'engine_label': info['engine_label'],
                        'seconds': round(time.monotonic() - started, 1)})

    async def _comfy(self, kind, request, cancel, progress):
        engine = self.engines.get(kind)
        await self._take_gpu(engine, progress)
        inventory = await engine.prepare(progress)
        workflow, shape, reasons = route(kind, request['prompt'], request['references'], inventory)
        if not workflow:
            log.info('No %s workflow routable: %s', kind, reasons)
            missing = any(str(v).startswith('model missing') for v in reasons.values())
            raise MediaError('model_missing' if missing else 'workflow_missing', str(reasons))
        job = secrets.token_hex(16)
        seed = secrets.randbelow(2 ** 48)
        source_ids = []
        reference_name = None
        if request['references']:
            name, raw = request['references'][0]
            original = self.media.preserve_bytes(name, raw)  # Original attachment stays intact.
            source_ids.append(original['id'])
            with Image.open(io.BytesIO(raw)) as image:
                buffer = io.BytesIO()
                ImageOps.exif_transpose(image).convert('RGB').save(buffer, format='PNG')
            reference_name = await engine.client.upload(job + '-reference.png', buffer.getvalue())
        prefix = 'OLIVE/' + job
        graph = image_graph(workflow, request['prompt'], seed, prefix, reference_name) if kind == 'image' \
            else video_graph(workflow, request['prompt'], seed, prefix)
        engine.active = True
        started = time.monotonic()
        try:
            data, filename, prompt_id = await engine.client.run(
                graph, job, cancel, progress, kind=kind, timeout=self.TIMEOUTS[kind])
        except RuntimeError as error:
            code = str(error) if str(error) in MediaError.MESSAGES else 'generation_failed'
            code = {'workflow_rejected': 'workflow_missing', 'workflow_failed': 'generation_failed'}.get(str(error), code)
            raise MediaError(code, str(error)) from None
        except TimeoutError:
            raise MediaError('timeout') from None
        finally:
            engine.active = False
            try:
                await engine.client.release_idle()
            except Exception as error:
                # The next text or media request re-verifies before loading anything.
                log.warning('%s engine release after generation not verified: %s', kind, error)
        seconds = round(time.monotonic() - started, 1)
        if kind == 'image':
            progress('Saving image…')
            return self.media.save_generated(
                'image', data, 'png', 'image/png', mode=request['mode'], source_ids=source_ids,
                generator={'provider': 'ComfyUI', 'family': workflow.label, 'workflow': workflow.key, 'engine_version': inventory['version']},
                parameters={'prompt': request['prompt'], 'operation': 'edit' if source_ids else 'generate', 'seed': seed,
                            **{k: workflow.defaults[k] for k in ('steps', 'cfg') if k in workflow.defaults}},
                provenance={'engine': 'ComfyUI', 'version': inventory['version'], 'workflow': workflow.key, 'route': shape,
                            'rejected_routes': reasons, 'files': sorted(workflow.files.values()), 'prompt_id': prompt_id,
                            'output': filename, 'seconds': seconds})
        # ComfyUI encodes the MP4 inside the workflow; that stage is not observable
        # separately, so no extra "encoding" status is claimed here.
        d = workflow.defaults
        return self.media.save_generated(
            'video', data, 'mp4', 'video/mp4', mode=request['mode'],
            generator={'provider': 'ComfyUI', 'family': workflow.label, 'workflow': workflow.key, 'engine_version': inventory['version']},
            parameters={'prompt': request['prompt'], 'seed': seed, 'width': d['width'], 'height': d['height'],
                        'frames': d['length'], 'fps': d['fps'], 'steps': d['steps'], 'cfg': d['cfg'],
                        'sampler': d['sampler'], 'schedule': d['schedule'], 'upscale': 'latent x2'},
            provenance={'engine': 'ComfyUI', 'version': inventory['version'], 'workflow': workflow.key,
                        'files': sorted(workflow.files.values()), 'prompt_id': prompt_id, 'output': filename, 'seconds': seconds})


def created_now():
    return datetime.now().isoformat(timespec='seconds')
