"""Entity matching against entities.json for Stage 3 query layer."""

from __future__ import annotations

import re
from typing import Any

from app.mindmap.query_layer.contracts import CandidateItem

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
_STOPWORDS = {
    # Vietnamese generic query terms
    "phan",
    "tich",
    "doanh",
    "nghiep",
    "chien",
    "luoc",
    "danh",
    "gia",
    "tong",
    "quan",
    "lien",
    "quan",
    "yeu",
    "to",
    "kha",
    "nang",
    # English generic query terms
    "company",
    "business",
    "analysis",
    "strategic",
    "strategy",
    "evaluate",
    "assessment",
    "overview",
    "related",
    "factors",
    "capability",
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "about",
    "this",
    "that",
    "over",
    "next",
    "years",
}


def _tokens(text: str) -> set[str]:
    return {x.lower() for x in _TOKEN_RE.findall(text) if len(x) >= 3 and x.lower() not in _STOPWORDS}


def _entity_token_index(entities_doc: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for node_id, rows in (entities_doc.get("entities_by_leaf") or {}).items():
        toks: set[str] = set()
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                text = str(r.get("text") or "").strip()
                toks.update(_tokens(text))
        if toks:
            out[str(node_id)] = toks
    return out


def score_entity_matches(
    query: str,
    candidates: list[CandidateItem],
    entities_doc: dict[str, Any],
    *,
    top_k: int,
) -> list[CandidateItem]:
    query_toks = _tokens(query)
    if not query_toks:
        return []

    idx = _entity_token_index(entities_doc)
    scored: list[CandidateItem] = []
    for c in candidates:
        entity_toks = idx.get(c.source_ref, set())
        if not entity_toks:
            continue
        inter = sorted(query_toks & entity_toks)
        if not inter:
            continue
        denom = max(1, min(len(query_toks), len(entity_toks)))
        c.entity_score = len(inter) / denom
        c.matched_entities = inter[:10]
        scored.append(c)

    scored.sort(key=lambda x: (x.entity_score, x.title), reverse=True)
    return scored[: max(0, top_k)]

