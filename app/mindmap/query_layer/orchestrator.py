"""Orchestrator for Stage 3 query layer."""

from __future__ import annotations

from app.mindmap.query_layer.artifact_loader import (
    build_candidates_from_artifacts,
    load_stage3_artifacts,
)
from app.mindmap.query_layer.contracts import QueryLayerInput, QueryLayerResult
from app.mindmap.query_layer.entity_matcher import score_entity_matches
from app.mindmap.query_layer.framework_selector import select_framework
from app.mindmap.query_layer.merge_rerank import merge_and_rerank
from app.mindmap.query_layer.overview_context import build_overview_context_candidates
from app.mindmap.query_layer.semantic_retriever import retrieve_semantic


def run_query_layer(input_data: QueryLayerInput) -> QueryLayerResult:
    query = input_data.normalized_query()
    artifacts = load_stage3_artifacts(input_data.artifact_root)
    if input_data.retrieval_mode == "overview":
        selected, overview_debug = build_overview_context_candidates(
            artifacts,
            top_k_final=input_data.top_k_final,
            rep_ratio=input_data.overview_rep_ratio,
        )
        debug = {
            "artifact_root": artifacts["artifact_root"],
            "counts": {
                "selected_context": len(selected),
            },
            "framework_rules": [],
            "score_formula": "0.85*semantic + 0.15*representative_boost",
            "overview": overview_debug,
        }
        return QueryLayerResult(
            query=query,
            framework_tag="SWOT",
            intent_confidence=1.0,
            selected_context=selected,
            semantic_candidates=[],
            entity_candidates=[],
            debug=debug,
        )

    selection = select_framework(query)
    base_candidates = build_candidates_from_artifacts(artifacts)

    semantic_candidates = retrieve_semantic(
        query,
        [c for c in base_candidates],
        top_k=input_data.top_k_semantic,
    )
    entity_candidates = score_entity_matches(
        query,
        [c for c in base_candidates],
        artifacts["entities"],
        top_k=input_data.top_k_entity,
    )
    selected = merge_and_rerank(
        semantic_candidates,
        entity_candidates,
        framework_tag=selection.framework_tag,
        top_k_final=input_data.top_k_final,
    )

    debug = {
        "artifact_root": artifacts["artifact_root"],
        "counts": {
            "base_candidates": len(base_candidates),
            "semantic_candidates": len(semantic_candidates),
            "entity_candidates": len(entity_candidates),
            "selected_context": len(selected),
        },
        "framework_rules": selection.matched_rules,
        "score_formula": "0.55*semantic + 0.30*entity + 0.15*framework_boost",
    }
    return QueryLayerResult(
        query=query,
        framework_tag=selection.framework_tag,
        intent_confidence=selection.intent_confidence,
        selected_context=selected,
        semantic_candidates=semantic_candidates,
        entity_candidates=entity_candidates,
        debug=debug,
    )

