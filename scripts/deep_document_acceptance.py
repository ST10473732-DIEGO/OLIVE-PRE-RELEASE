"""Real local DEEP image interpretation and native document retrieval."""
import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.evaluation.model_fixtures import vision_image

async def main():
    root = Path(tempfile.mkdtemp(prefix='olive-deep-'))
    async def deny(_):return ConfirmationResponse(False)
    s = ServiceContainer(lambda *a:None, deny, root/'profile', migrate=False)
    try:
        await s.initialize()
        chat_id = s.current_chat_id
        s.chat.update(chat_id, preset='deep')
        native = root/'sales.txt'
        native.write_text('Verified synthetic source: 2024 sales were 12 units; 2025 sales were 18 units.',encoding='utf-8')
        await s.knowledge.attach(chat_id,[str(native)],permanent=True)
        await s.chat.send(chat_id,'What was the percentage growth in sales? Cite the attached source.')
        text_result=s.chat.get(chat_id)['messages'][-1]
        assert '50' in text_result['content'] and text_result['sources'],text_result
        image=root/'button.png';image.write_bytes(base64.b64decode(vision_image()))
        await s.knowledge.attach(chat_id,[str(image)])
        await s.chat.send(chat_id,'Read the exact text on the attached image button; cite its filename.')
        image_result=s.chat.get(chat_id)['messages'][-1]
        assert 'SAVE' in image_result['content'],image_result
        assert any(r['filename']=='button.png' and r['origin_type'].startswith('vision_interpretation:') for r in image_result['sources'])
        assert not s.run_service.sessions and not s.workspace_repo.load_all()
        Path(sys.argv[1]).write_text(json.dumps({'native':text_result,'image':image_result},indent=2),encoding='utf-8')
        print('Native source retrieval and actual local vision-to-text synthesis passed.',flush=True)
    finally:await s.shutdown()

if __name__=='__main__':asyncio.run(main())
