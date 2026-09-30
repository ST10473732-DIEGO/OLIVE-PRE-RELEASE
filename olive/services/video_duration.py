"""OLIVE VIDEO target duration: deterministic parsing, resource policy and the
long-form segment planner.

The LTX engine renders one short native segment per graph (49 frames at
24 fps, about 2.04 s). A product duration is built from bounded sequential
segments: segment 1 is text- or image-to-video, each later segment is
image-to-video from the previous segment's last frame, and the stitched result
is trimmed to the requested frame count. Nothing here runs a model, reads a
file or calls an LLM; every function is pure so desktop Chat and OLIVE Mobile
share one planner.
"""
from dataclasses import dataclass
import math
import re

FPS = 24
NATIVE_FRAMES = 49             # The validated LTX 2.3 segment (8k+1 frames).
MIN_SECONDS = 0.5
# Technical ceilings that configuration cannot raise: they only stop an
# accidental absurd request (hours, overflow, thousands of segments).
HARD_MAX_SECONDS = 3600.0
HARD_MAX_SEGMENTS = 2000
DEFAULTS = {'default_duration_seconds': 2.0, 'long_video_warning_seconds': 30.0, 'max_duration_seconds': 180.0}
SETTINGS_KEY = 'media_video'
PRESETS = (2, 5, 10, 20, 30, 60)

_WORDS = {
    'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
    'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40,
    'forty-five': 45, 'fifty': 50, 'sixty': 60, 'ninety': 90,
}
_NUM = r'(?:\d{1,6}(?:\.\d{1,3})?|' + '|'.join(sorted((re.escape(w) for w in _WORDS), key=len, reverse=True)) + r')'
_UNIT = r'(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|h|m|s)'
# One part is "20 seconds", "20-second", "1m" or "a minute"; parts chain as "1 minute 30 seconds".
_PART = rf'{_NUM}(?:\s*-\s*|\s*){_UNIT}(?![a-z])'
_HALF = r'half(?:\s+an?|\s*-)?\s*(?:minute|hour)(?![a-z])'
_DURATION = rf'(?:{_HALF}|{_PART}(?:\s*(?:,|and)?\s*{_PART})*(?:\s+and\s+a\s+half)?)'
_CLOCK = r'(?<![\d:.])(\d{1,2}):([0-5]\d)(?::([0-5]\d))?(?![\d:])'
_NOUNS = r'(?:video|clip|scene|shot|animation|movie|film|sequence|timelapse|time-lapse|loop|footage|cinematic)'
# Strong contexts only: a duration word elsewhere ("the ball drops after 3
# seconds") describes the scene, not the clip, and is left alone.
_STRONG = (
    # "20 second video", "a 20-second cinematic scene", "1 minute long clip"
    re.compile(rf'(?P<d>{_DURATION})(?:\s*-?\s*long)?(?=\s+(?:[a-z-]+\s+){{0,3}}{_NOUNS}\b)', re.I),
    # "for 20 seconds", "lasting 1 minute", "duration: 20s"
    re.compile(rf'(?P<lead>\b(?:for|lasting|lasts|duration(?:\s+of)?|length(?:\s+of)?|runtime|total\s+of)\s*:?\s*)(?P<d>{_DURATION})', re.I),
    # "20 seconds long", "20 seconds of waves"
    re.compile(rf'(?P<d>{_DURATION})(?P<tail>\s+(?:long\b|of\s+))', re.I),
    # A duration clause on its own: "Waves, 20 sec." / "(20s)" / "20 seconds: waves"
    re.compile(rf'(?:^|(?<=[,;:(\[]))\s*(?P<d>{_DURATION})\s*(?=$|[,;:.!)\]])', re.I),
)
_CLOCK_RE = re.compile(_CLOCK)
_CLOCK_EXCLUDED = re.compile(r'\b(?:at|by|until|till|from|to|before|after|around)\s*$', re.I)
_CLOCK_SUFFIX = re.compile(r"^\s*(?:a\.?m\.?|p\.?m\.?|o'?clock|h\b|hrs?\b|hours?\b)", re.I)


def _number(token):
    token = token.lower()
    return float(_WORDS[token]) if token in _WORDS else float(token)


def _seconds(expression):
    """Seconds described by one matched duration expression, or None."""
    text = expression.lower().strip()
    half = re.fullmatch(r'half(?:\s+an?|\s*-)?\s*(minute|hour)', text)
    if half:
        return 30.0 if half.group(1) == 'minute' else 1800.0
    total, last_unit = 0.0, None
    for number, unit in re.findall(rf'({_NUM})(?:\s*-\s*|\s*)({_UNIT})(?![a-z])', text):
        scale = 3600.0 if unit[0] == 'h' else 60.0 if unit[0] == 'm' else 1.0
        total += _number(number) * scale
        last_unit = scale
    if last_unit is None:
        return None
    if re.search(r'and\s+a\s+half$', text):
        total += last_unit / 2
    return total


