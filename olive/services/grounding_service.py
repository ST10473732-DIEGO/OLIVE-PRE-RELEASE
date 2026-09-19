from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(slots=True)
class GroundingResult:
    status: str
    score: float
    supporting_sources: list[dict]
    explanation: str

    def to_dict(self) -> dict:
        return asdict(self)


class GroundingService:
    def analyze(self, answer: str, sources: list) -> GroundingResult:
        if not sources:
            return GroundingResult("unavailable", 0.0, [], "No document context was supplied")
        answer_terms = _meaningful_terms(answer)
        if not answer_terms:
            return GroundingResult("unavailable", 0.0, [], "No comparable answer terms")
        source_terms = set()
        supporting = []
        for source in sources:
            terms = _meaningful_terms(source.content)
            source_terms.update(terms)
            overlap = len(answer_terms & terms) / len(answer_terms)
            if overlap >= 0.1:
                supporting.append(source.source_dict())
        score = len(answer_terms & source_terms) / len(answer_terms)
        # A high bar avoids calling answers with a substantial unsupported clause "strong".
        status = "strong" if score >= 0.65 else "partial" if score >= 0.20 else "weak"
        return GroundingResult(
            status, round(score, 4), supporting,
            "Estimated from term overlap with retrieved context; this is not factual proof",
        )


def _meaningful_terms(text: str) -> set[str]:
    stop = {"the", "and", "for", "that", "with", "this", "from", "are", "was", "were", "have", "has"}
    return {term for term in re.findall(r"[a-z0-9-]+", text.lower()) if len(term) > 2 and term not in stop}
