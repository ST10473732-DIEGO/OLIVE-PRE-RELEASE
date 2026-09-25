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


def _tesseract(image, scale, left, top, words=False, psm=11):
    data = io.BytesIO()
    image.save(data, format='PNG')
    output = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', str(psm), 'tsv'], input=data.getvalue(),
                            capture_output=True, timeout=10, check=True)
    grouped = {}
    for word in csv.DictReader(io.StringIO(output.stdout.decode(errors='replace')), delimiter='\t',
                               quoting=csv.QUOTE_NONE):
        if word.get('level') != '5' or not (word.get('text') or '').strip():
            continue
        key = tuple(word[k] for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        grouped.setdefault(key, []).append(word)
    if words:
        # Each word keeps its own confidence, so one unreadable word (for example a
        # small-caps category label) never hides a clearly read neighbour.
        return [{'text': w['text'], 'confidence': float(w['conf']),
                 'box': (int(w['left']) / scale + left, int(w['top']) / scale + top,
                         (int(w['left']) + int(w['width'])) / scale + left,
                         (int(w['top']) + int(w['height'])) / scale + top)}
                for group in grouped.values() for w in group]
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


def ocr_lines(frame, box, scale=3, isolate=True, words=False, psm=11):
    """Two independent passes: global contrast, and text isolated from its local background.

    The second pass keeps low-contrast placeholders readable when a crop spans
    several background shades. Lines are merged; duplicates keep the higher confidence.
    With words=True the same passes return individual words with their own confidence.
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
    readings = (_tesseract(basic, scale, left, top, words, psm) +
                (_tesseract(isolated, scale, left, top, words, psm) if isolate else []))
    if words:
        # Words from the two passes that cover the same glyphs are one reading.
        for word in readings:
            merge_reading(merged, word)
        merged.sort(key=lambda word: (word['box'][1], word['box'][0]))
        return merged
    for line in readings:
        # Lines merge only identical text; the more confident reading is kept.
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


def merge_reading(found, word):
    """Add one word reading to `found`, resolving readings of the same glyphs.

    Near-identical boxes are one reading: the more confident wins. A credible
    reading (confidence >= MIN_CONFIDENCE) that spans narrower ones is the whole
    word they are fragments of (for example a pass that split '#nepali-jerk-circle'
    at its hyphens) and replaces them; a low-confidence wide reading (for example a
    whole row read as one garbled glyph) never displaces confident fragments.
    """
    width = lambda box: max(1e-6, box[2] - box[0])
    shared = lambda a, b: min(a[2], b[2]) - max(a[0], b[0])
    overlapping = [other for other in found if _overlap(other['box'], word['box'])]
    for other in overlapping:
        if shared(other['box'], word['box']) >= .7 * max(width(other['box']), width(word['box'])):
            if word['confidence'] > other['confidence']:
                found[found.index(other)] = word
            return
    credible = word['confidence'] >= MIN_CONFIDENCE
    inside = [o for o in overlapping if shared(o['box'], word['box']) >= .7 * width(o['box'])]
    around = [o for o in overlapping if shared(o['box'], word['box']) >= .7 * width(word['box'])]
    if any(o['confidence'] >= MIN_CONFIDENCE for o in around):
        return  # A fragment of a credible wider reading.
    if inside and not credible:
        return  # A garbled wide reading next to confident fragments.
    for fragment in inside:
        found.remove(fragment)
    for garbled in around:
        found.remove(garbled)
    found.append(word)


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


def unchanged_outside(before, after, box, within=None):
    """True when two same-size frames are pixel-identical everywhere outside `box`
    (and, with `within`, only inside that area).

    Model- and OCR-free evidence that nothing but that region changed between a
    verified observation and a later one (for example, only the composer).
    """
    from PIL import Image, ImageChops, ImageDraw
    if (before['width'], before['height']) != (after['width'], after['height']):
        return False
    masked = box[2] > box[0] and box[3] > box[1]
    left, top, right, bottom = clamp_box(after, box) if masked else (0, 0, 0, 0)
    images = []
    for frame in (before, after):
        with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as image:
            rgb = image.convert('RGB')
        if within:
            rgb = rgb.crop(tuple(int(v) for v in clamp_box(after, within)))
            left, top, right, bottom = left - within[0], top - within[1], right - within[0], bottom - within[1]
        if masked:
            ImageDraw.Draw(rgb).rectangle((left, top, right - 1, bottom - 1), fill=(0, 0, 0))
        images.append(rgb)
    return images[0].size == images[1].size and ImageChops.difference(*images).getbbox() is None


def ocr_words(frame, box, scale=4, psm=11):
    return ocr_lines(frame, box, scale=scale, words=True, psm=psm)


def ocr_rows(frame, box, scale=4, half_height=12, only=None, psm=11, coarse_scale=None):
    """Words of a list, each row re-read as its own strip.

    A coarse read of the whole list locates the rows; reading each row alone is
    markedly more accurate for small labels. With `only` (a predicate on the words
    of a coarse row), only matching rows are re-read and the rest keep their coarse
    words. Overlapping readings keep the more confident one. Evidence only.
    """
    left, top, right, bottom = clamp_box(frame, box)
    coarse = ocr_words(frame, box, coarse_scale or scale)
    middles, kept = [], []
    for middle in sorted((w['box'][1] + w['box'][3]) / 2 for w in coarse):
        if not middles or middle - middles[-1] >= half_height / 2:
            middles.append(middle)
    if only is not None:
        near = lambda word, middle: abs((word['box'][1] + word['box'][3]) / 2 - middle) < half_height / 2
        selected = [m for m in middles if only([w for w in coarse if near(w, m)])]
        kept = [w for w in coarse if not any(near(w, m) for m in selected)]
        middles = selected
    found = []
    for middle in middles:
        try:
            words = ocr_words(frame, (left, max(top, middle - half_height), right, min(bottom, middle + half_height)), scale, psm)
        except ValueError:
            continue  # A strip clamped below the minimum size has nothing to read.
        for word in words:
            merge_reading(found, word)
    return kept + found
