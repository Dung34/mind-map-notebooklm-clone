"""Build final mindmap.json by merging tree + topics + entities."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.config import get_settings
from app.mindmap.representative import representative_chunk_ids
from app.mindmap.vector_loader import LoadedVectors


def _mindmap_ms_fields(topic: dict[str, Any]) -> dict[str, str]:
    """Ensure every tree node exposes the same M&S keys (topics.json v2 or defaults)."""
    swot_raw = topic.get("swot_category")
    funnel_raw = topic.get("funnel_stage")
    notes_raw = topic.get("ms_notes")

    swot = str(swot_raw).strip() if isinstance(swot_raw, str) and swot_raw.strip() else "N_A"
    funnel = str(funnel_raw).strip() if isinstance(funnel_raw, str) and funnel_raw.strip() else "Unknown"
    notes = notes_raw.strip() if isinstance(notes_raw, str) else ""

    return {
        "swot_category": swot,
        "funnel_stage": funnel,
        "ms_notes": notes,
    }


def _topic_for_node(node: dict[str, Any], topics_doc: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "")
    label = node.get("cluster_label")
    candidates = [node_id]
    if isinstance(label, int):
        if label == -1:
            candidates.append("cluster_noise")
        else:
            candidates.append(f"cluster_{label}")
    for key in candidates:
        value = topics_doc.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _stable_ids_by_depth(tree: dict[str, Any]) -> dict[str, str]:
    counters: dict[int, int] = defaultdict(int)
    out: dict[str, str] = {}

    def _walk(node: dict[str, Any]) -> None:
        depth = int(node.get("depth") or 0)
        node_id = str(node.get("node_id") or "")
        idx = counters[depth]
        counters[depth] += 1
        if node_id:
            out[node_id] = f"n_{depth}_{idx}"
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _walk(child)

    _walk(tree)
    return out


def build_mindmap_payload(
    loaded: LoadedVectors,
    tree_doc: dict[str, Any],
    topics_doc: dict[str, Any],
    entities_doc: dict[str, Any],
) -> dict[str, Any]:
    tree = tree_doc.get("tree") or {}
    entities_by_leaf = entities_doc.get("entities_by_leaf") or {}
    settings = get_settings()
    top_k = settings.MINDMAP_TOPIC_REPR_K
    id_map = _stable_ids_by_depth(tree)

    def _build(node: dict[str, Any]) -> dict[str, Any]:
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        child_nodes = [_build(c) for c in children]
        if child_nodes:
            chunk_ids = sorted({cid for child in child_nodes for cid in child.get("chunk_ids", [])})
        else:
            chunk_ids = [str(x) for x in (node.get("chunk_ids") or [])]

        topic = _topic_for_node(node, topics_doc)
        ms = _mindmap_ms_fields(topic)
        node_id = str(node.get("node_id") or "")
        label = node.get("cluster_label")
        if isinstance(label, int) and label >= 0:
            fallback_title = f"Cluster {label}"
        elif label == -1:
            fallback_title = "Noise"
        else:
            fallback_title = "Root"

        entities = entities_by_leaf.get(node_id) if not child_nodes else []
        if not isinstance(entities, list):
            entities = []

        return {
            "id": id_map.get(node_id, node_id),
            "node_id": node_id,
            "depth": int(node.get("depth") or 0),
            "title": str(topic.get("title") or fallback_title),
            "summary": str(topic.get("summary") or ""),
            **ms,
            "size": len(chunk_ids),
            "chunk_ids": chunk_ids,
            "representative_chunk_ids": representative_chunk_ids(loaded, chunk_ids, top_k=top_k),
            "entities": entities,
            "children": child_nodes,
        }

    root_node = _build(tree)
    expected_root_count = int((tree_doc.get("metrics") or {}).get("vector_count") or 0)
    actual_root_count = len(root_node["chunk_ids"])
    if expected_root_count and expected_root_count != actual_root_count:
        raise ValueError(
            f"Root chunk_ids coverage mismatch: expected={expected_root_count}, actual={actual_root_count}"
        )

    return {
        "schema_version": 2,
        "mindmap_run_id": str(tree_doc.get("mindmap_run_id") or ""),
        "scope": tree_doc.get("scope") or {},
        "metrics": {
            "vector_count": actual_root_count,
            "tree_max_depth": int((tree_doc.get("metrics") or {}).get("tree_max_depth") or 0),
            "tree_leaf_count": int((tree_doc.get("metrics") or {}).get("tree_leaf_count") or 0),
        },
        "tree": root_node,
    }
