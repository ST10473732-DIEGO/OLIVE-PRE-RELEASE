"""TEST ONLY: a deterministic stand-in for the desktop Remote Chat runtime.

It implements the same interface as ``olive.services.remote_chat_runtime.RemoteChatRuntime``
(capabilities / validate / run / artifact_file) so the production Connect service,
protocol, staging and receipts are exercised end to end, while every mode answers
from fixed rules instead of models: no Ollama, ComfyUI, VoiceStudio or network.

Results produced here never count as real-model verification.
"""
import asyncio
import hashlib
import io
import math
import re
import struct
import uuid
import wave
from pathlib import Path

from olive.connect.chat_protocol import MAX_BYTES, MIMES, video_options
from olive.connect.contracts import ConnectError
from olive.services.remote_chat_runtime import RemoteChatRuntime


class TestError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def png(width, height, pixel):
    from PIL import Image
    image = Image.new('RGB', (width, height))
    image.putdata([pixel(x, y) for y in range(height) for x in range(width)])
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def wav(seconds=1.5, rate=22050, tone=440.0):
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b''.join(struct.pack('<h', int(12000 * math.sin(2 * math.pi * tone * i / rate)))
                               for i in range(int(seconds * rate))))
    return out.getvalue()


def fake_mp4():
    """Container-shaped bytes for unit tests only (not playable)."""
    return struct.pack('>I', 24) + b'ftypisom' + b'\0\0\x02\0isomiso2' + struct.pack('>I', 8) + b'free'


def document_text(path):
    path = Path(path)
    if path.suffix == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return [(i + 1, page.extract_text() or '') for i, page in enumerate(pdf.pages)]
        except Exception:
            raise TestError('document_unreadable') from None
    return [(None, path.read_text('utf-8'))]


