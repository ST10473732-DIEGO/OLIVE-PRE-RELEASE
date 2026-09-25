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


def ocr_lines(frame, box, scale=3, isolate=True):
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
    for line in _tesseract(basic, scale, left, top) + (_tesseract(isolated, scale, left, top) if isolate else []):
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


def region_lines(frame, limit=24):
    """Region-first reading: OCR each filled area that differs from the page background.

    For labels inside filled controls whose polarity differs from the page (for
    example white text on dark buttons in a light UI). Pure PIL; bounded number
    of regions. Lines keep frame coordinates. Evidence only, never authority.
    """
    from PIL import Image, ImageChops
    with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
        rgb = image.convert('RGB')
    step = 4
    small = rgb.resize((max(1, rgb.width // step), max(1, rgb.height // step)), Image.NEAREST)
    colors = small.getcolors(small.width * small.height) or []
    if not colors:
        return []
    background = max(colors)[1]
    difference = ImageChops.difference(small, Image.new('RGB', small.size, background)).convert('L')
    mask = difference.point(lambda v: 255 if v > 40 else 0).load()
    seen, boxes = set(), []
    for y in range(small.height):
        for x in range(small.width):
            if mask[x, y] == 0 or (x, y) in seen:
                continue
            stack, left, top, right, bottom, count = [(x, y)], x, y, x, y, 0
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                count += 1
                left, top, right, bottom = min(left, cx), min(top, cy), max(right, cx), max(bottom, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < small.width and 0 <= ny < small.height and mask[nx, ny] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            width, height = (right - left + 1) * step, (bottom - top + 1) * step
            # Control-sized, mostly filled components only (not page chrome or text specks).
            if 16 <= height <= 160 and 24 <= width <= rgb.width * .9 and count * step * step >= .6 * width * height:
                boxes.append((left * step, top * step, (right + 1) * step, (bottom + 1) * step))
    lines = []
    scale_x, scale_y = frame['width'] / rgb.width, frame['height'] / rgb.height
    for left, top, right, bottom in sorted(boxes, key=lambda b: (b[1], b[0]))[:limit]:
        # Inset past the control's own border; its uniform fill needs one pass.
        inset = (left + 3) * scale_x, (top + 3) * scale_y, (right - 3) * scale_x, (bottom - 3) * scale_y
        try:
            lines.extend(ocr_lines(frame, inset, scale=3, isolate=False))
        except ValueError:
            continue
    return lines
