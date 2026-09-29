"""Chat-native research: local document evidence plus explicitly requested public evidence."""
import re

from .now_weather import NowError
from .now_service import NowPrepared
from ..research.models import timestamp
from ..research.planner import freshness_requirement
from ..research.passages import MAX_EXCERPT
from .rag_service import RAGResult

# Only these public concepts may be derived from PRIVATE evidence for an
# explicitly requested online comparison. Arbitrary names, IDs and excerpts
# cannot escape via keyword extraction. Unknown topics require user wording.
PUBLIC_TOPICS = ('quantum computing', 'cybersecurity', 'artificial intelligence', 'machine learning',
    'renewable energy', 'solar energy', 'climate change', 'electric vehicles', 'public health',
    'education', 'inflation', 'interest rates', 'cloud computing', 'data protection', 'zero trust',
    'software engineering', 'Python', 'NVIDIA', 'AMD', 'SpaceX', 'Bitcoin')


def research_intent(chat, text, override=''):
    """Cheap explicit-intent path; existing semantic interpreter remains fallback."""
    value = text.strip()
    if re.search(r'\b(?:create|export|save|write)\b.*\b(?:full |research )report\b', value, re.I):
        return ''  # Existing report/artifact workflow remains available.
    if re.fullmatch(r'(?:hi|hello|hey|thanks|thank you|ok|okay)[!. ]*', value, re.I):
        return ''
    docs = bool(getattr(chat, 'documents', []))
    explicit_document = bool(re.search(r'\b(pdf|document|report|attached|attachment|chapter|file|findings)\b', value, re.I))
    # Ordinary intervening turns do not erase the last document investigation.
    # Pronouns need that context AND a reference-like question, not just "this
    # error" or the impersonal "what does it cost to run ...".
    prior_document = any(m.role == 'assistant' and m.provider.get('research_kind') in {'documents', 'combined'}
                         for m in getattr(chat, 'messages', []))
    followup = prior_document and bool(re.search(
        r'\b(?:what does (?:it|this|that) (?:say|show|recommend|contain)|'
        r'(?:it|this|that) (?:say|says|provide|provides|support|supports|recommend|recommends)|'
        r'(?:summari[sz]e|explain|compare|verify|research) (?:it|this|that|those)|'
        r'(?:it|this|that|those) compare|'
        r'(?:its|their) (?:cost|evidence|recommendation)|'
        r'what about (?:the )?(?:cost|evidence|recommendation))\b', value, re.I))
    document_request = docs and (explicit_document or followup)
    explicit = bool(override or re.search(r'\b(research|look into|find (?:\w+ )?sources|verify|compare (?:\w+ )?sources|investigate|find the latest information|multiple sources|several sources)\b', value, re.I))
    if not (explicit or document_request):
        return ''
    external = bool(re.search(r'\b(online|web|internet|current|today|latest|newer|still (?:accurate|current)|industry practice)\b', value, re.I))
    if document_request:
        return 'combined' if external else 'documents'
    return 'web'


