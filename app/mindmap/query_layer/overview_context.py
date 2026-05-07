"""Build queryless overview context from cluster artifacts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.mindmap.query_layer.contracts import CandidateItem
from app.mindmap.vector_loader import (
    LoadedVectors,
    NotFoundVectorsError,
    load_vectors_by_chunk_ids,
    load_vectors_by_run_id,
    load_vectors_by_website,
)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _load_vectors_for_scope(clusters_top: dict[str, Any]) -> LoadedVectors | None:
    scope = clusters_top.get("scope") or {}
    notebooklm_id = str(scope.get("notebooklm_id") or "").strip()
    if not notebooklm_id:
        return None

    scope_mode = str(scope.get("scope_mode") or "").strip().lower()
    try:
        if scope_mode == "by_website":
            website = str(scope.get("website") or "").strip()
            if not website:
                return None
            return load_vectors_by_website(notebooklm_id=notebooklm_id, website=website)
        if scope_mode == "by_run_id":
            run_id = str(scope.get("run_id") or "").strip()
            if not run_id:
                return None
            return load_vectors_by_run_id(notebooklm_id=notebooklm_id, run_id=run_id)
        if scope_mode == "by_chunk_ids":
            chunk_ids = [str(x) for x in (scope.get("chunk_ids") or []) if str(x).strip()]
            if not chunk_ids:
                return None
            return load_vectors_by_chunk_ids(notebooklm_id=notebooklm_id, chunk_ids=chunk_ids)
    except (NotFoundVectorsError, Exception):
        return None
    return None


def _build_topic_lookup(topics_doc: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for key, value in topics_doc.items():
        if key in {"schema_version", "mindmap_run_id"} or not isinstance(value, dict):
            continue
        label = _safe_int(value.get("cluster_label"), default=10**9)
        if label == 10**9:
            continue
        out[label] = value
    return out


def _item_from_chunk(
    *,
    chunk_id: str,
    cluster_label: int,
    topic: dict[str, Any],
    rank_in_cluster: int,
    source: str,
    loaded: LoadedVectors | None,
) -> CandidateItem:
    title = str(topic.get("title") or f"Cluster {cluster_label}").strip()
    summary = str(topic.get("summary") or "").strip()
    notes = str(topic.get("ms_notes") or "").strip()

    chunk_text = ""
    if loaded is not None:
        meta = loaded.meta_by_id.get(chunk_id) or {}
        chunk_text = str(meta.get("chunk_text") or "").strip()

    text = chunk_text or " ".join(x for x in (summary, notes) if x).strip() or title
    # Stable pseudo relevance: representative first, earlier rank gets slightly higher score.
    pseudo_semantic = max(0.0, 1.0 - 0.03 * max(0, rank_in_cluster))
    return CandidateItem(
        candidate_id=f"chunk::{chunk_id}",
        source="topic_entry",
        source_ref=f"cluster_{cluster_label}",
        title=title,
        text=text,
        swot_category=str(topic.get("swot_category") or "N_A") or "N_A",
        funnel_stage=str(topic.get("funnel_stage") or "Unknown") or "Unknown",
        framework_tag=source,
        semantic_score=pseudo_semantic,
    )


def _dedupe_keep_best(items: list[CandidateItem]) -> list[CandidateItem]:
    best: dict[str, CandidateItem] = {}
    for item in items:
        prev = best.get(item.candidate_id)
        if prev is None or item.semantic_score > prev.semantic_score:
            best[item.candidate_id] = item
    return list(best.values())


def build_overview_context_candidates(
    artifacts: dict[str, Any],
    *,
    top_k_final: int,
    rep_ratio: float,
) -> tuple[list[CandidateItem], dict[str, Any]]:
    topics_doc = artifacts.get("topics") or {}
    clusters_top = artifacts.get("clusters_top") or {}
    clusters = clusters_top.get("clusters") or []
    if not isinstance(topics_doc, dict) or not isinstance(clusters, list):
        return [], {"reason": "invalid_artifacts"}

    loaded = _load_vectors_for_scope(clusters_top) if isinstance(clusters_top, dict) else None
    topic_lookup = _build_topic_lookup(topics_doc)
    total_slots = max(0, int(top_k_final))
    if total_slots <= 0:
        return [], {"reason": "top_k_final_le_zero"}

    rep_slots = max(0, min(total_slots, int(round(total_slots * max(0.0, min(1.0, rep_ratio))))))
    cov_slots = max(0, total_slots - rep_slots)

    rep_items: list[CandidateItem] = []
    cov_items: list[CandidateItem] = []
    cluster_sizes: list[tuple[int, int, list[str], set[str]]] = []

    for cl in clusters:
        if not isinstance(cl, dict):
            continue
        label = _safe_int(cl.get("label"), default=10**9)
        if label == 10**9:
            continue
        topic = topic_lookup.get(label)
        if topic is None:
            continue
        all_chunk_ids = [str(x) for x in (cl.get("chunk_ids") or []) if str(x).strip()]
        if not all_chunk_ids:
            continue
        rep_ids = [str(x) for x in (topic.get("representative_chunk_ids") or []) if str(x).strip()]
        rep_set = set(rep_ids)
        cluster_sizes.append((label, len(all_chunk_ids), all_chunk_ids, rep_set))

        for idx, cid in enumerate(rep_ids):
            rep_items.append(
                _item_from_chunk(
                    chunk_id=cid,
                    cluster_label=label,
                    topic=topic,
                    rank_in_cluster=idx,
                    source="representative",
                    loaded=loaded,
                )
            )

        cov_candidates = [cid for cid in all_chunk_ids if cid not in rep_set]
        for idx, cid in enumerate(cov_candidates):
            cov_items.append(
                _item_from_chunk(
                    chunk_id=cid,
                    cluster_label=label,
                    topic=topic,
                    rank_in_cluster=idx,
                    source="coverage",
                    loaded=loaded,
                )
            )

    rep_items = _dedupe_keep_best(rep_items)
    cov_items = _dedupe_keep_best(cov_items)

    # Ensure minimum 1 representative item per cluster if possible.
    rep_by_cluster: dict[str, list[CandidateItem]] = {}
    for item in rep_items:
        rep_by_cluster.setdefault(item.source_ref, []).append(item)
    for items in rep_by_cluster.values():
        items.sort(key=lambda x: x.semantic_score, reverse=True)

    selected: list[CandidateItem] = []
    selected_ids: set[str] = set()
    cluster_order = [f"cluster_{label}" for label, _, _, _ in sorted(cluster_sizes, key=lambda x: x[1], reverse=True)]
    for cref in cluster_order:
        bucket = rep_by_cluster.get(cref) or []
        if not bucket:
            continue
        item = bucket[0]
        if item.candidate_id not in selected_ids and len(selected) < rep_slots:
            selected.append(item)
            selected_ids.add(item.candidate_id)

    rep_items.sort(key=lambda x: x.semantic_score, reverse=True)
    for item in rep_items:
        if len(selected) >= rep_slots:
            break
        if item.candidate_id in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item.candidate_id)

    cov_items.sort(key=lambda x: x.semantic_score, reverse=True)
    cov_selected_count = 0
    for item in cov_items:
        if len(selected) >= total_slots:
            break
        if cov_selected_count >= cov_slots:
            break
        if item.candidate_id in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item.candidate_id)
        cov_selected_count += 1

    if len(selected) < total_slots:
        all_pool = sorted(rep_items + cov_items, key=lambda x: x.semantic_score, reverse=True)
        for item in all_pool:
            if len(selected) >= total_slots:
                break
            if item.candidate_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item.candidate_id)

    final: list[CandidateItem] = []
    for item in selected[:total_slots]:
        final_score = 0.85 * _safe_float(item.semantic_score) + 0.15 * (0.2 if item.framework_tag == "representative" else 0.0)
        final.append(
            replace(
                item,
                framework_boost=0.2 if item.framework_tag == "representative" else 0.0,
                final_score=final_score,
            )
        )

    final.sort(key=lambda x: (x.final_score, x.semantic_score, x.title), reverse=True)
    debug = {
        "mode": "overview",
        "clusters_used": len(cluster_sizes),
        "rep_ratio": round(max(0.0, min(1.0, rep_ratio)), 4),
        "rep_pool": len(rep_items),
        "coverage_pool": len(cov_items),
        "vectors_loaded": loaded is not None,
    }
    return final, debug
