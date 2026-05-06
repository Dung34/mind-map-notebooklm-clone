"""Lightweight semantic retrieval on artifacts (token overlap based)."""

from __future__ import annotations

import math
import re

from app.mindmap.query_layer.contracts import CandidateItem

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tf(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) < 2:
            continue
        out[token] = out.get(token, 0.0) + 1.0
    return out


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    if dot <= 0:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def retrieve_semantic(
    query: str,
    candidates: list[CandidateItem],
    *,
    top_k: int,
) -> list[CandidateItem]:
    qtf = _tf(query)
    scored: list[CandidateItem] = []
    for c in candidates:
        score = _cosine(qtf, _tf(c.text))
        if score <= 0:
            continue
        c.semantic_score = score
        scored.append(c)
    scored.sort(key=lambda x: (x.semantic_score, x.title), reverse=True)
    return scored[: max(0, top_k)]