class ChatTestRuntime:
    """Every mode available unless ``unavailable`` names it."""
    validate = RemoteChatRuntime.validate

    def __init__(self, root, *, unavailable=(), video=None, image_edit=True, delay=0.02, animate=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.unavailable = set(unavailable)
        self.video = video or fake_mp4
        self.image_edit = image_edit
        self.animate = animate   # A computer with validated VIDEO image-to-video and long-form assembly.
        self.delay = delay
        self.slow_seconds = 8    # How long a request whose prompt says "slow" keeps working.
        self.files = {}
        self.runs = []          # (job_id, mode, attachment kinds) for assertions
        self.received = []      # attachment snapshots the "desktop" consumed
        self.voice_list = [dict(id='default', name='Test voice'), dict(id='calm', name='Calm test voice')]

    def _modes(self):
        def mode(key, *, image=0, document=0, note=0, outputs=('text',), citations=False, prompt=False,
                 limitations=(), voices=()):
            available = key not in self.unavailable
            return dict(id=key, available=available, reason='' if available else 'needs_setup',
                        inputs=dict(image=dict(max=image, max_bytes=MAX_BYTES['image'], mimes=list(MIMES['image'])),
                                    document=dict(max=document, max_bytes=MAX_BYTES['document'],
                                                  mimes=list(MIMES['document'][:4])),
                                    note=dict(max=note, max_bytes=MAX_BYTES['note'])),
                        outputs=list(outputs), citations=citations, stream=outputs == ('text',), cancel=True,
                        prompt_required=prompt, tiers=[], voices=list(voices), limitations=list(limitations))
        modes_list = [mode('fast', note=2), mode('normal', image=4, note=2), mode('max', image=4, note=2),
                mode('uncensored', note=2, limitations=('automatic_tier',)),
                mode('now', citations=True, limitations=('public_web_only',)),
                mode('deep', document=4, note=2, image=3, citations=True),
                mode('reimagine', image=1 if self.image_edit else 0, outputs=('image',), prompt=True,
                     limitations=('one_reference_image',) if self.image_edit else ('text_only',)),
                mode('audio', outputs=('audio',), prompt=True, limitations=('speech_only',), voices=self.voice_list),
                mode('video', image=1 if self.animate else 0, outputs=('video',), prompt=True,
                     limitations=('one_start_image', 'video_with_audio', 'long_video') if self.animate
                     else ('text_only', 'video_with_audio'))]
        return modes_list

    def capabilities(self, extended=False):
        modes = self._modes()
        if extended:
            for entry in modes:
                entry['options'] = video_options(self.video_capability()) if entry['id'] == 'video' else {}
        return modes

    def video_capability(self):
        return {'supports_text_to_video': True, 'supports_image_to_video': self.animate, 'supports_audio': True,
                'native_segment_seconds': 49 / 24, 'fps': 24, 'max_images': 1 if self.animate else 0,
                'accepted_attachment_kinds': ['image'] if self.animate else [],
                'continuation': 'last_frame' if self.animate else 'independent',
                'duration': {'configurable': self.animate, 'default_seconds': 2.0, 'minimum_seconds': 0.5,
                             'maximum_seconds': 180.0 if self.animate else 49 / 24, 'long_video_warning_seconds': 30.0,
                             'presets': [2, 5, 10, 20, 30, 60]}}

    # ------------------------------------------------------------ helpers
    async def _pause(self, sink, seconds):
        steps = max(1, int(seconds / 0.05))
        for _ in range(steps):
            if sink.cancelled is not None and sink.cancelled.is_set():
                raise asyncio.CancelledError()
            await asyncio.sleep(seconds / steps)

    async def _stream(self, sink, text, slow):
        parts = [text[i:i + 12] for i in range(0, len(text), 12)] or [text]
        for part in parts:
            await self._pause(sink, 0.4 if slow else self.delay)
            sink.text(part)

    def _save(self, kind, data, mime, extension, mode, **extra):
        identity = uuid.uuid4().hex
        path = self.root / (identity + extension)
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        self.files[identity] = dict(path=str(path), size=len(data), sha256=digest)
        return {'id': identity, 'kind': kind, 'mime_type': mime, 'size_bytes': len(data), 'sha256': digest,
                'mode': mode, 'generator': {'family': 'Test Host ' + kind.title()}, 'completion_state': 'complete', **extra}

    def artifact_file(self, artifact_id):
        if artifact_id not in self.files:
            raise ConnectError('artifact_unavailable')
        return dict(self.files[artifact_id])

    # ------------------------------------------------------------ run
    async def run(self, job, sink):
        user = job.arguments['messages'][-1]['content']
        kinds = [inp['ref']['kind'] for inp in job.inputs]
        self.runs.append((job.job_id, job.mode, kinds))
        for inp in job.inputs:
            self.received.append(dict(ref=inp['ref'], sha256=hashlib.sha256(Path(inp['path']).read_bytes()).hexdigest()))
        slow = 'slow' in user.lower()
        if 'fail' in user.lower():
            raise TestError('inference_failed')
        exact = re.search(r'Reply with exactly:\s*(\S+)', user)
        if job.mode in ('fast', 'normal', 'max', 'uncensored'):
            sink.phase('thinking')
            tier = ''
            if job.mode == 'uncensored':
                tier = 'CREATIVE' if re.search(r'\b(story|poem|creative)\b', user, re.I) else 'FAST'
            sink.attribute(tier)
            parts = [exact.group(1) if exact else f'{job.mode.upper()} test host reply: {user[:80]}']
            for inp in job.inputs:
                if inp['ref']['kind'] == 'note':
                    body = Path(inp['path']).read_text('utf-8').strip().splitlines()
                    parts.append(f"Note “{inp['ref']['name']}” received ({len(body)} lines): " + (body[-1][:120] if body else ''))
                if inp['ref']['kind'] == 'image':
                    from PIL import Image
                    with Image.open(inp['path']) as image:
                        colours = sorted({name for name, rgb in (('red', (255, 0, 0)), ('green', (0, 160, 0)), ('blue', (0, 0, 255)))
                                          if any(all(abs(a - b) < 80 for a, b in zip(px[:3], rgb))
                                                 for px in image.convert('RGB').resize((32, 32)).getdata())})
                        parts.append(f'Image received: {image.width}x{image.height}; colours: ' + (', '.join(colours) or 'none'))
            return await self._stream(sink, '\n\n'.join(parts), slow)
        if job.mode == 'now':
            sink.phase('retrieving')
            await self._pause(sink, self.delay)
            if 'offline' in user.lower():
                raise TestError('search_unavailable')
            sources = [
                dict(id='S1', kind='page_excerpt', title='Synthetic weather bulletin', source='example.org',
                     url='https://example.org/weather', published_at='2026-09-30T08:00:00+00:00', updated_at=None,
                     retrieved_at='2026-09-30T09:00:00+00:00', evidence='Synthetic bulletin text.'),
                dict(id='S2', kind='current_snapshot', title='Synthetic status page', source='example.com',
                     url='https://example.com/status', published_at=None, updated_at=None,
                     retrieved_at='2026-09-30T09:00:01+00:00', evidence='Synthetic snapshot.'),
            ]
            sink.phase('synthesizing')
            await self._stream(sink, 'Based on public sources retrieved 2026-09-30T09:00:00+00:00.\n\n'
                               'The synthetic bulletin reports mild weather [S1]; the status page shows normal service [S2].', slow)
            sink.sources(sources)
            sink.attribute('LIVE')
            return
        if job.mode == 'deep':
            sink.phase('indexing')
            await self._pause(sink, self.delay)
            sources, found = [], []
            words = [w for w in re.findall(r'[A-Za-z]{5,}', user)]
            for inp in job.inputs:
                if inp['ref']['kind'] == 'image':
                    sources.append(dict(id=f'D{len(sources) + 1}', kind='document_excerpt', title='Image: ' + inp['ref']['name'],
                                        filename=inp['ref']['name'], evidence='Image interpreted by the test host.'))
                    continue
                for page, text in document_text(inp['path']):
                    for sentence in re.split(r'(?<=[.!?])\s+|\n', text):
                        if sentence.strip() and (re.search(r'unique|secret|phrase', sentence, re.I)
                                                 or any(w.lower() in sentence.lower() for w in words)):
                            sid = f'D{len(sources) + 1}'
                            sources.append(dict(id=sid, kind='document_excerpt', filename=inp['ref']['name'],
                                                title=inp['ref']['name'] + (f' — page {page}' if page else ''),
                                                page_number=page, evidence=sentence.strip()))
                            found.append((sid, sentence.strip()))
                            break
            sink.phase('synthesizing')
            if found:
                text = ' '.join(f'{s} [{sid}]' for sid, s in found[:3])
            elif sources:
                text = 'The attached image was read by the test host [D1].'
            else:
                text = 'I could not find evidence for that question in the attached document index.'
            await self._stream(sink, text, slow)
            sink.sources(sources)
            sink.attribute('RESEARCH')
            return
        # Media.
        kind = {'reimagine': 'image', 'audio': 'audio', 'video': 'video'}[job.mode]
        sink.phase({'image': 'preparing_image_engine', 'audio': 'preparing_audio_engine', 'video': 'preparing_video_engine'}[kind])
        await self._pause(sink, 0.2)
        sink.phase({'image': 'generating_image', 'audio': 'generating_speech', 'video': 'generating_video'}[kind])
        target = ((job.arguments.get('options') or {}).get('target_duration_ms') or 2000) / 1000
        if kind == 'video' and self.animate:
            segments = max(1, -(-round(target * 24 - 1) // 48))
            for index in range(1, segments + 1):
                sink.phase('generating_video', {'stage': 'segment', 'current': index, 'total': segments})
                await self._pause(sink, (self.slow_seconds if slow else 0.3) / segments)
            sink.phase('saving', {'stage': 'stitching', 'current': segments, 'total': segments})
        else:
            await self._pause(sink, self.slow_seconds if slow else 0.3)
        if kind == 'image':
            references = [inp for inp in job.inputs if inp['ref']['kind'] == 'image']
            if references:
                from PIL import Image, ImageOps
                with Image.open(references[0]['path']) as source:
                    edited = ImageOps.invert(source.convert('RGB'))
                    out = io.BytesIO(); edited.save(out, format='PNG'); data = out.getvalue()
                    width, height = edited.size
            else:
                width = height = 256
                data = png(width, height, lambda x, y: (30, 90, 230) if 64 <= x < 192 and 64 <= y < 192 else (255, 255, 255))
            artifact = self._save('image', data, 'image/png', '.png', job.mode, width=width, height=height,
                                  source_ids=['0' * 32] if references else [])
        elif kind == 'audio':
            data = wav()
            artifact = self._save('audio', data, 'audio/wav', '.wav', job.mode, duration_seconds=1.5)
        else:
            data = self.video() if callable(self.video) else Path(self.video).read_bytes()
            images = [inp for inp in job.inputs if inp['ref']['kind'] == 'image']
            artifact = self._save('video', data, 'video/mp4', '.mp4', job.mode, width=320, height=240,
                                  duration_seconds=target, has_audio=True, source_ids=['0' * 32] if images else [])
        sink.phase('saving')
        sink.attribute({'image': 'IMAGE', 'audio': 'SPEECH', 'video': 'VIDEO'}[kind])
        sink.text({'image': 'Image generated on your computer.', 'audio': 'Speech generated on your computer.',
                   'video': 'Video generated on your computer.'}[kind])
        sink.artifact(artifact)
