"""Independent literal target evidence for the accepted visual text-control route."""
import base64
import csv
import io
import re
import subprocess


def normalize(value):
    return re.sub(r'\W+', ' ', value.casefold()).strip()


def locate(frame, label):
    """Require one complete OCR line, never a first fuzzy match or model label."""
    from PIL import Image, ImageOps, ImageStat
    with Image.open(io.BytesIO(base64.b64decode(frame['png'], validate=True))) as pixels:
        output_image = io.BytesIO()
        pixels = ImageOps.grayscale(pixels)
        if ImageStat.Stat(pixels).mean[0] < 128:
            # Light text on filled dark controls is otherwise classified as an
            # image by sparse-page OCR. Keep the confidence/uniqueness gate.
            pixels = pixels.point(lambda value: 0 if value > 160 else 255)
        pixels.resize((pixels.width*2, pixels.height*2)).save(output_image, format='PNG')
    output = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '11', 'tsv'],
        input=output_image.getvalue(), capture_output=True, timeout=8, check=True)
    lines = {}
    for word in csv.DictReader(io.StringIO(output.stdout.decode()), delimiter='\t'):
        if word['level'] != '5' or not word['text'].strip():
            continue
        key = tuple(word[k] for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        lines.setdefault(key, []).append(word)
    matches = []
    for words in lines.values():
        if normalize(' '.join(w['text'] for w in words)) != normalize(label) or min(float(w['conf']) for w in words) < 70:
            continue
        left = min(int(w['left']) for w in words)
        top = min(int(w['top']) for w in words)
        right = max(int(w['left'])+int(w['width']) for w in words)
        bottom = max(int(w['top'])+int(w['height']) for w in words)
        matches.append((left/2, top/2, right/2, bottom/2))
    if len(matches) != 1:
        raise ValueError('Visual target is absent, ambiguous or unreadable; no input')
    return matches[0]


def validate_point(action, frame, bounds):
    if action['action'] != 'left_click':
        raise ValueError('The visual proposal did not resolve the requested click')
    x, y = action['coordinate']
    x, y = x * frame['width']/1000, y * frame['height']/1000
    left, top, right, bottom = bounds
    if not (left-8 <= x <= right+8 and top-8 <= y <= bottom+8):
        raise ValueError('GUI model and independent target evidence disagree')
    return x, y
