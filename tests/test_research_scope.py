"""Structural extraction and scope-review regressions, with labelled mock inference."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from olive.research.extraction import extract_page
from olive.research.evidence import extract_evidence
from olive.research.models import ResearchSession, ResearchSource
from olive.research.citations import ResearchSynthesizer, validate_findings

CASES = [
    ('decode', 'asciiDecoder', 'Decode accepts encoded input.',
     'When ASCII mode is selected, decode delegates to asciiDecoder for detailed errors.',
     'asciiDecoder rejects non-ASCII bytes. This helper runs only in ASCII mode.',
     'decode always rejects non-ASCII bytes.'),
    ('compareValues', 'compareLists', 'compareValues checks value equality.',
     'For two lists, compareValues uses compareLists to describe differences.',
     'compareLists raises an error for non-list arguments. Other values use ordinary equality.',
     'compareValues requires every argument to be a list.'),
]


def material(case):
    parent, helper, definition, condition, specialised, _ = case
    page = extract_page(f'<main><h1>API reference</h1><dl><dt>{parent}(value)</dt><dd>'
        f'<p>{definition}</p><p>{condition}</p></dd><dt>{helper}(value)</dt>'
        f'<dd><p>{specialised}</p></dd></dl></main>', 'https://example.invalid/docs')
    source = ResearchSource(page.url, page.title, content_hash=page.content_hash, status='read')
    evidence = extract_evidence(page, source.id, [specialised, f'What does {parent} do?'], question=f'Explain {parent}')
    return page, source, evidence


class ExtractionScopeTests(unittest.TestCase):
    def test_requested_definition_keeps_module_wide_qualifiers(self):
        page=extract_page('<main><h1>Number API</h1><p>Unless explicitly stated otherwise, every function returns a decimal value.</p><dl><dt>root(value)</dt><dd>Return the square root of value.</dd><dt>helper(value)</dt><dd>Use root(value) for another calculation.</dd></dl></main>','https://example.invalid/docs')
        evidence=extract_evidence(page,'fixture',['What does root(9) return?'],limit=2,question='What does root(9) return?')
        self.assertEqual(evidence[0].metadata['scope_kind'],'definition')
        self.assertEqual(evidence[1].metadata['scope_kind'],'document_overview')
        self.assertIn('every function returns a decimal',evidence[1].quote)
        self.assertEqual(page.text[evidence[1].start:evidence[1].end],evidence[1].quote)
    def test_main_definition_keeps_its_conditions_ahead_of_helper_overlap(self):
        for case in CASES:
            with self.subTest(parent=case[0]):
                page, _, evidence = material(case)
                self.assertIn(case[2], evidence[0].quote)
                self.assertIn(case[3], evidence[0].quote)
                self.assertNotIn(case[4], evidence[0].quote)
                self.assertIn(case[0], evidence[0].metadata['scope'])
                for item in evidence:
                    self.assertEqual(page.text[item.start:item.end], item.quote)

    def test_shared_words_and_valid_ids_are_not_factual_verification(self):
        _, source, evidence = material(CASES[0])
        helper = next(e for e in evidence if CASES[0][1] in e.metadata['scope'])
        finding = {'text':CASES[0][-1], 'kind':'source_claim', 'evidence_ids':[helper.id]}
        # Deliberately passes the provenance-only validator. Scope review is separate.
        self.assertEqual(validate_findings({'findings':[finding]},[source],evidence),[finding])


class ScopeReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_premise_repair_is_bounded_and_independently_reviewed(self):
        page = extract_page('<main><h1>Number API</h1><p>Unless stated otherwise, functions return decimal values.</p><dl><dt>root(value)</dt><dd>Return the square root of value.</dd></dl></main>', 'https://example.invalid/docs')
        source = ResearchSource(page.url, page.title, content_hash=page.content_hash, status='read')
        evidence = extract_evidence(page, source.id, ['What does root(9) return?'], limit=2, question='What does root(9) return?')
        claim = 'root(9) returns the decimal value 3.0.'
        proposed = {'findings': [{'text': claim, 'kind': 'inference', 'evidence_ids': ['E1']}]}
        corrected = {'findings': [{'text': claim, 'kind': 'inference', 'evidence_ids': ['E1', 'E2']}]}
        insufficient = {'assessments': [{'index': 0, 'verdict': 'insufficient', 'reason': 'The cited definition omits the return-type premise.'}]}
        for verdict in ('supported', 'insufficient'):
            with self.subTest(final_review=verdict):
                final_review = {'assessments': [{'index': 0, 'verdict': verdict, 'reason': 'Independent second review.'}]}
                ollama = SimpleNamespace(chat_once=AsyncMock(side_effect=[json.dumps(value) for value in (proposed, insufficient, corrected, final_review)]))
                session = ResearchSession('What does root(9) return?', sources=[source], evidence=evidence)
                findings, report = await ResearchSynthesizer(ollama, SimpleNamespace(route=lambda _: SimpleNamespace(name='fixture'))).synthesize(session)
                self.assertEqual(ollama.chat_once.await_count, 4)
                self.assertEqual(len(session.context['synthesis_review_attempts']), 2)
                if verdict == 'supported':
                    self.assertEqual(findings[0]['kind'], 'inference')
                    self.assertEqual(set(findings[0]['evidence_ids']), {item.id for item in evidence})
                else:
                    self.assertEqual(findings[0]['kind'], 'uncertain')
                    self.assertNotIn(claim, report)

    async def test_specialist_behaviour_is_withheld_when_review_detects_scope_expansion(self):
        for case in CASES:
            with self.subTest(parent=case[0]):
                _, source, evidence = material(case)
                helper_index = next(i for i,e in enumerate(evidence) if case[1] in e.metadata['scope'])
                proposed = {'findings':[{'text':case[-1],'kind':'source_claim','evidence_ids':[f'E{helper_index+1}']}]}
                review = {'assessments':[{'index':0,'verdict':'wrong_subject','reason':'The stated restriction belongs to the specialised helper, not all parent calls.'}]}
                ollama = SimpleNamespace(chat_once=AsyncMock(side_effect=[json.dumps(proposed),json.dumps(review)]))
                session = ResearchSession(f'Explain {case[0]}', sources=[source], evidence=evidence)
                result, report = await ResearchSynthesizer(ollama,SimpleNamespace(route=lambda _:SimpleNamespace(name='fixture'))).synthesize(session)
                self.assertEqual(result[0]['kind'],'uncertain')
                self.assertNotIn(case[-1],report)
                self.assertEqual(session.context['synthesis_review']['proposed_findings'][0]['text'],case[-1])
                payload=json.loads(ollama.chat_once.call_args_list[1].args[1][1]['content'])
                self.assertIn(case[1],payload['untrusted_evidence'][0]['scope'])

    async def test_missing_review_never_promotes_paraphrase_to_verified_claim(self):
        _, source, evidence = material(CASES[1])
        proposed={'findings':[{'text':'compareValues checks equality.','kind':'source_claim','evidence_ids':['E1']}]}
        ollama=SimpleNamespace(chat_once=AsyncMock(side_effect=[json.dumps(proposed),TimeoutError()]))
        session=ResearchSession('Explain compareValues',sources=[source],evidence=evidence)
        result,_=await ResearchSynthesizer(ollama,SimpleNamespace(route=lambda _:SimpleNamespace(name='fixture'))).synthesize(session)
        self.assertEqual(result[0]['kind'],'uncertain')
        self.assertEqual(session.context['synthesis_review']['assessments'][0]['verdict'],'insufficient')