def _bare_s_ok(text, start, end, expression):
    """A bare "20s" is often a decade or an age ("in her 20s"). It only counts
    in the strong contexts above and never after possessives or "the"."""
    if not re.fullmatch(r'\s*\d{1,4}s\s*', expression, re.I):
        return True
    return not re.search(r"\b(?:the|her|his|their|my|your|our|in|early|late|mid)\s*$|'$", text[:start], re.I)


def parse_duration(text):
    """(seconds, (start, end)) for the clip duration stated in a prompt, else (None, None).

    Deterministic and conservative: phrases such as "20 second video",
    "20-second video", "for 20 seconds", "20 sec", "20s video", "half a
    minute", "1 minute 30 seconds", "90 seconds", "2 minutes", "0:20" and
    "01:30". The first strong match wins.
    """
    value = text or ''
    found = []
    for pattern in _STRONG:
        for match in pattern.finditer(value):
            start, end = match.span('d')
            expression = match.group('d')
            if not _bare_s_ok(value, start, end, expression):
                continue
            seconds = _seconds(expression)
            if seconds:
                span = (match.start(), match.end()) if 'lead' in pattern.groupindex or 'tail' in pattern.groupindex else (start, end)
                found.append((start, seconds, span))
    for match in _CLOCK_RE.finditer(value):
        if _CLOCK_EXCLUDED.search(value[:match.start()]) or _CLOCK_SUFFIX.match(value[match.end():]):
            continue
        a, b, c = match.groups()
        seconds = (int(a) * 3600 + int(b) * 60 + int(c)) if c else int(a) * 60 + int(b)
        if seconds:
            found.append((match.start(), float(seconds), match.span()))
    if not found:
        return None, None
    _, seconds, span = min(found, key=lambda item: item[0])
    return seconds, span


def strip_duration(text, span):
    """The prompt without its purely operational duration words.

    "Generate a 20 second cinematic scene of clouds" -> "Generate a cinematic
    scene of clouds". Only the matched span (and a dangling connective) goes;
    if nothing descriptive would remain the original is kept.
    """
    if not span:
        return text
    start, end = span
    before, after = text[:start], text[end:]
    before = re.sub(r'(?:\s*-\s*|\s+)$', ' ' if after[:1].isalnum() else '', before)
    after = re.sub(r'^\s*-?\s*long\b', '', after, flags=re.I)
    result = before + after.lstrip() if before.endswith(' ') or not before else before + ' ' + after.lstrip()
    result = re.sub(r'\(\s*\)|\[\s*\]', '', result)
    result = re.sub(r'\b([Aa])n? (?=[aeiouAEIOU])', r'\1n ', result)
    result = re.sub(r'\b([Aa])n (?=[^aeiouAEIOU\W])', r'\1 ', result)
    result = re.sub(r'\s+([,.;:!?])', r'\1', re.sub(r'\s{2,}', ' ', result))
    result = re.sub(r'[,;:]+(?=[.!?]|$)', '', result)
    # A connective left dangling at either end ("of forest", "waves for").
    result = re.sub(r'^\s*(?:of|for)\s+|\s+(?:for|of|lasting|duration|length)\s*:?\s*(?=[.!?]?$)', '', result, flags=re.I)
    result = result.strip(' ,;:-')
    return result if re.search(r'[A-Za-z]{3}', result) else text


def _number_setting(values, key):
    value = values.get(key, DEFAULTS[key])
    if type(value) not in (int, float) or not math.isfinite(value):
        return DEFAULTS[key]
    return float(value)


@dataclass(frozen=True)
class VideoPolicy:
    """Configurable limits (settings.json → "media_video"); hard ceilings still apply."""
    default_seconds: float = DEFAULTS['default_duration_seconds']
    warning_seconds: float = DEFAULTS['long_video_warning_seconds']
    max_seconds: float = DEFAULTS['max_duration_seconds']

    @classmethod
    def from_settings(cls, settings):
        values = settings.get(SETTINGS_KEY) if isinstance(settings, dict) else None
        values = values if isinstance(values, dict) else {}
        maximum = min(max(_number_setting(values, 'max_duration_seconds'), MIN_SECONDS), HARD_MAX_SECONDS)
        default = min(max(_number_setting(values, 'default_duration_seconds'), MIN_SECONDS), maximum)
        warning = max(_number_setting(values, 'long_video_warning_seconds'), MIN_SECONDS)
        return cls(default, warning, maximum)

    def public(self):
        return {'default_seconds': self.default_seconds, 'maximum_seconds': self.max_seconds,
                'long_video_warning_seconds': self.warning_seconds, 'minimum_seconds': MIN_SECONDS,
                'setting': SETTINGS_KEY + '.max_duration_seconds'}


class DurationError(ValueError):
    def __init__(self, code, seconds=None):
        self.code, self.seconds = code, seconds
        super().__init__(code)