class ChatResearchService:
    def __init__(self, services):
        self.s = services

    async def document_evidence(self, chat, question):
        if any(not ref.indexed for ref in chat.documents):
            raise ValueError('Wait for attached documents to finish indexing, or remove failed attachments')
        hits = await self.s.rag.retrieve(chat.id, question, limit=6)
        attached = {ref.id for ref in chat.documents}
        hits = [h for h in hits if h.document_id in attached]
        overview = bool(re.search(r'\b(research|summari[sz]e|main findings|recommendation|overview|compare|still accurate|still current)\b', question, re.I))
        if overview:
            # Include bounded opening evidence for broad document questions whose
            # vocabulary does not occur literally in the file. Never load a full PDF.
            seen = {(h.document_id, h.chunk_index) for h in hits}
            for ref in chat.documents[:4]:
                for c in self.s.rag.store.document_excerpt(chat.id, ref.id, 4):
                    if (c.document_id, c.chunk_index) not in seen:
                        hits.append(RAGResult(c.document_id, c.document_name, c.page_number, c.chunk_index,
                            c.source_type, c.content, 0, origin_type=c.origin_type))
        sources = []
        for hit in hits[:4]:
            sid = f'D{len(sources) + 1}'
            sources.append({**hit.source_dict(), 'id': sid, 'label': sid + ' · ' + hit.source_label,
                'source': hit.document_name, 'title': hit.source_label, 'kind': 'document_excerpt',
                'evidence': hit.content[:MAX_EXCERPT], 'retrieved_at': timestamp(), 'published_at': None,
                'provider': 'Local document index', 'trust_label': 'untrusted_document'})
        return sources

    def public_terms(self, question, sources):
        # A bounded explicit topic supplied by the user is safe to send. Never
        # append history or text extracted from an attachment to this query.
        match = re.search(r'\b(?:about|regarding|on the topic of)\s+(.+)', question, re.I)
        if match and not re.search(r'\b(it|this|that|document|pdf|report)\b', match.group(1), re.I):
            return match.group(1).strip(' ?.\n')[:200]
        evidence = '\n'.join(s['evidence'] for s in sources)
        topics = [topic for topic in PUBLIC_TOPICS if re.search(r'\b' + re.escape(topic) + r'\b', question + '\n' + evidence, re.I)]
        return ' '.join(topics[:3])

    async def stream(self, chat, text, mode):
        self.s.now.require_local()
        sources, failures = [], []
        question = text
        # Locally bind a pronoun to the prior user request only. It is never used
        # as a public search query for a document comparison.
        if re.match(r'^(what|how|does|and)\b', text, re.I):
            prior = next((m.provider.get('research_question') for m in reversed(chat.messages)
                          if m.role == 'assistant' and m.provider.get('research_question')), '')
            if prior:
                question += '\nPrevious user question (context only): ' + prior[:1000]
        if mode in {'documents', 'combined'}:
            self.s.publish('interaction_activity', {'chat_id': chat.id, 'message': 'Reading attached document evidence…'})
            sources = await self.document_evidence(chat, question)
            if not sources:
                async def missing():
                    yield 'I could not find evidence for that question in the attached document index. The document may not contain the information, or extraction/retrieval may be incomplete. I cannot establish the answer from the document.'
                return missing(), NowPrepared([], {'runtime': 'Ollama', 'model': '', 'preset': chat.preset,
                    'research_kind': mode, 'research_question': text, 'inference_performed': False})
        public_query = ''
        if mode in {'web', 'combined'}:
            public_query = text if mode == 'web' else self.public_terms(text, sources)
            if not public_query:
                async def clarify():
                    yield 'Name the public topic or search terms to use for this comparison. I have kept the attached document local and have not sent its contents to search providers.'
                return clarify(), NowPrepared(sources, {'runtime': 'Ollama', 'model': '', 'preset': chat.preset,
                    'research_kind': mode, 'research_question': text, 'inference_performed': False})
            if mode == 'combined':
                public_query += ' current information'
            elif re.match(r'^(what about|how about|and)\b', text, re.I):
                previous = next((m.provider.get('public_question') for m in reversed(chat.messages)
                                 if m.role == 'assistant' and m.provider.get('research_kind') == 'web'), '')
                if previous:
                    public_query = previous[:600] + ' ' + text
            web, failures = await self.s.now.evidence(public_query, require_fresh=freshness_requirement(public_query) != 'any')
            sources.extend(web[:4] if mode == "combined" else web)
        provider = {'runtime': 'Ollama', 'model': chat.model, 'preset': chat.preset,
            'research_kind': mode, 'research_question': text[:1000], 'public_question': public_query,
            'retrieved_at': timestamp(), 'page_failures': len(failures)}
        if chat.preset == 'uncensored':
            choice = self.s.uncensored_router.select(text)
            provider.update(tier=choice.tier, route_reason=choice.reason)
        return await self.s.now.synthesize(chat, question, sources, failures, provider)
