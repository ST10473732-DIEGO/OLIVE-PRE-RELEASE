"""Declared MAX-role gate for a pinned local candidate through production Chat.

Runs the ordinary ServiceContainer Chat path in an isolated temporary profile.
Only this evaluation process maps OLIVE MAX to the candidate; public presets,
user profiles and remote mappings are untouched. Generated code runs in a
no-network Bubblewrap sandbox with no user files. Writes one JSON evidence file.
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DECLARATION = {
    'role': 'OLIVE MAX (heavy answer + code); FAST/NORMAL/DEEP/REIMAGINE/GUI grounding unchanged',
    'profile': 'production preset max: temperature 0.2, max_tokens 8192, think=false, coding-role context budget',
    'cases': {
        'M1_python': 'parse_duration: compiled behaviour in sandbox (6 assertions)',
        'M2_javascript': 'slugify: compiled behaviour in sandbox (5 assertions)',
        'M3_rust_no_run': 'one rust code block; no claim that it was executed',
        'M4_follow_up': 'is_palindrome then follow-up adding a length rule; both rules checked in sandbox',
        'M5_long_answer': 'complete (not truncated), >= 8 numbered sections',
        'M6_table': 'markdown table with the three requested columns and three rows',
        'M7_cancel_recover': 'Stop after first streamed text: no stream events after Stop, then a fresh exact answer',
        'M8_residency_handoff': 'candidate -> GUI-Owl -> candidate, never both resident; handoff and first-token times',
        'M9_resource': 'no OOM or provider error at MAX settings on the 16 GiB GPU; cold first token <= 60 s, warm <= 10 s',
    },
    'pass_rule': 'every case passes; any failure blocks promotion and is reported as FAILED_GATE',
}

PY_CHECK = '''import runpy
f = runpy.run_path('/work/candidate.py')['parse_duration']
for value, expected in [('1h30m', 5400), ('45s', 45), ('2h', 7200), ('1h1m1s', 3661)]:
    assert f(value) == expected, value
for value in ['', 'abc', '5x', '-1h']:
    try: f(value)
    except ValueError: pass
    else: raise AssertionError(value)
'''
JS_CHECK = '''
const assert = require('node:assert/strict');
assert.equal(slugify('Hello, World!'), 'hello-world');
assert.equal(slugify('  Multiple   spaces  '), 'multiple-spaces');
assert.equal(slugify('Déjà vu'), 'deja-vu');
assert.equal(slugify('a--b__c'), 'a-b-c');
assert.equal(slugify(''), '');
'''
PAL_CHECK = '''import runpy
f = runpy.run_path('/work/candidate.py')['is_palindrome']
assert f('A man, a plan, a canal: Panama') is True
assert f('Racecar') is True
assert f('hello') is False
assert f('Aa') is False
assert f('') is False
'''


def fences(answer, language=None):
    blocks = re.findall(r'```([^\n]*)\n(.*?)```', answer, re.S)
    return [code for lang, code in blocks if language is None or language in lang.lower()] or \
        ([code for _, code in blocks] if language is None else [])


def sandbox(files, command, node=None):
    with tempfile.TemporaryDirectory(prefix='olive-max-gate-') as folder:
        root = Path(folder)
        for name, text in files.items():
            (root / name).write_text(text)
        args = ['bwrap', '--die-with-parent', '--unshare-all', '--new-session', '--ro-bind', '/usr', '/usr',
                '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib', '/lib64', '--proc', '/proc', '--dev', '/dev',
                '--tmpfs', '/tmp', '--ro-bind', str(root), '/work', '--chdir', '/work']
        if node:
            args += ['--ro-bind', str(Path(node).resolve().parent.parent), '/node']
        completed = subprocess.run(args + command, capture_output=True, text=True, timeout=15)
        return {'passed': completed.returncode == 0, 'exit_code': completed.returncode,
                'diagnostic': completed.stderr[-800:]}


class GPU:
    def __init__(self):
        self.samples, self.task = [], None

    async def loop(self):
        while True:
            process = await asyncio.create_subprocess_exec('nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits',
                                                           stdout=asyncio.subprocess.PIPE)
            out, _ = await process.communicate()
            try:
                self.samples.append((time.monotonic(), int(out.strip())))
            except ValueError:
                pass
            await asyncio.sleep(.5)

    def start(self):
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)

    def peak(self, since=0):
        values = [v for t, v in self.samples if t >= since]
        return max(values) if values else None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--digest', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--node', default=str(Path(__file__).resolve().parents[1] / '.toolchains/node/bin/node'))
    args = parser.parse_args()
    result = {'declaration': DECLARATION, 'model': args.model, 'expected_digest': args.digest, 'cases': {}}
    args.output.write_text(json.dumps(result, indent=1))
    from olive.services import presets
    public_before = dict(presets.PRESETS['max'])
    presets.PRESETS['max']['model'] = args.model  # This evaluation process only.
    from olive.application.service_container import ServiceContainer
    from olive.models import Chat
    events = []
    def publish(topic, value):
        events.append((time.monotonic(), topic, value))
    with tempfile.TemporaryDirectory(prefix='olive-max-profile-') as profile:
        services = ServiceContainer(publish, None, data_dir=profile, migrate=False)
        await services.initialize()
        info = next((m for m in services.model_infos if m.name == args.model), None)
        result['observed_digest'] = getattr(info, 'digest', '')
        gpu = GPU()
        gpu.start()

        def new_chat():
            chat = Chat(title='MAX gate', preset='max')
            services.chats[chat.id] = chat
            services.presets.apply(chat, 'max')
            return chat

        async def ask(chat, text):
            started = time.monotonic()
            first = None
            mark = len(events)
            task = asyncio.create_task(services.chat.send(chat.id, text))
            while not task.done():
                if first is None and any(t == 'chat_stream' and v.get('chat_id') == chat.id for _, t, v in events[mark:]):
                    first = time.monotonic() - started
                await asyncio.sleep(.02)
            await task
            message = chat.messages[-1]
            return {'answer': message.content, 'completion_state': message.completion_state,
                    'provider_model': message.provider.get('model'), 'provider_digest': message.provider.get('digest'),
                    'seconds': round(time.monotonic() - started, 3),
                    'first_token_seconds': round(first, 3) if first is not None else None,
                    'answer_sha256': hashlib.sha256(message.content.encode()).hexdigest()}

        def record(name, value, passed):
            value['passed'] = bool(passed)
            result['cases'][name] = value
            args.output.write_text(json.dumps(result, indent=1))
            print(name, 'PASS' if passed else 'FAIL', flush=True)

        try:
            since = time.monotonic()
            r = await ask(new_chat(), "Write a Python function parse_duration(text) that converts strings like "
                          "'1h30m', '45s', '2h' or '1h1m1s' into total seconds as an int. Raise ValueError for empty, "
                          "negative or malformed input. Reply with one Python code block only.")
            code = fences(r['answer'], 'python') or fences(r['answer'])
            r['behaviour'] = sandbox({'candidate.py': code[0], 'check.py': PY_CHECK},
                                     ['/usr/bin/python', '-I', '/work/check.py']) if code else {'passed': False}
            r['gpu_peak_mib'] = gpu.peak(since)
            record('M1_python', r, r['behaviour']['passed'] and r['completion_state'] == 'complete')

            r = await ask(new_chat(), 'Write a JavaScript function slugify(title) that lowercases, removes accents, '
                          'replaces every run of non-alphanumeric characters with a single hyphen and trims hyphens '
                          'from both ends. Reply with one JavaScript code block only, no exports.')
            code = fences(r['answer'], 'javascript') or fences(r['answer'], 'js') or fences(r['answer'])
            r['behaviour'] = sandbox({'check.js': code[0] + '\n' + JS_CHECK}, ['/node/bin/node', '/work/check.js'],
                                     node=args.node) if code else {'passed': False}
            record('M2_javascript', r, r['behaviour']['passed'])

            r = await ask(new_chat(), 'Write a Rust function that reverses the order of words in a sentence.')
            rust = fences(r['answer'], 'rust')
            claims = re.search(r'\b(?:I (?:ran|executed|tested|compiled)|output was|running it (?:gives|prints))\b', r['answer'], re.I)
            r['rust_blocks'], r['execution_claim'] = len(rust), bool(claims)
            record('M3_rust_no_run', r, len(rust) >= 1 and 'fn ' in rust[0] and not claims)

            chat = new_chat()
            first = await ask(chat, 'Write a Python function is_palindrome(s) that ignores case, spaces and '
                              'punctuation. Reply with one Python code block only.')
            second = await ask(chat, 'Now also make it return False for inputs with fewer than 3 letters or digits, '
                               'keeping the earlier rules. Reply with the complete updated code block only.')
            code = fences(second['answer'], 'python') or fences(second['answer'])
            second['behaviour'] = sandbox({'candidate.py': code[0], 'check.py': PAL_CHECK},
                                          ['/usr/bin/python', '-I', '/work/check.py']) if code else {'passed': False}
            record('M4_follow_up', {'first': first, 'second': second}, second['behaviour']['passed'])

            since = time.monotonic()
            r = await ask(new_chat(), 'Explain in detail how a TLS 1.3 handshake works, organised as at least 8 '
                          'numbered sections with a heading each.')
            sections = len(re.findall(r'^\s*(?:#+\s*)?(?:\*\*)?\d+[.)]', r['answer'], re.M))
            r['numbered_sections'], r['characters'] = sections, len(r['answer'])
            r['gpu_peak_mib'] = gpu.peak(since)
            record('M5_long_answer', r, r['completion_state'] == 'complete' and sections >= 8)

            r = await ask(new_chat(), 'Return only a Markdown table comparing Python list, tuple and set with the '
                          'columns Mutability, Ordered and Duplicates.')
            table = [l for l in r['answer'].splitlines() if l.strip().startswith('|')]
            header = table[0].lower() if table else ''
            r['table_rows'] = max(0, len(table) - 2)
            record('M6_table', r, all(c in header for c in ('mutability', 'ordered', 'duplicates')) and r['table_rows'] == 3)

            chat = new_chat()
            mark = len(events)
            task = asyncio.create_task(services.chat.send(chat.id, 'Write a very long, detailed history of the '
                                                          'printing press in at least 3000 words.'))
            while not any(t == 'chat_stream' and v.get('chat_id') == chat.id for _, t, v in events[mark:]):
                await asyncio.sleep(.02)
            stopped_at = time.monotonic()
            services.chat.stop(chat.id)
            await asyncio.gather(task, return_exceptions=True)
            stop_seconds = time.monotonic() - stopped_at
            await asyncio.sleep(1.5)
            late = [t for t, topic, v in events[mark:] if topic == 'chat_stream' and v.get('chat_id') == chat.id
                    and t > stopped_at + stop_seconds + .1]
            state = chat.messages[-1].completion_state if chat.messages[-1].role == 'assistant' else 'none'
            recovery = await ask(new_chat(), 'Reply with exactly: recovered')
            record('M7_cancel_recover', {'stop_seconds': round(stop_seconds, 3), 'late_stream_events': len(late),
                                         'stopped_state': state, 'recovery': recovery},
                   not late and state in {'incomplete', 'none'} and 'recovered' in recovery['answer'].lower())

            from olive.services.gui_model_service import GuiModelService
            from PIL import Image, ImageDraw
            image = Image.new('RGB', (640, 360), (245, 245, 245))
            draw = ImageDraw.Draw(image)
            draw.rectangle((250, 150, 390, 200), fill=(40, 90, 200))
            draw.text((290, 168), 'Continue', fill=(255, 255, 255))
            data = io.BytesIO()
            image.save(data, format='PNG')
            frame = {'png': base64.b64encode(data.getvalue()).decode(), 'width': 640, 'height': 360}
            gui = GuiModelService(services.model_residency)
            handoff_start = time.monotonic()
            residency_owners = []
            async def watch():
                while True:
                    residency_owners.append(services.model_residency.active)
                    await asyncio.sleep(.1)
            watcher = asyncio.create_task(watch())
            action = await gui.action(frame, 'Click the Continue button.')
            to_gui = time.monotonic() - handoff_start
            gui_peak = gpu.peak(handoff_start)
            back_start = time.monotonic()
            back = await ask(new_chat(), 'Reply with exactly: back on max')
            to_max = time.monotonic() - back_start
            # Cancellation during a handoff must leave the next request usable.
            cancel = asyncio.create_task(gui.action(frame, 'Click the Continue button.'))
            await asyncio.sleep(.5)
            cancel.cancel()
            await asyncio.gather(cancel, return_exceptions=True)
            after_cancel = await ask(new_chat(), 'Reply with exactly: after cancel')
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            await gui.close()
            owners = sorted({str(o) for o in residency_owners if o})
            record('M8_residency_handoff', {'gui_action': action, 'candidate_to_gui_seconds': round(to_gui, 3),
                                            'gui_to_candidate_answer_seconds': round(to_max, 3),
                                            'first_token_after_reacquire': back['first_token_seconds'],
                                            'gui_peak_mib': gui_peak, 'residency_owners_seen': owners,
                                            'back': back, 'after_cancelled_handoff': after_cancel},
                   'back on max' in back['answer'].lower() and 'after cancel' in after_cancel['answer'].lower()
                   and action.get('action') == 'left_click')
            firsts = [c.get('first_token_seconds') for c in (result['cases']['M1_python'], back, after_cancel)]
            record('M9_resource', {'gpu_peak_mib_overall': gpu.peak(), 'gpu_total_mib': 16384,
                                   'first_token_cold': firsts[0], 'first_token_warm': after_cancel['first_token_seconds'],
                                   'provider_digest_matches': result['observed_digest'] == args.digest},
                   gpu.peak() is not None and gpu.peak() <= 16384 and firsts[0] is not None and firsts[0] <= 60
                   and (after_cancel['first_token_seconds'] or 99) <= 10 and result['observed_digest'] == args.digest)
        finally:
            await gpu.stop()
            await services.shutdown()
    presets.PRESETS['max'].update(public_before)
    result['passed'] = all(c['passed'] for c in result['cases'].values()) and len(result['cases']) == 9
    args.output.write_text(json.dumps(result, indent=1))
    print('RESULT', 'PASSED' if result['passed'] else 'FAILED_GATE', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