def explicit_seconds(value):
    """Validate a UI/request duration: a finite positive number, or None for Auto."""
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise DurationError('video_duration_invalid')
    return round(float(value), 3)


@dataclass(frozen=True)
class Resolution:
    seconds: float
    source: str                    # explicit | prompt | default
    prompt_seconds: float | None   # What the prompt said, even when overridden
    prompt_span: tuple | None

    @property
    def conflict(self):
        return self.source == 'explicit' and self.prompt_seconds is not None and abs(self.prompt_seconds - self.seconds) > 1e-6


def resolve(explicit, prompt, policy):
    """Precedence: explicit choice > duration stated in the prompt > configured default."""
    chosen = explicit_seconds(explicit)
    stated, span = parse_duration(prompt)
    if chosen is not None:
        seconds, source = chosen, 'explicit'
    elif stated is not None:
        seconds, source = round(stated, 3), 'prompt'
    else:
        seconds, source = policy.default_seconds, 'default'
    if seconds < MIN_SECONDS:
        raise DurationError('video_duration_invalid', seconds)
    if seconds > policy.max_seconds or seconds > HARD_MAX_SECONDS:
        raise DurationError('video_duration_too_long', seconds)
    return Resolution(seconds, source, stated, span)


@dataclass(frozen=True)
class Segment:
    index: int          # 1-based
    frames: int         # Frames the engine renders for this segment
    keep_start: int     # First rendered frame kept (1 skips a continuation's held frame)
    keep_frames: int    # Frames this segment contributes to the final video
    source: str         # text | image | continuation | text-independent


@dataclass(frozen=True)
class Plan:
    target_seconds: float
    fps: int
    total_frames: int
    native_frames: int
    continuation: str   # last_frame | independent | none
    mode: str           # text_to_video | image_to_video
    segments: tuple

    @property
    def segment_count(self):
        return len(self.segments)

    @property
    def native_seconds(self):
        return self.native_frames / self.fps

    @property
    def final_seconds(self):
        return self.total_frames / self.fps

    @property
    def direct(self):
        """One native segment already within one frame of the target: no re-encode."""
        return self.segment_count == 1 and abs(self.native_frames - self.total_frames) <= 1

    def public(self):
        return {'target_seconds': self.target_seconds, 'segments': self.segment_count, 'fps': self.fps,
                'frames': self.total_frames, 'native_segment_seconds': round(self.native_seconds, 4),
                'continuation': self.continuation, 'mode': self.mode}


def plan(target_seconds, *, image=False, continuation=True, fps=FPS, native_frames=NATIVE_FRAMES):
    """Deterministic segment plan for one target duration.

    With continuation, segment N+1 starts from segment N's last frame; its
    first rendered frame repeats that frame, so it is dropped when stitching
    and each continuation adds native_frames - 1 new frames. Without
    continuation (image-to-video unavailable) segments are independent.
    """
    if type(target_seconds) not in (int, float) or not math.isfinite(target_seconds) or target_seconds <= 0:
        raise DurationError('video_duration_invalid')
    if target_seconds > HARD_MAX_SECONDS:
        raise DurationError('video_duration_too_long', target_seconds)
    total = max(1, round(target_seconds * fps))
    step = native_frames - 1 if continuation else native_frames
    count = 1 if total <= native_frames else 1 + math.ceil((total - native_frames) / step)
    if count > HARD_MAX_SEGMENTS:
        raise DurationError('video_duration_too_long', target_seconds)
    segments, remaining = [], total
    for index in range(1, count + 1):
        first = index == 1
        keep_start = 0 if first or not continuation else 1
        keep = min(native_frames - keep_start, remaining)
        source = ('image' if image else 'text') if first else ('continuation' if continuation else 'text-independent')
        segments.append(Segment(index, native_frames, keep_start, keep, source))
        remaining -= keep
    mode = 'image_to_video' if image else 'text_to_video'
    strategy = 'none' if count == 1 else 'last_frame' if continuation else 'independent'
    return Plan(round(float(target_seconds), 3), fps, total, native_frames, strategy, mode, tuple(segments))


def estimate(segment_count, samples):
    """(low, high) seconds from measured segment times, or None without enough data.

    Samples are wall-clock seconds of recent successful segments on this
    computer; no ETA is invented without them.
    """
    values = sorted(float(v) for v in samples if type(v) in (int, float) and 0 < v < 7200)
    if len(values) < 2:
        return None
    return values[0] * segment_count, values[-1] * segment_count


def label(seconds):
    """Compact human duration: 20 s, 1 min, 1 min 30 s, 2.5 s."""
    if seconds < 60:
        return (f'{seconds:.1f}'.rstrip('0').rstrip('.') if seconds % 1 else str(int(seconds))) + ' s'
    minutes, rest = divmod(round(seconds), 60)
    return f'{minutes} min' + (f' {rest} s' if rest else '')
