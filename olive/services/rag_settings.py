from __future__ import annotations

DEFAULTS = {"top_k": 6, "lexical_weight": 0.35, "semantic_weight": 0.65, "relevance_threshold": 0.08}


def validate_rag_settings(top_k, lexical_weight, semantic_weight, relevance_threshold) -> dict:
    values = {"top_k": int(top_k), "lexical_weight": float(lexical_weight),
              "semantic_weight": float(semantic_weight), "relevance_threshold": float(relevance_threshold)}
    if not 1 <= values["top_k"] <= 20: raise ValueError("top_k must be between 1 and 20")
    if not 0 <= values["lexical_weight"] <= 1 or not 0 <= values["semantic_weight"] <= 1:
        raise ValueError("Retrieval weights must be between 0 and 1")
    if values["lexical_weight"] + values["semantic_weight"] <= 0:
        raise ValueError("At least one retrieval weight must be greater than zero")
    if not 0 <= values["relevance_threshold"] <= 1:
        raise ValueError("Relevance threshold must be between 0 and 1")
    return values
