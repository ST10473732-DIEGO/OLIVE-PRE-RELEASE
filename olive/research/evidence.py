"""Evidence selection and provenance checks, independent of model instructions."""

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit
from .models import ResearchEvidence

STOP = set(
    "the and for are what how does with from this that research latest current compare about sources evidence".split()
)


def terms(text):
    return {word.removesuffix("s") for word in re.findall(r"[\w-]{3,}", text.lower()) if word not in STOP}


def source_quality(page):
    domain = urlsplit(page.url).hostname
    return {
        "domain": domain,
        "has_author": bool(page.author),
        "publication_metadata": bool(page.publication_date),
        "retrieved_at": page.retrieved_at,
        "source_type_hint": "documentation"
        if domain.startswith("docs.") or "/docs" in page.url
        else "webpage",
        "primary_source": "not independently established",
        "independent_corroboration": 0,
    }


def rank_sources(results, question, freshness="any"):
    query_terms = terms(question)

    def score(result):
        overlap = len(query_terms & terms(result.title + " " + result.snippet))
        recency = 0
        if freshness != "any" and result.publication_date:
            try:
                date = datetime.fromisoformat(result.publication_date.replace("Z", "+00:00"))
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - date).days
                recency = 2 / (1 + age / 30) if age >= 0 else 0
            except (ValueError, TypeError):
                recency = 0
        return -(overlap + recency + 1 / max(1, result.rank))

    return sorted(results, key=score)


def extract_evidence(page, source_id, subquestions, limit=4, *, question=""):
    from .passages import scoped_passages
    candidates = []
    primary_terms = terms(question)
    for start, end, scope, kind, truncated in scoped_passages(page):
        text = page.text[start:end]
        if len(text) < 20:
            continue
        for question in subquestions:
            query_terms = terms(question)
            score = len(query_terms & terms(text)) / max(1, len(query_terms))
            if score:
                quote = text
                candidates.append(
                    ResearchEvidence(
                        source_id,
                        question,
                        quote.split("\n")[0][:200],
                        quote,
                        start,
                        end,
                        score=score,
                        metadata={"content_hash": page.content_hash, "relationship": "source_excerpt",
                                  "scope":scope,"scope_kind":kind,"truncated":truncated,
                                  "requested_definition":kind == 'definition' and any(
                                      bool(terms(name) & primary_terms) for name in re.findall(r'([A-Za-z_]\w*)\s*\(',scope))},
                    )
                )
    selected, seen = [], set()
    definitions=[section['start'] for section in page.metadata.get('sections',[]) if section['kind']=='definition']
    if limit > 1 and definitions and any(item.metadata['requested_definition'] for item in candidates):
        # API definitions inherit module-level qualifiers. Reserve a bounded
        # overview rather than filling every slot with neighbouring helper APIs.
        end=min(min(definitions),2400)
        if end >= 40:
            candidates.append(ResearchEvidence(source_id,question,page.title[:200],page.text[:end],0,end,score=0,
                metadata={'content_hash':page.content_hash,'relationship':'source_excerpt','scope':page.title,
                          'scope_kind':'document_overview','truncated':end<min(definitions),'requested_definition':False}))
    anchors = {term for item in candidates if item.metadata['requested_definition']
               for name in re.findall(r'([A-Za-z_]\w*)\s*\(',item.metadata['scope']) for term in terms(name)}
    # Rank relevance, never factual support. Reserve the requested definition before
    # high-overlap specialised helpers; keep neighbouring qualifiers in each excerpt.
    for evidence in sorted(candidates, key=lambda item: (not item.metadata['requested_definition'],
            item.metadata['scope_kind'] != 'document_overview',
            bool(anchors) and not bool(anchors & terms(item.quote)), -item.score)):
        if evidence.start not in seen:
            selected.append(evidence)
            seen.add(evidence.start)
        if len(selected) >= limit:
            break
    return selected


def potential_conflicts(evidence):
    conflicts = []
    for index, first in enumerate(evidence):
        for second in evidence[index + 1 :]:
            if first.source_id == second.source_id or first.subquestion != second.subquestion:
                continue
            overlap = terms(first.quote) & terms(second.quote)
            if len(overlap) < 3:
                continue
            negative = lambda text: bool(re.search(r"\b(not|never|unsupported|cannot)\b", text, re.I))
            if negative(first.quote) != negative(second.quote):
                conflicts.append(
                    {
                        "evidence_ids": [first.id, second.id],
                        "status": "potential_disagreement",
                        "note": "Different wording/polarity; compare scope and date before concluding contradiction",
                    }
                )
    return conflicts[:20]
