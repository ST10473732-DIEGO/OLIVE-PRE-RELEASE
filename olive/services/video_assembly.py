"""Long-form OLIVE VIDEO assembly with the locally installed FFmpeg.

Only OLIVE-owned files inside one private job directory are ever read or
written. Every command is an argument list (never a shell string), inputs are
restricted to the local file protocol with an explicit container format, and
user text never reaches a command line. Nothing here installs FFmpeg; when it
is missing, multi-segment VIDEO reports that truthfully instead.
"""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from .media_errors import MediaError

JOB_ID = re.compile(r'[0-9a-f]{32}')
_TIMEOUT_PROBE = 60


def tools():
    """(ffmpeg, ffprobe) executables already on this computer, or None."""
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    return (ffmpeg, ffprobe) if ffmpeg and ffprobe else None


class JobWorkspace:
    """media/jobs/<job-id>/ with segments/, continuation/ and final.tmp.mp4.

    The directory name is OLIVE's own random job id; no peer or prompt text
    contributes to any path. Removed on success, cancel and known failure.
    """

    def __init__(self, root, job):
        if not JOB_ID.fullmatch(job):
            raise ValueError('invalid job id')
        self.root = Path(root).resolve()
        self.path = self.root / job
        self.job = job

    def create(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.mkdir(mode=0o700)
        for name in ('segments', 'continuation'):
            (self.path / name).mkdir(mode=0o700)
        return self

    def file(self, *parts):
        """A path inside this job only; anything that escapes is refused."""
        for part in parts:
            if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', part) or '..' in part:
                raise ValueError('invalid workspace name')
        path = self.path.joinpath(*parts).resolve()
        if not path.is_relative_to(self.path):
            raise ValueError('workspace path escaped')
        return path

    def owns(self, path):
        try:
            return Path(path).resolve().is_relative_to(self.path)
        except (OSError, ValueError):
            return False

    def remove(self):
        if self.path.parent == self.root and JOB_ID.fullmatch(self.path.name) and self.path.is_dir():
            shutil.rmtree(self.path, ignore_errors=True)

    @staticmethod
    def sweep(root):
        """Startup: jobs never survive a restart, so abandoned job folders go.
        Only OLIVE-named (32 hex) directories directly under media/jobs."""
        root = Path(root)
        removed = 0
        if not root.is_dir():
            return removed
        for child in root.iterdir():
            if child.is_dir() and not child.is_symlink() and JOB_ID.fullmatch(child.name):
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        return removed


async def _run(argv, timeout, *, cancel=None):
    """Run one tool; the process is killed on cancel, timeout or error."""
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    waiter = asyncio.ensure_future(process.communicate())
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while not waiter.done():
            if cancel is not None and cancel.is_set():
                raise asyncio.CancelledError()
            left = deadline - asyncio.get_running_loop().time()
            if left <= 0:
                raise TimeoutError('media tool timeout')
            await asyncio.wait({waiter}, timeout=min(.25, left))
        stdout, stderr = waiter.result()
        return process.returncode, stdout, stderr
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
        if not waiter.done():
            waiter.cancel()


def _input(path, workspace):
    if not workspace.owns(path) or not Path(path).is_file():
        raise MediaError('video_assembly_failed', 'input outside the job workspace')
    # file: only, and the container is stated: no protocol URLs, no sniffed formats.
    return ['-protocol_whitelist', 'file', '-f', 'mov', '-i', 'file:' + str(Path(path).resolve())]


def _output(path, workspace):
    if not workspace.owns(path):
        raise MediaError('video_assembly_failed', 'output outside the job workspace')
    return 'file:' + str(Path(path).resolve())


def _fraction(text):
    try:
        top, _, bottom = str(text).partition('/')
        value = float(top) / float(bottom or 1)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


async def probe(path, workspace, *, count_frames=False, cancel=None):
    """Container and stream facts from ffprobe for one OLIVE-owned MP4."""
    found = tools()
    if not found:
        raise MediaError('video_assembly_unavailable')
    argv = [found[1], '-v', 'error', '-protocol_whitelist', 'file', '-f', 'mov']
    if count_frames:
        argv += ['-count_frames']
    argv += ['-show_entries', 'format=format_name,duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,'
             'avg_frame_rate,duration,nb_frames,nb_read_frames,sample_rate,channels,pix_fmt',
             '-of', 'json', _output(path, workspace)]
    code, stdout, stderr = await _run(argv, _TIMEOUT_PROBE, cancel=cancel)
    if code != 0:
        raise MediaError('video_verify_failed', 'ffprobe: ' + stderr.decode('utf-8', 'replace')[-300:])
    try:
        data = json.loads(stdout or b'{}')
    except ValueError:
        raise MediaError('video_verify_failed', 'ffprobe output') from None
    streams = data.get('streams') or []
    video = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    fmt = data.get('format') or {}
    info = {'format': str(fmt.get('format_name', '')), 'video_streams': len(video), 'audio_streams': len(audio)}
    try:
        info['duration'] = float(fmt.get('duration'))
    except (TypeError, ValueError):
        info['duration'] = None
    if video:
        v = video[0]
        info.update(video_codec=v.get('codec_name'), width=v.get('width'), height=v.get('height'),
                    fps=_fraction(v.get('r_frame_rate')) or _fraction(v.get('avg_frame_rate')), pix_fmt=v.get('pix_fmt'))
        frames = v.get('nb_read_frames') if count_frames else v.get('nb_frames')
        info['frames'] = int(frames) if str(frames or '').isdigit() else None
        try:
            info['video_duration'] = float(v.get('duration'))
        except (TypeError, ValueError):
            info['video_duration'] = None
    if audio:
        a = audio[0]
        info.update(audio_codec=a.get('codec_name'), sample_rate=int(a['sample_rate']) if str(a.get('sample_rate', '')).isdigit() else None,
                    channels=a.get('channels'))
        try:
            info['audio_duration'] = float(a.get('duration'))
        except (TypeError, ValueError):
            info['audio_duration'] = None
    return info


def check_segment(info, *, width, height, fps, frames, audio):
    """A generated segment must match the planned geometry before it is used."""
    problems = []
    if 'mp4' not in info.get('format', '') and 'mov' not in info.get('format', ''):
        problems.append('not an MP4 container')
    if info.get('video_streams') != 1:
        problems.append('video stream count')
    if (info.get('width'), info.get('height')) != (width, height):
        problems.append(f"dimensions {info.get('width')}x{info.get('height')} != {width}x{height}")
    if not info.get('fps') or abs(info['fps'] - fps) > 0.01:
        problems.append('frame rate')
    if info.get('frames') is not None and info['frames'] < frames:
        problems.append(f"frames {info['frames']} < {frames}")
    if audio and info.get('audio_streams') != 1:
        problems.append('missing audio')
    if problems:
        raise MediaError('video_segment_invalid', '; '.join(problems))


def check_final(info, plan, *, width, height, audio):
    """The published file: one H.264 stream of the planned size, rate and length."""
    problems = []
    fps, frame = plan.fps, 1 / plan.fps
    if 'mp4' not in info.get('format', ''):
        problems.append('container')
    if info.get('video_streams') != 1 or info.get('video_codec') != 'h264':
        problems.append('video stream')
    if (info.get('width'), info.get('height')) != (width, height):
        problems.append('dimensions')
    if not info.get('fps') or abs(info['fps'] - fps) > 0.01:
        problems.append('frame rate')
    duration = info.get('duration')
    if not duration or duration <= 0:
        problems.append('duration')
    elif abs(duration - plan.final_seconds) > frame + 0.03:
        problems.append(f'duration {duration:.4f} vs {plan.final_seconds:.4f}')
    if info.get('frames') is not None and info['frames'] != plan.total_frames:
        problems.append(f"frames {info['frames']} != {plan.total_frames}")
    if audio:
        if info.get('audio_streams') != 1 or info.get('audio_codec') != 'aac':
            problems.append('audio stream')
        elif info.get('audio_duration') and abs(info['audio_duration'] - plan.final_seconds) > frame + 0.03:
            problems.append('audio duration')
    elif info.get('audio_streams'):
        problems.append('unexpected audio')
    if problems:
        raise MediaError('video_verify_failed', '; '.join(problems))


async def last_frame(segment, frames, target, workspace, *, cancel=None):
    """Write the exact last decoded frame of one segment as a PNG."""
    found = tools()
    if not found:
        raise MediaError('video_assembly_unavailable')
    argv = [found[0], '-nostdin', '-hide_banner', '-loglevel', 'error', *_input(segment, workspace),
            '-map', '0:v:0', '-vf', f'select=eq(n\\,{int(frames) - 1})', '-fps_mode', 'passthrough', '-frames:v', '1',
            '-f', 'image2', '-c:v', 'png', '-y', _output(target, workspace)]
    code, _, stderr = await _run(argv, 120, cancel=cancel)
    if code != 0 or not Path(target).is_file() or Path(target).stat().st_size == 0:
        raise MediaError('video_assembly_failed', 'frame extraction: ' + stderr.decode('utf-8', 'replace')[-300:])
    return Path(target).read_bytes()


async def first_frame(segment, target, workspace, *, cancel=None):
    """Diagnostic only: the first decoded frame of a continuation segment."""
    found = tools()
    if not found:
        raise MediaError('video_assembly_unavailable')
    argv = [found[0], '-nostdin', '-hide_banner', '-loglevel', 'error', *_input(segment, workspace),
            '-map', '0:v:0', '-frames:v', '1', '-f', 'image2', '-c:v', 'png', '-y', _output(target, workspace)]
    code, _, stderr = await _run(argv, 120, cancel=cancel)
    if code != 0 or not Path(target).is_file():
        raise MediaError('video_assembly_failed', 'frame extraction: ' + stderr.decode('utf-8', 'replace')[-300:])
    return Path(target).read_bytes()


def stitch_command(ffmpeg, parts, output, plan, workspace, *, audio):
    """One deterministic decode→trim→concat→encode pass.

    parts: [(segment path, keep_start, keep_frames)]. Video keeps exact frame
    ranges; each segment's audio is cut to the same span and padded with
    silence to exactly its video length, so A/V sync cannot drift across
    boundaries. The result is H.264 High/yuv420p + AAC-LC 48 kHz stereo with
    fast-start metadata (AVPlayer and Electron compatible).
    """
    fps = plan.fps
    argv = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error']
    for path, _, _ in parts:
        argv += _input(path, workspace)
    chains, labels = [], []
    for i, (_, start, keep) in enumerate(parts):
        chains.append(f'[{i}:v:0]trim=start_frame={start}:end_frame={start + keep},setpts=PTS-STARTPTS,'
                      f'fps={fps},format=yuv420p[v{i}]')
        labels.append(f'[v{i}]')
        if audio:
            begin, span = start / fps, keep / fps
            chains.append(f'[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,atrim=start={begin:.6f},'
                          f'asetpts=PTS-STARTPTS,apad=whole_dur={span:.6f},atrim=end={span:.6f},asetpts=N/SR/TB[a{i}]')
            labels.append(f'[a{i}]')
    chains.append(''.join(labels) + f'concat=n={len(parts)}:v=1:a={1 if audio else 0}' + ('[v][a]' if audio else '[v]'))
    argv += ['-filter_complex', ';'.join(chains), '-map', '[v]']
    if audio:
        argv += ['-map', '[a]']
    argv += ['-frames:v', str(plan.total_frames), '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-profile:v', 'high',
             '-pix_fmt', 'yuv420p', '-r', str(fps), '-fps_mode', 'cfr']
    if audio:
        argv += ['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-t', f'{plan.final_seconds:.6f}']
    argv += ['-movflags', '+faststart', '-map_metadata', '-1', '-f', 'mp4', '-y', _output(output, workspace)]
    return argv


async def stitch(parts, output, plan, workspace, *, audio, cancel=None):
    found = tools()
    if not found:
        raise MediaError('video_assembly_unavailable')
    argv = stitch_command(found[0], parts, output, plan, workspace, audio=audio)
    code, _, stderr = await _run(argv, 120 + 20 * len(parts), cancel=cancel)
    if code != 0 or not Path(output).is_file() or Path(output).stat().st_size == 0:
        raise MediaError('video_assembly_failed', 'ffmpeg: ' + stderr.decode('utf-8', 'replace')[-400:])
    return argv


def file_digest(path):
    digest, size = hashlib.sha256(), 0
    with open(path, 'rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def similarity(a_png, b_png):
    """PSNR (dB) between two boundary frames: diagnostic evidence, not a claim of seamlessness."""
    import io
    from PIL import Image, ImageChops, ImageStat
    with Image.open(io.BytesIO(a_png)) as a, Image.open(io.BytesIO(b_png)) as b:
        a, b = a.convert('RGB'), b.convert('RGB').resize(a.size)
        stat = ImageStat.Stat(ImageChops.difference(a, b))
        mse = sum(v ** 2 for v in stat.rms) / 3
    return round(99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse), 2)
