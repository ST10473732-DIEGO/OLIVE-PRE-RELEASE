"""Bounded, fallible model review of paraphrase scope; not factual certification."""
import asyncio
import json
import re
from .planner import strict_json, UNTRUSTED_RULE

SCHEMA = {'type':'object','additionalProperties':False,'required':['assessments'],'properties':{
    'assessments':{'type':'array','maxItems':16,'items':{'type':'object','additionalProperties':False,
        'required':['index','verdict','reason'],'properties':{
            'index':{'type':'integer','minimum':0,'maximum':15},
            'verdict':{'type':'string','enum':['supported','wrong_subject','lost_condition','insufficient']},
            'reason':{'type':'string'}}}}}}


async def review_scope(ollama, model, session, findings, evidence, timeout):
    evidence_map = {e.id:e for e in evidence}
    original_findings = findings
    findings = [dict(f) for f in findings]
    for finding in findings:
        # A newly derived quantity is not a quotation/source assertion. This
        # relabels only; the independent scope review must still justify it.
        quantities = set(re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])', finding['text']))
        quoted = set(re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])', ' '.join(evidence_map[i].quote for i in finding['evidence_ids'])))
        if finding['kind'] == 'source_claim' and quantities - quoted:
            finding['kind'] = 'inference'
    exact = lambda f: any(f['text'].strip().strip('"') == evidence_map[i].quote.strip()
                          and not evidence_map[i].metadata.get('truncated') for i in f['evidence_ids'])
    proposals = [(i, f) for i, f in enumerate(findings) if not exact(f)]
    if not proposals:
        return findings
    cited = list(dict.fromkeys(eid for _,f in proposals for eid in f['evidence_ids']))
    payload = {'question':session.question,'untrusted_proposals':[
        {'index':i, 'finding':f} for i,f in proposals],
        'untrusted_evidence':[
            {'id':eid,'quote':evidence_map[eid].quote,'scope':evidence_map[eid].metadata.get('scope',''),
             'truncated':evidence_map[eid].metadata.get('truncated',False)} for eid in cited],
        'instructions':
        'Independently check each proposed finding against ONLY its cited excerpts. Valid IDs and shared words do not prove support. '
        'Identify the operation that owns each behaviour. A specialised helper, overload or callback does not establish a universal rule for its parent API. '
        'Preserve conditions, exceptions, negation and quantifiers. Reject subject changes as wrong_subject, broadened conditional behaviour as lost_condition. '
        'Judge each finding as a standalone statement; do not silently borrow a restriction from another finding. A conditional helper dispatch does not support saying all other types use that helper. Missing behaviour is not evidence of a fallback rule. '
        'If the main definition or required context is missing, or support is ambiguous, use insufficient. Do not use background knowledge to fill gaps. '
        'For a finding explicitly labelled inference, check the deduction from cited premises and values supplied in the user question. Elementary arithmetic and logical substitution are allowed and need not appear verbatim in the excerpt. '
        'Keep that finding labelled inference. Do not infer undocumented API type contracts, preconditions, fallback behaviour, broader domains or empirical facts. '
        'Use supported only when the excerpts support the whole statement with its stated scope; this remains a model judgement, not verification.'}
    failure_kind = None
    try:
        response = await asyncio.wait_for(ollama.chat_once(model, [
            {'role':'system','content':'Review evidence scope, not writing style. '+UNTRUSTED_RULE},
            {'role':'user','content':json.dumps(payload)}],
            options={'temperature':0,'num_predict':2400},format=SCHEMA,
            think='low' if model.startswith('gpt-oss') else False), timeout=min(timeout,45))
        value = strict_json(response)
        if not isinstance(value,dict) or set(value) != {'assessments'} or not isinstance(value['assessments'],list):
            raise ValueError('Invalid scope review')
        assessments = value['assessments']
        expected = {i for i,_ in proposals}
        if len(assessments) != len(expected):
            raise ValueError('Incomplete scope review')
        seen = set()
        for a in assessments:
            if (not isinstance(a,dict) or set(a) != {'index','verdict','reason'} or type(a['index']) is not int
                or a['index'] not in expected or a['index'] in seen
                or a['verdict'] not in {'supported','wrong_subject','lost_condition','insufficient'}
                or not isinstance(a['reason'],str) or not 1 <= len(a['reason']) <= 2000):
                raise ValueError('Invalid scope assessment')
            seen.add(a['index'])
    except asyncio.CancelledError:
        raise
    except Exception as error:
        failure_kind = type(error).__name__
        assessments = [{'index':i,'verdict':'insufficient','reason':'Scope review unavailable or invalid; paraphrase withheld.'} for i,_ in proposals]
    session.context['synthesis_review'] = {'kind':'fallible_model_scope_review',
        'proposed_findings':original_findings,'reviewed_findings':findings,'assessments':assessments,'failure_kind':failure_kind}
    rejected = {a['index'] for a in assessments if a['verdict'] != 'supported'}
    accepted = [f for i,f in enumerate(findings) if i not in rejected]
    if rejected:
        ids = list(dict.fromkeys(eid for i in sorted(rejected) for eid in findings[i]['evidence_ids']))[:8]
        accepted.append({'text':'The selected evidence does not establish an additional proposed conclusion with sufficient scope and conditions. That conclusion has been withheld; inspect the recorded excerpts.',
                         'kind':'uncertain','evidence_ids':ids})
    return accepted
