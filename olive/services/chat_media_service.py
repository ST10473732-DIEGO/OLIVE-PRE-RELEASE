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
import hashlib
from datetime import datetime
import io
import json
import logging
import re
import secrets
import time

from PIL import Image, ImageOps

from pathlib import Path
import shutil

from . import video_assembly as assembly
from . import video_duration as durations
from .media_engines import MediaEngines
from .media_errors import MediaError
from .media_workflows import LTX_I2V, image_graph, route, video_graph, video_size
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
        from .runtime_discovery import from_environment
        located = (getattr(services, 'runtimes', None) or from_environment())['voicestudio']
        self.voice = VoiceStudio(located.get('url'), located.get('root'))
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
        if {'flux2-klein-9b', 'flux2-klein-4b', 'qwen-image-2.1'} & set(info['ready_workflows']):
            capabilities = ['text-to-image', 'image-edit']
        elif 'sdxl-base' in info['ready_workflows']:
            capabilities = ['text-to-image']
        if 'ltx-2.3-t2av' in info['ready_workflows']:
            capabilities = ['text-to-video', 'video-audio']
            if 'ltx-2.3-i2av' in info['ready_workflows']:
                capabilities.append('image-to-video')
            if assembly.tools():
                capabilities.append('long-video')
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
    # ------------------------------------------------------------------ video duration
    def video_policy(self):
        return durations.VideoPolicy.from_settings(self.s.settings)

    def image_to_video_ready(self):
        engine = self.engines.video
        return engine.configured() and engine.workflow_states().get(LTX_I2V.key) == 'ready'

    def video_capability(self):
        """What VIDEO can do here; the Remote AI panel and OLIVE Mobile read this."""
        policy = self.video_policy()
        states = self.engines.video.workflow_states() if self.engines.video.configured() else {}
        long_form = bool(assembly.tools())
        i2v = states.get(LTX_I2V.key) == 'ready'
        native = durations.NATIVE_FRAMES / durations.FPS
        return {'supports_text_to_video': states.get('ltx-2.3-t2av') == 'ready', 'supports_image_to_video': i2v,
                'supports_audio': states.get('ltx-2.3-t2av') == 'ready', 'native_segment_seconds': round(native, 4),
                'fps': durations.FPS, 'max_images': 1 if i2v else 0,
                'accepted_attachment_kinds': ['image'] if i2v else [],
                'continuation': 'last_frame' if i2v else 'independent',
                'duration': {'configurable': long_form, 'default_seconds': policy.default_seconds,
                             'maximum_seconds': policy.max_seconds if long_form else round(native, 4),
                             'minimum_seconds': durations.MIN_SECONDS if long_form else round(native, 4),
                             'long_video_warning_seconds': policy.warning_seconds, 'presets': list(durations.PRESETS),
                             'setting': policy.public()['setting']}}

    def _video_stats(self):
        from ..storage.json_store import JsonStore
        return JsonStore(self.media.root / 'video-stats.json')

    def video_plan(self, text='', duration=None, images=0):
        """Resolve and plan a VIDEO request for the composer: target, segments and a
        measured estimate. Pure planning; nothing starts."""
        policy = self.video_policy()
        result = {'policy': policy.public(), 'capability': self.video_capability(), 'error': None, 'message': ''}
        try:
            resolved = durations.resolve(duration, text or '', policy)
            plan = durations.plan(resolved.seconds, image=images > 0, continuation=self.image_to_video_ready())
        except durations.DurationError as error:
            message = MediaError(error.code, limit=durations.label(policy.max_seconds)).args[0]
            result.update(error=error.code, message=message, requested_seconds=error.seconds)
            return result
        samples = self._video_stats().read({}).get('segment_seconds', [])
        spread = durations.estimate(plan.segment_count, samples)
        result.update(target_seconds=resolved.seconds, source=resolved.source, prompt_seconds=resolved.prompt_seconds,
                      conflict=resolved.conflict, label=durations.label(resolved.seconds), segments=plan.segment_count,
                      long=resolved.seconds >= policy.warning_seconds, native_segment_seconds=round(plan.native_seconds, 4),
                      estimate_seconds=[round(spread[0]), round(spread[1])] if spread else None)
        return result

    def _plan_video(self, request, text, images, options):
        policy = self.video_policy()
        i2v = self.image_to_video_ready()
        if len(images) > 1:
            raise MediaError('video_one_image')
        if images and not i2v:
            raise MediaError('video_image_unsupported')
        options = options or {}
        try:
            resolved = durations.resolve(options.get('target_duration_seconds'), text, policy)
            if options.get('duration_source') == 'prompt' and not resolved.conflict and resolved.prompt_seconds is not None:
                # OLIVE Mobile resolved Auto from the prompt with the same parser; record it as such.
                resolved = durations.Resolution(resolved.seconds, 'prompt', resolved.prompt_seconds, resolved.prompt_span)
            plan = durations.plan(resolved.seconds, image=bool(images), continuation=i2v)
        except durations.DurationError as error:
            raise MediaError(error.code, str(error.seconds), limit=durations.label(policy.max_seconds)) from None
        if not plan.direct and not assembly.tools():
            raise MediaError('video_assembly_unavailable')
        # Conservative temporary storage: every segment, the stitched file and slack.
        rate = max(self._video_stats().read({}).get('bytes_per_second', []) or [1_000_000])
        needed = int(rate * plan.native_seconds * plan.segment_count * 2.5) + 512 * 1024 * 1024
        try:
            self.media.root.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(self.media.root).free
        except OSError:
            free = needed
        if free < needed:
            raise MediaError('video_storage_full', f'free {free} < needed {needed}')
        generation = durations.strip_duration(text, resolved.prompt_span) if resolved.source == 'prompt' else text
        request.update(plan=plan, target_duration_seconds=resolved.seconds, duration_source=resolved.source,
                       prompt_duration_seconds=resolved.prompt_seconds, duration_conflict=resolved.conflict,
                       generation_prompt=generation)

    def plan(self, chat, text, images, options=None):
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
        if kind == 'video':
            self._plan_video(request, text, images, options)
        elif len(images) > 1:
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
    async def generate(self, chat_id, request, cancel, on_progress=None):
        def progress(text, detail=None):
            if on_progress is not None:
                on_progress(text, detail)  # Remote Chat: factual status for the requesting phone.
            if self.progress.get(chat_id) != text:
                self.progress[chat_id] = text
                if chat_id in self.s.chats:  # A remote request has no desktop conversation.
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
                    if kind == 'video':
                        return await self._video(request, cancel, progress)
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
            engine.touch()  # An OLIVE-started engine stops after the idle period (media_engines).
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
        raise MediaError('workflow_missing', 'video requests use _video')

    # ------------------------------------------------------------------ video
    def _comfy_file(self, engine, folder, name):
        """A file OLIVE itself put in (or received from) its engine, by exact job name."""
        if not engine.runtime.root or not assembly.JOB_ID.fullmatch(name[:32]) or '/' in name or '\\' in name:
            return None
        base = Path(engine.runtime.root, *folder).resolve()
        path = (base / name).resolve()
        return path if path.parent == base else None

    def _forget_engine_files(self, engine, uploads, outputs):
        """Uploaded frames and segment outputs are this job's own copies; the
        published artifact and the job manifest keep what matters."""
        for folder, names in ((('input',), uploads), (('output', 'OLIVE'), outputs)):
            for name in names:
                path = self._comfy_file(engine, folder, name)
                try:
                    if path is not None and path.is_file():
                        path.unlink()
                except OSError:
                    log.warning('Could not remove engine file for a finished video job')

    def _record_stats(self, seconds, rate):
        store = self._video_stats()
        stats = store.read({})
        stats['segment_seconds'] = (stats.get('segment_seconds', []) + [round(seconds, 1)])[-20:]
        if rate:
            stats['bytes_per_second'] = (stats.get('bytes_per_second', []) + [int(rate)])[-20:]
        store.write(stats)

    async def _video(self, request, cancel, progress):
        """Long-form VIDEO: bounded native LTX segments, continued from each
        segment's last frame, stitched and trimmed to the target, verified, then
        published as one artifact. Stop at any stage publishes nothing."""
        engine = self.engines.video
        await self._take_gpu(engine, progress)
        inventory = await engine.prepare(progress)
        plan = request['plan']
        references = request['references']
        workflow, shape, reasons = route('video', request['prompt'], references, inventory)
        if not workflow:
            log.info('No video workflow routable: %s', reasons)
            missing = any(str(v).startswith('model missing') for v in reasons.values())
            raise MediaError('model_missing' if missing else 'workflow_missing', str(reasons))
        continued = None
        if plan.continuation == 'last_frame':
            continued, _, why = route('video', '', [('frame', b'')], inventory)
            if continued is None:
                raise MediaError('workflow_missing', 'continuation: ' + str(why))
        job = secrets.token_hex(16)
        workspace = assembly.JobWorkspace(self.media.root / 'jobs', job).create()
        prompt = request.get('generation_prompt') or request['prompt']
        uploads, outputs, segments, parts = [], [], [], []
        source_ids, source_hash, size = [], None, None
        started = time.monotonic()
        audio = True  # The validated LTX graph always renders synchronized sound.
        manifest = {'job': job, 'target_duration_seconds': plan.target_seconds, 'plan': plan.public(), 'segments': segments}

        def save_manifest():
            workspace.file('manifest.json').write_text(json.dumps(manifest, default=str), encoding='utf-8')
        try:
            save_manifest()
            image = None
            if references:
                name, raw = references[0]
                original = self.media.preserve_bytes(name, raw)  # The frozen source stays intact.
                source_ids.append(original['id'])
                source_hash = hashlib.sha256(raw).hexdigest()
                with Image.open(io.BytesIO(raw)) as picture:
                    picture = ImageOps.exif_transpose(picture).convert('RGB')
                    orientation, size = video_size(*picture.size)
                    picture.thumbnail((1536, 1536))  # The node resizes/crops again to the latent size.
                    buffer = io.BytesIO()
                    picture.save(buffer, format='PNG')
                image = await engine.client.upload(job + '-reference.png', buffer.getvalue())
                uploads.append(image)
            else:
                orientation, size = video_size()
            width, height = size[0] * 2, size[1] * 2   # After the workflow's fixed x2 latent upscale.
            count = plan.segment_count
            engine.active = True
            for segment in plan.segments:
                if cancel.is_set():
                    raise asyncio.CancelledError()
                detail = {'stage': 'segment', 'current': segment.index, 'total': count}
                progress(f'Generating segment {segment.index} of {count}…' if count > 1 else 'Generating video…', detail)
                seed = secrets.randbelow(2 ** 48)  # A fresh seed per segment, each recorded.
                if segment.source == 'continuation':
                    use, condition = continued, image          # Previous segment's last frame.
                elif segment.index == 1:
                    use, condition = workflow, image           # The attached image, or none (text).
                else:
                    use, condition = workflow, None            # Independent text segment.
                graph = video_graph(use, prompt, seed, f'OLIVE/{job}-s{segment.index:03d}', segment.frames,
                                    image=condition, size=size)
                began = time.monotonic()
                label = f'Generating segment {segment.index} of {count}…' if count > 1 else 'Generating video…'
                try:
                    data, filename, prompt_id = await engine.client.run(
                        graph, job, cancel, lambda text, label=label, detail=detail: progress(
                            text if text.startswith('Waiting') else label, detail),
                        kind='video', timeout=self.TIMEOUTS['video'])
                except RuntimeError as error:
                    code = {'workflow_rejected': 'workflow_missing', 'engine_busy': 'engine_busy'}.get(str(error), 'generation_failed')
                    raise MediaError(code, str(error)) from None
                except TimeoutError:
                    raise MediaError('timeout') from None
                outputs.append(filename)
                seconds = time.monotonic() - began
                path = workspace.file('segments', f'{segment.index:04d}.mp4')
                with path.open('xb') as stream:
                    stream.write(data)
                info = await assembly.probe(path, workspace, count_frames=True, cancel=cancel) if assembly.tools() else {}
                if info:
                    assembly.check_segment(info, width=width, height=height, fps=plan.fps, frames=segment.frames, audio=audio)
                record = {'index': segment.index, 'source': segment.source, 'seed': seed, 'prompt_id': prompt_id,
                          'workflow': use.key, 'seconds': round(seconds, 1), 'bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest(), 'frames': info.get('frames'),
                          'keep_start': segment.keep_start, 'keep_frames': segment.keep_frames,
                          'conditioning_image': condition}
                segments.append(record)
                parts.append((path, segment.keep_start, segment.keep_frames))
                self._record_stats(seconds, len(data) / plan.native_seconds)
                save_manifest()
                if segment.index < count and plan.continuation == 'last_frame':
                    if cancel.is_set():
                        raise asyncio.CancelledError()
                    progress('Extracting continuation frame…', {'stage': 'continuation', 'current': segment.index, 'total': count})
                    frame_path = workspace.file('continuation', f'{segment.index:04d}.png')
                    png = await assembly.last_frame(path, info.get('frames') or segment.frames, frame_path, workspace, cancel=cancel)
                    image = await engine.client.upload(f'{job}-c{segment.index:03d}.png', png)
                    uploads.append(image)
                    record['continuation_frame'] = {'sha256': hashlib.sha256(png).hexdigest(), 'upload': image}
            engine.active = False
            # Continuity evidence: segment N's last frame vs segment N+1's first rendered frame.
            for before, after, (path, _, _) in zip(segments, segments[1:], parts[1:]):
                if before.get('continuation_frame'):
                    first = await assembly.first_frame(path, workspace.file('continuation', f'first-{after["index"]:04d}.png'),
                                                       workspace, cancel=cancel)
                    last = workspace.file('continuation', f'{before["index"]:04d}.png').read_bytes()
                    after['conditioned_on'] = before['continuation_frame']['sha256']
                    after['boundary_psnr_db'] = assembly.similarity(last, first)
            if cancel.is_set():
                raise asyncio.CancelledError()
            if plan.direct:
                final = parts[0][0]
                command = None
            else:
                final = workspace.file('final.tmp.mp4')
                progress(f'Stitching {count} segments…' if count > 1 else 'Encoding final video…',
                         {'stage': 'stitching' if count > 1 else 'encoding', 'current': count, 'total': count})
                command = await assembly.stitch(parts, final, plan, workspace, audio=audio, cancel=cancel)
            progress('Verifying output…', {'stage': 'verifying', 'current': count, 'total': count})
            verified = {}
            if assembly.tools():
                verified = await assembly.probe(final, workspace, count_frames=True, cancel=cancel)
                if plan.direct:
                    assembly.check_segment(verified, width=width, height=height, fps=plan.fps, frames=plan.native_frames, audio=audio)
                else:
                    assembly.check_final(verified, plan, width=width, height=height, audio=audio)
            digest, _ = assembly.file_digest(final)
            if cancel.is_set():
                raise asyncio.CancelledError()  # Stop wins: nothing late is published.
            progress('Saving video…', {'stage': 'saving', 'current': count, 'total': count})
            d = workflow.defaults
            # Only measured facts: without ffprobe the actual duration and audio are not claimed.
            extra = {'width': verified.get('width', width), 'height': verified.get('height', height), 'fps': plan.fps,
                     'target_duration_seconds': plan.target_seconds, 'segment_count': count,
                     'generation_mode': plan.mode, 'continuation': plan.continuation}
            if verified.get('duration'):
                extra.update(duration_seconds=round(verified['duration'], 3), has_audio=bool(verified.get('audio_streams')))
            elapsed = round(time.monotonic() - started, 1)
            if command:
                command = [part.replace(str(workspace.path), '<job>') for part in command[5:]]
            manifest.update(stitch=command, verified=verified, seconds=elapsed)
            return self.media.save_generated_file(
                final, mode=request['mode'], source_ids=source_ids, sha256=digest,
                generator={'provider': 'ComfyUI', 'family': workflow.label, 'workflow': workflow.key,
                           'engine_version': inventory['version']},
                parameters={'prompt': request['prompt'], 'generation_prompt': prompt, 'seed': segments[0]['seed'],
                            'width': size[0], 'height': size[1], 'orientation': orientation,
                            'frames': plan.native_frames if plan.direct else plan.total_frames,
                            'fps': plan.fps, 'steps': d['steps'], 'cfg': d['cfg'], 'sampler': d['sampler'],
                            'schedule': d['schedule'], 'upscale': 'latent x2', 'operation': 'animate' if references else 'generate',
                            'target_duration_seconds': plan.target_seconds, 'duration_source': request.get('duration_source'),
                            'prompt_duration_seconds': request.get('prompt_duration_seconds'),
                            'segments': count, 'native_segment_frames': plan.native_frames},
                extra=extra,
                provenance={'engine': 'ComfyUI', 'version': inventory['version'], 'workflow': workflow.key,
                            'continuation_workflow': continued.key if continued else None, 'route': shape,
                            'files': sorted(workflow.files.values()), 'source_image_sha256': source_hash,
                            'segments': segments, 'plan': plan.public(), 'stitch': manifest['stitch'],
                            'ffprobe': verified, 'seconds': elapsed, 'prompt_id': segments[0]['prompt_id']})
        finally:
            engine.active = False
            try:
                await engine.client.release_idle()
            except Exception as error:
                # The next text or media request re-verifies before loading anything.
                log.warning('video engine release after generation not verified: %s', error)
            self._forget_engine_files(engine, uploads, outputs)
            workspace.remove()


def created_now():
    return datetime.now().isoformat(timespec='seconds')
