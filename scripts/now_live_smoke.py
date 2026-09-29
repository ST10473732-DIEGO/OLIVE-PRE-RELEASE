"""Opt-in live NOW retrieval/synthesis; isolated profile, no model pulls.
Run: python scripts/now_live_smoke.py --live [--synthesize]
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.services.now_service import PRIMARY, HEAVY
from olive.research.models import timestamp


async def run(synthesize, questions=None):
    async def approve(_):
        return ConfirmationResponse(True)
    records = []
    with tempfile.TemporaryDirectory(prefix='olive-now-live-') as profile:
        s = ServiceContainer(lambda *args: None, approve, data_dir=profile, migrate=False)
        s.permissions.save({'network.search': 'allow', 'network.read': 'allow'})
        try:
            if synthesize:
                await s.model_registry.refresh()
            for question in questions or ('What is the weather in Cape Town right now?',
                             'What is the latest news in South Africa today?',
                             "What is Elon Musk's current net worth?",
                             'Compare current reports about NVIDIA and AMD today.'):
                record = {'question': question, 'started_at': timestamp()}
                try:
                    if synthesize:
                        chat = s.chats[s.current_chat_id]
                        s.presets.apply(chat, 'now')
                        await s.chat.send(chat.id, question)
                        record['answer'] = chat.messages[-1].to_dict()
                    else:
                        sources, failures = await s.now.evidence(question)
                        record.update(sources=sources, page_failures=failures)
                    record['status'] = 'completed' if synthesize else 'retrieved'
                    record['acceptance'] = 'Manual comparison with source payloads required; completion does not establish answer sufficiency.'
                except Exception as error:
                    record.update(status='failed', error=str(error), error_type=type(error).__name__)
                record['finished_at'] = timestamp()
                records.append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
        finally:
            await s.shutdown()
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--synthesize', action='store_true')
    parser.add_argument('--question', action='append', help='Public question; repeat for several checks')
    args = parser.parse_args()
    asyncio.run(run(args.synthesize, args.question))
