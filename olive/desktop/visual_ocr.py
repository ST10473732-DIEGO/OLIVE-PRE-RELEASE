"""OCR of small, proposal-anchored frame crops; never whole conversation panes.

Lines are evidence signals, not authority. Each line keeps its frame-pixel box
and minimum word confidence so callers can require exact, unique, confident
matches. Dark themes are inverted and contrast-stretched so low-contrast
placeholder text is not thresholded away.
"""
import base64
import csv
import io
import re
import subprocess

MIN_CONFIDENCE = 60


def normalize(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w#@.+-]+', ' ', str(value).casefold())).strip()


def clamp_box(frame, box):
    left, top, right, bottom = box
    left, top = max(0, int(left)), max(0, int(top))
    right, bottom = min(int(frame['width']), int(right)), min(int(frame['height']), int(bottom))
    if right - left < 8 or bottom - top < 8:
        raise ValueError('Proposed region is outside the observed window')
    return left, top, right, bottom


def band(frame, point, half_height, half_width=None):
    """A crop around a model-proposed point; the model never chooses its size."""
    x, y = point
    half_width = frame['width'] if half_width is None else half_width
    return clamp_box(frame, (x - half_width, y - half_height, x + half_width, y + half_height))


def _tesseract(image, scale, left, top):
    data = io.BytesIO()
    image.save(data, format='PNG')
    output = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '11', 'tsv'], input=data.getvalue(),
                            capture_output=True, timeout=10, check=True)
    grouped = {}
    for word in csv.DictReader(io.StringIO(output.stdout.decode(errors='replace')), delimiter='\t',
                               quoting=csv.QUOTE_NONE):
        if word.get('level') != '5' or not (word.get('text') or '').strip():
            continue
        key = tuple(word[k] for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        grouped.setdefault(key, []).append(word)
    lines = []
    for words in grouped.values():
        words.sort(key=lambda w: int(w['left']))
        l = min(int(w['left']) for w in words) / scale + left
        t = min(int(w['top']) for w in words) / scale + top
        r = max(int(w['left']) + int(w['width']) for w in words) / scale + left
        b = max(int(w['top']) + int(w['height']) for w in words) / scale + top
        lines.append({'text': ' '.join(w['text'] for w in words), 'box': (l, t, r, b),
                      'confidence': min(float(w['conf']) for w in words)})
    return lines


def ocr_lines(frame, box, scale=3):
    """Two independent passes: global contrast, and text isolated from its local background.

    The second pass keeps low-contrast placeholders readable when a crop spans
    several background shades. Lines are merged; duplicates keep the higher confidence.
    """
    from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat
    left, top, right, bottom = clamp_box(frame, box)
    with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
        gray = ImageOps.grayscale(image.crop((left, top, right, bottom)))
    size = (gray.width * scale, gray.height * scale)
    basic = ImageOps.invert(gray) if ImageStat.Stat(gray).mean[0] < 128 else gray
    basic = ImageOps.autocontrast(basic).resize(size)  # No cutoff: sparse text is the extreme 1%.
    large = gray.resize(size, Image.LANCZOS)
    background = large.filter(ImageFilter.MedianFilter(21)).filter(ImageFilter.BoxBlur(30))
    isolated = ImageChops.difference(large, background).point(lambda v: 0 if v > 30 else 255)
    merged = []
    for line in _tesseract(basic, scale, left, top) + _tesseract(isolated, scale, left, top):
        duplicate = next((m for m in merged if normalize(m['text']) == normalize(line['text']) and
                          _overlap(m['box'], line['box'])), None)
        if duplicate is None:
            merged.append(line)
        elif line['confidence'] > duplicate['confidence']:
            merged[merged.index(duplicate)] = line
    merged.sort(key=lambda line: (line['box'][1], line['box'][0]))
    return merged


def _overlap(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def confident(lines):
    return [line for line in lines if line['confidence'] >= MIN_CONFIDENCE]
