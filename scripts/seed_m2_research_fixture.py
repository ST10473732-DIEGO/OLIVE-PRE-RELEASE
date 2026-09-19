"""Labelled source/evidence fixtures; no network requests or model work."""
from pathlib import Path
import os
import sys

if __name__ == '__main__':
    profile = Path(sys.argv[1]).resolve()
    if profile == (Path.home() / '.olive').resolve():
        raise SystemExit('Use an isolated fixture profile')
    os.environ['OLIVE_DATA_DIR'] = str(profile)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from olive.research.models import ResearchSession, ResearchSource, ResearchEvidence
    from olive.research.repository import ResearchRepository
    from olive.research.quarantine import DownloadQuarantine
    session = ResearchSession('Fixture: compare local test approaches', status='completed')
    source = ResearchSource('https://example.invalid/fixture-testing', 'Fixture testing notes', domain='example.invalid', status='evidence', content_hash='fixture-only')
    evidence = ResearchEvidence(source.id, 'What should a test verify?', 'Verify observable outcomes.', 'A fixture illustrates an outcome without contacting a website.', 0, 70)
    session.sources = [source]
    session.evidence = [evidence]
    session.findings = [{'text': 'Verify observable outcomes.', 'kind': 'supported', 'evidence_ids': [evidence.id]}]
    session.final_report = '# Fixture findings\n\nIllustrative review data, not live research evidence.\n\nVerify observable outcomes. [S1](https://example.invalid/fixture-testing)'
    session.activity = 'Fixture completed record; no website was contacted.'
    ResearchRepository(profile / 'research_sessions.json').save(session)
    DownloadQuarantine(profile / 'quarantine').store_download('https://example.invalid/fixture.txt', 'fixture.txt', 'text/plain', b'Clearly labelled inert download fixture. No network request was made.', approved=True)
