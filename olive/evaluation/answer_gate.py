"""Finite held-out local answer gate using the existing benchmark adapter/leases.

No acquisition or promotion. Generated code is never repaired; isolated compiler
checks run with no network and no user files mounted. All trials are retained.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

from .backend_benchmark import distribution

CANDIDATES = {
    'olive-eval-hauhau-q6:20260924': '022de4bfdd9d4c16141f8c30846f155c51cf7a5b91090a24dcb63a7dbeddec07',
    'orcarouter/Qwen3.8-27B-Uncensored:q3_K_M': '4da593b4aaed076b41e22b07f680075ff3856c46802f64866c353ac2b1a4fbcd',
}
CASES = [
    ('followup', [
        {'role':'user', 'content':'For this conversation answer in Spanish, exactly two short lines, without Markdown. The test pump is named Cedar. Acknowledge.'},
        {'role':'assistant', 'content':'Entendido.\nLa bomba se llama Cedar.'},
        {'role':'user', 'content':'What is the pump called? Keep my earlier response constraints.'}]),
    ('missing_image', [{'role':'user','content':'What exact serial number is printed in the attached image? No image was actually attached. Answer in one sentence.'}]),
    ('missing_context', [{'role':'user','content':'What was the exact maintenance date in the PDF I mentioned yesterday? This conversation contains no PDF and no earlier date. Do not invent it; answer in under 30 words.'}]),
    ('format', [{'role':'user','content':'Return only a JSON object with keys "language" and "count", values "Spanish" and integer 3. No Markdown or other text.'}]),
    ('length', [{'role':'user','content':'Explain a Python list in exactly two lines, each at most eight words. No heading, bullets, or code.'}]),
    ('python', [{'role':'user','content':'Return only one Python code block defining cents(text). Convert a nonnegative decimal currency string to integer cents using Decimal, never float. Accept "0", "1.2", "12.34" and reject negative values, NaN, Infinity and more than two decimal places with ValueError. Include required imports. Do not read input or print.'}]),
    ('javascript', [{'role':'user','content':'Return only one JavaScript code block defining uniqueNames(values). Trim each string, discard blanks, and remove case-insensitive duplicates while preserving the first trimmed spelling and order. For [" Ada ","ada","","BOB","bob "] return ["Ada","BOB"]. No dependencies, I/O or exports.'}]),
]
SYSTEM = 'You are OLIVE, a local assistant. Follow the user constraints. Be truthful about missing context. Return useful answers and complete requested code.'
IMPLICIT_CASES = [
    ('implicit_image', 'What serial number is visible in the photograph I attached? Answer in one short sentence.'),
    ('implicit_pdf', 'Give the maintenance date from the attached PDF in one sentence.'),
    ('context_boundary8192', 'The marker is SILVER-291.\n' +
     'Maintenance record: routine inspection completed.\n' * 580 + '\nReturn only the marker from the beginning.'),
]


async def implicit_context_gate(service, registry, output):
    """Separate predeclared supplement: absent references without an absence hint."""
    from .backend_benchmark import sample_resources
    report = {'suite':'implicit-context-supplement', 'declared_cases':IMPLICIT_CASES, 'records':[]}
    output.write_text(json.dumps(report,indent=2)+'\n')
    for model in [*CANDIDATES, 'gpt-oss:20b']:
        cap = registry.get(model)
        if not cap or model in CANDIDATES and cap.digest.removeprefix('sha256:') != CANDIDATES[model]:
            raise ValueError('Pinned model identity changed')
        for case, prompt in IMPLICIT_CASES:
            options = {'temperature':.2,'num_predict':2048,'num_ctx':8192 if case.endswith('8192') else 4096}
            record = {'case':case,'model':model,'digest':cap.digest,'options':options,'passed':False}
            stop, samples = asyncio.Event(), []
            sampler = asyncio.create_task(sample_resources(stop, samples))
            start = time.monotonic()
            try:
                response = await asyncio.wait_for(service.chat_measured(model,
                    [{'role':'system','content':SYSTEM},{'role':'user','content':prompt}], options=options,
                    think='low' if model.startswith('gpt-oss') else False, stream=True),120)
                answer = response['content']
                record.update(answer=answer,prompt_tokens=response.get('prompt_eval_count'),first_visible_ms=response.get('first_token_ms'))
                if case == 'context_boundary8192':
                    record['passed'] = answer.strip() == 'SILVER-291'
                else:
                    record['passed'] = bool(re.search(r'cannot|can.t|don.t|do not|no (?:image|photo|pdf|file|attachment)|not (?:see|have|attached|provided)|please (?:attach|upload|provide)',answer,re.I))
                record['resident'] = await service.loaded_models()
            except Exception as error:
                record['error'] = type(error).__name__
            finally:
                stop.set(); await sampler
            record.update(seconds=time.monotonic()-start,
                peak_vram_mib=max((s.get('vram_used_mib',0) for s in samples),default=None),
                min_ram_available_bytes=min((s['ram_available_bytes'] for s in samples),default=None))
            report['records'].append(record)
            output.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:record.get(k) for k in ('model','case','passed','seconds','error')}),flush=True)
    return report


def score(case, answer):
    text = answer.strip()
    if case == 'format':
        try:
            value = json.loads(text)
            return value == {'language':'Spanish','count':3} and type(value['count']) is int
        except (ValueError, TypeError, KeyError):
            return False
    if case == 'followup':
        return len(text.splitlines()) == 2 and 'Cedar' in text and bool(re.search(r'\b(?:bomba|llama|nombre)\b', text, re.I)) and not re.search(r'[`*#]', text)
    if case == 'length':
        return len(text.splitlines()) == 2 and all(len(s.split()) <= 8 for s in text.splitlines()) and not re.search(r'[`*#]', text)
    if case == 'missing_image':
        return bool(re.search(r'no image|not attached|not provided|without.*image|cannot|can.t', text, re.I)) and not re.search(r'\b[A-Z]{2,}\d{3,}\b', text)
    if case == 'missing_context':
        return len(text.split()) < 30 and bool(re.search(r'don.t|do not|cannot|can.t|no |not ', text, re.I)) and not re.search(r'\b(?:19|20)\d{2}\b', text)
    return None


async def compiled(case, answer, node):
    fences = re.findall(r'```[^\n]*\n(.*?)```', answer, re.S)
    if len(fences) != 1:
        return {'passed':False, 'stage':'code_extraction'}
    code = fences[0]
    # Sandbox provides the boundary, not a source keyword filter.
    with tempfile.TemporaryDirectory(prefix='olive-answer-compile-') as folder:
        root = Path(folder)
        if case == 'python':
            (root/'candidate.py').write_text(code)
            checks = '''import runpy
ns = runpy.run_path('/work/candidate.py')
f = ns['cents']
for value, expected in [('0',0),('1.2',120),('12.34',1234),('90071992547409.93',9007199254740993)]:
    assert f(value) == expected, value
for value in ['-1','NaN','Infinity','0.001']:
    try: f(value)
    except ValueError: pass
    else: raise AssertionError(value)
'''
            (root/'check.py').write_text(checks)
            command = ['/usr/bin/python', '-I', '/work/check.py']
        else:
            (root/'check.js').write_text(code + '\n' + '''
const assert = require('node:assert/strict');
assert.deepEqual(uniqueNames([" Ada ","ada","","BOB","bob "]),["Ada","BOB"]);
assert.deepEqual(uniqueNames(["  ","Éva","éva","ÉVA","Cedar"]),["Éva","Cedar"]);
assert.deepEqual(uniqueNames([]),[]);
''')
            command = ['/node/bin/node', '/work/check.js']
        args = ['bwrap', '--die-with-parent', '--unshare-all', '--new-session',
                '--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
                '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(root),'/work',
                '--ro-bind',str(Path(node).resolve().parent.parent),'/node','--chdir','/work', *command]
        process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
            return {'passed':process.returncode == 0, 'stage':'compiled_behaviour', 'exit_code':process.returncode,
                    'diagnostic':stderr.decode(errors='replace')[-1200:], 'code_sha256':hashlib.sha256(code.encode()).hexdigest()}
        except TimeoutError:
            process.kill()
            await process.wait()
            return {'passed':False,'stage':'compiled_behaviour_timeout'}


async def run(service, registry, output, node):
    models = [*CANDIDATES, 'gpt-oss:20b']
    caps = {m:registry.get(m) for m in models}
    for model, cap in caps.items():
        if not cap or model in CANDIDATES and cap.digest.removeprefix('sha256:') != CANDIDATES[model]:
            raise ValueError('Missing or changed pinned answer candidate')
    report = {'suite':'olive-held-out-answer-20260924', 'models':{}, 'records':[],
              'declared_cases':[c[0] for c in CASES]+['context4096','context8192','latency_1','latency_2','latency_3','cancellation','recovery'],
              'promotion':'Not requested by this harness; decisions require review', 'c7':'NOT_RUN; public defaults unchanged'}
    def save():
        output.write_text(json.dumps(report, indent=2)+'\n')
    save()
    for model, cap in caps.items():
        thinking = 'low' if model.startswith('gpt-oss') else False
        options = {'temperature':.2, 'num_ctx':4096, 'num_predict':2048}
        report['models'][model] = {'digest':cap.digest, 'options':options, 'think':thinking}
        cases = list(CASES)
        for context in (4096,8192):
            filler = 'Maintenance record: routine inspection completed.\n' * (90 if context == 4096 else 210)
            prompt = 'Remember the marker COPPER-173.\n'+filler+'\nReturn only the marker from the beginning.'
            cases.append(('context'+str(context), [{'role':'user','content':prompt}]))
        cases += [('latency_'+str(i), [{'role':'user','content':'Return only the word READY.'}]) for i in range(1,4)]
        for case, messages in cases:
            configured = {**options,'num_ctx':8192 if case == 'context8192' else 4096}
            start = time.monotonic()
            record = {'model':model,'case':case,'options':configured,'passed':False}
            try:
                response = await asyncio.wait_for(service.chat_measured(model,
                    [{'role':'system','content':SYSTEM},*messages], options=configured, think=thinking, stream=True), 120)
                answer = response['content']
                record.update(answer=answer, first_visible_ms=response.get('first_token_ms'),
                              output_tokens=response.get('eval_count'), prompt_tokens=response.get('prompt_eval_count'))
                if case in {'python','javascript'}:
                    record.update(await compiled(case, answer, node))
                elif case.startswith('context'):
                    record['passed'] = answer.strip() == 'COPPER-173'
                elif case.startswith('latency'):
                    record['passed'] = answer.strip() == 'READY'
                else:
                    record['passed'] = score(case, answer)
            except Exception as error:
                record['error'] = type(error).__name__ + ': ' + str(error)[:300]
            record['seconds'] = time.monotonic()-start
            report['records'].append(record); save()
            print(json.dumps({k:record.get(k) for k in ('model','case','passed','seconds','error')}),flush=True)
        started = asyncio.Event()
        async def long_answer():
            async for chunk in service.chat_stream(model,[{'role':'user','content':'List all integers from 1 to 10000, one per line.'}],options=options,think=thinking):
                started.set()
        task = asyncio.create_task(long_answer())
        try:
            await asyncio.wait_for(started.wait(), 120)
            start = time.monotonic(); task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            report['records'].append({'model':model,'case':'cancellation','passed':task.cancelled(),'seconds':time.monotonic()-start})
        except TimeoutError:
            task.cancel(); await asyncio.gather(task, return_exceptions=True)
            report['records'].append({'model':model,'case':'cancellation','passed':False,'stage':'no_visible_output'})
        start = time.monotonic()
        try:
            response = await asyncio.wait_for(service.chat_measured(model,[{'role':'user','content':'Return only RECOVERED.'}],options=options,think=thinking,stream=True),120)
            report['records'].append({'model':model,'case':'recovery','passed':response['content'].strip()=='RECOVERED',
                'answer':response['content'],'seconds':time.monotonic()-start})
        except Exception as error:
            report['records'].append({'model':model,'case':'recovery','passed':False,'error':type(error).__name__})
        rows = [r for r in report['records'] if r['model']==model]
        report['models'][model]['failed_gates'] = [r['case'] for r in rows if not r['passed']]
        report['models'][model]['latency'] = distribution([r['seconds'] for r in rows if r['case'].startswith('latency')])
        save()
    return report
