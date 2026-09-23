"""Held-out synthetic localization, including absent targets; no desktop input.

Fixed seed and cases; reports this local quantization, not upstream benchmarks.
Screens are generated in memory and never contain user data.
"""
import argparse
import asyncio
import base64
import io
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from olive.services.gui_model_service import GuiModelService, MODEL
from olive.services.model_residency_service import ModelResidencyService


def cases(seed=871934):
    rng = random.Random(seed)
    labels = ['Save copy', 'Open folder', 'Next page', 'Apply filter', 'New note', 'Zoom in',
              'View details', 'Refresh', 'Previous', 'Cancel', 'Send', 'Archive', 'Show all', 'Search']
    for index in range(50):
        width, height = [(1024, 640), (1280, 720), (800, 1000), (960, 640), (1120, 840)][index % 5]
        dark = index % 2 == 0
        image = Image.new('RGB', (width, height), '#20242c' if dark else '#edf0f5')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('DejaVuSans.ttf', 20 if index % 3 else 26)
        draw.text((28, 20), 'OLIVE synthetic workspace', fill='#ffffff' if dark else '#17202d', font=font)
        chosen = rng.sample(labels, 6)
        target_index = rng.randrange(6)
        absent = index % 5 == 4
        target = 'Export report' if absent else chosen[target_index]
        expected = None
        for button, label in enumerate(chosen):
            column, row = button % 2, button // 2
            left = 35 + column * (width//2) + rng.randrange(0, 35)
            top = 115 + row * ((height-140)//3) + rng.randrange(0, 20)
            rect = (left, top, left+width//2-105, top+65)
            draw.rounded_rectangle(rect, radius=8, fill='#316baf' if dark else '#cddcee', outline='#7595bb', width=2)
            draw.text((left+15, top+18), label, font=font, fill='white' if dark else '#111b26')
            if not absent and button == target_index:
                expected = rect
        yield index, image, target, expected


async def evaluate(seed=871934):
    class NoOtherModels:
        async def unload_model(self, name):
            raise RuntimeError('This isolated evaluation owns no Ollama model')
    model = GuiModelService(ModelResidencyService(NoOtherModels()))
    rows = []
    resources = []
    try:
        for index, image, target, expected in cases(seed):
            data = io.BytesIO()
            image.save(data, format='PNG')
            frame = {'png': base64.b64encode(data.getvalue()).decode(), 'width': image.width, 'height': image.height}
            started = time.monotonic()
            try:
                action = await model.action(frame, 'Click ' + target + '. If the target is absent, use interact.')
                if expected:
                    x, y = action.get('coordinate', [-1000, -1000])
                    x, y = x * image.width/1000, y * image.height/1000
                    passed = action['action'] == 'left_click' and expected[0] <= x <= expected[2] and expected[1] <= y <= expected[3]
                else:
                    passed = action['action'] == 'interact' or action == {'action': 'terminate', 'status': 'failure'}
                result = {'action': action['action'], 'point': action.get('coordinate')}
            except Exception as error:
                passed, result = False, {'error': type(error).__name__, 'message': str(error)[:150]}
            row = {'case': index, 'present': expected is not None, 'pass': passed,
                   'seconds': time.monotonic()-started, **result}
            rows.append(row)
            print(json.dumps(row), flush=True)
            import psutil
            process = psutil.Process(model.process.pid)
            processes = [process, *process.children(recursive=True)]
            pids = {p.pid for p in processes}
            gpu = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory',
                '--format=csv,noheader,nounits'], text=True)
            resources.append({'rss_bytes': sum(p.memory_info().rss for p in processes),
                'vram_mib': sum(int(line.split(',')[1].strip()) for line in gpu.splitlines()
                                if int(line.split(',')[0].strip()) in pids)})
        return {'model': MODEL, 'fixture_seed': seed, 'count': len(rows),
                'correct': sum(row['pass'] for row in rows),
                'present_correct': sum(r['pass'] for r in rows if r['present']),
                'absent_correct': sum(r['pass'] for r in rows if not r['present']),
                'median_seconds': statistics.median(r['seconds'] for r in rows[1:]),
                'cases': rows, 'metrics': model.metrics,
                'peak_sampled_rss_bytes': max(r['rss_bytes'] for r in resources),
                'peak_sampled_vram_mib': max(r['vram_mib'] for r in resources)}
    finally:
        await model.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=871934)
    args = parser.parse_args()
    with args.output.open('x') as output:
        json.dump(asyncio.run(evaluate(args.seed)), output, indent=2)
