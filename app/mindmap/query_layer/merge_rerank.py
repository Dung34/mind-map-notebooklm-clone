"""Merge and rerank candidates from semantic/entity retrieval."""

from __future__ import annotations

from app.mindmap.query_layer.contracts import CandidateItem, FrameworkTag

_FRAMEWORK_SWOT_HINTS = {
    "SWOT": {"strength", "weakness", "opportunity", "threat", "n_a"},
    "Compare": {"compare", "vs"},
    "RootCause": {"rootcause", "cause"},
    "ProsCons": {"proscons"},
    "DeepDive": {"deepdive"},
}


def _framework_boost(item: CandidateItem, framework_tag: FrameworkTag) -> float:
    tag = framework_tag.lower()
    swot = (item.swot_category or "").strip().lower().replace(" ", "")
    if framework_tag == "SWOT" and swot in _FRAMEWORK_SWOT_HINTS["SWOT"]:
        return 0.25
    if framework_tag != "SWOT" and tag in (item.framework_tag or "").lower():
        return 0.20
    if framework_tag == "SWOT" and item.funnel_stage not in {"", "Unknown"}:
        return 0.1
    return 0.0


def merge_and_rerank(
    semantic_candidates: list[CandidateItem],
    entity_candidates: list[CandidateItem],
    *,
    framework_tag: FrameworkTag,
    top_k_final: int,
) -> list[CandidateItem]:
    merged: dict[str, CandidateItem] = {}
    for c in semantic_candidates + entity_candidates:
        existing = merged.get(c.candidate_id)
        if existing is None:
            merged[c.candidate_id] = c
            continue
        existing.semantic_score = max(existing.semantic_score, c.semantic_score)
        existing.entity_score = max(existing.entity_score, c.entity_score)
        if c.matched_entities:
            seen = set(existing.matched_entities)
            for m in c.matched_entities:
                if m not in seen:
                    existing.matched_entities.append(m)
                    seen.add(m)

    out: list[CandidateItem] = []
    for c in merged.values():
        c.framework_boost = _framework_boost(c, framework_tag)
        c.final_score = 0.55 * c.semantic_score + 0.30 * c.entity_score + 0.15 * c.framework_boost
        out.append(c)

    out.sort(key=lambda x: (x.final_score, x.semantic_score, x.entity_score, x.title), reverse=True)
    return out[: max(0, top_k_final)]

