"""Opt-in bounded model-backed scope check against one public documentation page.

Writes only an isolated profile and ignored review artifacts. Does not modify the
recorded old result, model assignments, permissions, or a user's Research history.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')


async def run(output, recorded_only=False):
    from olive.application.service_container import ServiceContainer
    from olive.research.extraction import extract_page, MAX_HTML
    from olive.research.evidence import extract_evidence
    from olive.research.models import ResearchSession, ResearchSource, ResearchEvidence, timestamp
    from olive.research.scope_review import review_scope
    from olive.agent.model_router import RoutingRequest
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((ROOT/'tests/fixtures/research_scope_original.json').read_text(encoding='utf-8'))
    url = 'https://docs.python.org/3/library/unittest.html'
    fetch_record = output/'source-fetch.json'
    if (output/'public-source.html').exists():
        raw = (output/'public-source.html').read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=25) as response:
            if response.url != url:
                raise ValueError('Unexpected source redirect')
            raw = response.read(MAX_HTML + 1)
        fetch_record.write_text(json.dumps({'url':url,'retrieved_at':timestamp()}),encoding='utf-8')
    if len(raw) > MAX_HTML:
        raise ValueError('Source exceeds bound')
    (output/'public-source.html').write_bytes(raw)
    page = extract_page(raw.decode('utf-8'), url)
    if not fetch_record.exists():
        raise ValueError('Recorded HTML requires its original retrieval timestamp')
    page.retrieved_at = json.loads(fetch_record.read_text(encoding='utf-8'))['retrieved_at']
    (output/'extracted-source.json').write_text(json.dumps(page.to_dict(),indent=2,ensure_ascii=False),encoding='utf-8')
    profile = Path(tempfile.mkdtemp(prefix='olive-m2-research-final-'))
    os.environ['OLIVE_DATA_DIR'] = str(profile)
    services = ServiceContainer(lambda *args:None, None, data_dir=profile, migrate=False)
    try:
        await services.initialize()
        synthesizer = services.research.orchestrator.synthesizer
        old_session = ResearchSession(original['question'],
            sources=[ResearchSource(**s) for s in original['sources']],
            evidence=[ResearchEvidence(**e) for e in original['evidence']])
        model = services.model_router.route(RoutingRequest(role='research_synthesis'))
        old_review = await review_scope(services.ollama, model.name, old_session, original['findings'][-1:], old_session.evidence, 45)
        (output/'old-claims-new-review.json').write_text(json.dumps({'retained':old_review,'review':old_session.context},indent=2,ensure_ascii=False),encoding='utf-8')
        if recorded_only:
            print(json.dumps(old_session.context,ensure_ascii=False),flush=True)
            return
        source = ResearchSource(url,page.title,content_hash=page.content_hash,retrieved_at=page.retrieved_at,status='evidence')
        evidence = extract_evidence(page, source.id, original['plan']['subquestions'], question=original['question'])
        session = ResearchSession(original['question'],sources=[source],evidence=evidence,
            settings={'depth':'Quick'},context={'acceptance':'Separate live local synthesis of one public source; not the original stored answer'})
        session.plan = original['plan']
        print('Selected scopes:', [e.metadata['scope'] for e in evidence],flush=True)
        started = time.perf_counter()
        session.findings, session.final_report = await synthesizer.synthesize(session)
        session.transition('completed','Separate recorded/public-source scope check completed')
        services.research.repository.save(session)
        result={'classification':'Live local synthesis and fallible review; single public documentation fetch',
                'model':model.name,'seconds':time.perf_counter()-started,'raw_source_sha256':hashlib.sha256(raw).hexdigest(),
                'profile':str(profile),'session':session.to_dict()}
        (output/'new-research-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        (output/'new-answer.md').write_text(session.final_report,encoding='utf-8')
        print(session.final_report,flush=True)
        print('Review profile:',profile,flush=True)
    finally:
        await services.shutdown()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/ui-review/M2-final')
    parser.add_argument('--recorded-only',action='store_true')
    args=parser.parse_args()
    asyncio.run(run(args.output.resolve(),args.recorded_only))
