"""Recursive HDBSCAN sub-clustering → tree payload for clusters_tree_raw.json (Phase 10 C4)."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.config import get_settings
from app.mindmap.clusterer import cluster_top
from app.mindmap.reducer import default_umap_params
from app.mindmap.vector_loader import LoadedVectors


def _sub_cluster_params() -> dict[str, Any]:
    settings = get_settings()
    umap_base = default_umap_params()
    umap_base["n_neighbors"] = settings.MINDMAP_SUB_N_NEIGHBORS
    return {
        "umap": umap_base,
        "hdbscan": {
            "min_cluster_size": settings.MINDMAP_SUB_MIN_CLUSTER_SIZE,
            "min_samples": settings.MINDMAP_SUB_MIN_SAMPLES,
        },
        "small_n_threshold": settings.MINDMAP_SMALL_N_THRESHOLD,
    }


def _vectors_for_chunk_ids(
    loaded: LoadedVectors,
    chunk_ids: list[str],
) -> tuple[np.ndarray, list[str]]:
    id_to_row = {cid: i for i, cid in enumerate(loaded.chunk_ids)}
    ordered = sorted(chunk_ids)
    rows: list[int] = []
    out_ids: list[str] = []
    for cid in ordered:
        r = id_to_row.get(cid)
        if r is None:
            continue
        rows.append(r)
        out_ids.append(cid)
    if not out_ids:
        raise ValueError("No chunk_ids resolved against LoadedVectors")
    return loaded.vectors[np.asarray(rows, dtype=np.intp)], out_ids


def _build_subtree(
    loaded: LoadedVectors,
    *,
    node_id: str,
    chunk_ids: list[str],
    depth: int,
    cluster_label: int | None,
) -> dict[str, Any]:
    settings = get_settings()
    max_depth = settings.MINDMAP_MAX_DEPTH
    min_recurse = settings.MINDMAP_MIN_RECURSE_SIZE

    base: dict[str, Any] = {
        "node_id": node_id,
        "depth": depth,
        "cluster_label": cluster_label,
        "chunk_ids": list(chunk_ids),
        "noise_chunk_ids": [],
        "children": [],
        "stopped_reason": None,
    }

    if depth >= max_depth:
        base["stopped_reason"] = "max_depth"
        return base

    if len(chunk_ids) < min_recurse:
        base["stopped_reason"] = "min_recurse_size"
        return base

    sub_vectors, ordered_ids = _vectors_for_chunk_ids(loaded, chunk_ids)
    sub_result = cluster_top(
        sub_vectors,
        chunk_ids=ordered_ids,
        reduced=None,
        params=_sub_cluster_params(),
    )

    if int(sub_result.metrics["cluster_count"]) < 2:
        base["stopped_reason"] = "no_split"
        return base

    children: list[dict[str, Any]] = []
    for cl in sub_result.cluster_to_chunk_ids:
        label = int(cl["label"])
        cids = [str(x) for x in cl["chunk_ids"]]
        child_id = f"{node_id}_c{label}"
        children.append(
            _build_subtree(
                loaded,
                node_id=child_id,
                chunk_ids=cids,
                depth=depth + 1,
                cluster_label=label,
            )
        )

    if sub_result.noise_chunk_ids:
        children.append(
            {
                "node_id": f"{node_id}_n",
                "depth": depth + 1,
                "cluster_label": -1,
                "chunk_ids": list(sub_result.noise_chunk_ids),
                "noise_chunk_ids": [],
                "children": [],
                "stopped_reason": "noise_bucket",
            }
        )

    base["noise_chunk_ids"] = list(sub_result.noise_chunk_ids)
    base["children"] = children
    return base


def _collect_tree_metrics(node: dict[str, Any]) -> tuple[int, int, int]:
    """Returns (node_count, leaf_count, max_depth)."""
    node_count = 1
    ch = node.get("children") or []
    if not ch:
        return 1, 1, int(node.get("depth") or 0)
    max_d = int(node.get("depth") or 0)
    leaves = 0
    for c in ch:
        nc, lc, md = _collect_tree_metrics(c)
        node_count += nc
        leaves += lc
        max_d = max(max_d, md)
    return node_count, leaves, max_d


def build_clusters_tree_raw_payload(
    loaded: LoadedVectors,
    *,
    mindmap_run_id: str,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Run top-level cluster + recursive sub-cluster; return JSON-ready dict."""
    top_result = cluster_top(loaded.vectors, chunk_ids=loaded.chunk_ids, reduced=None)

    children: list[dict[str, Any]] = []
    for cl in top_result.cluster_to_chunk_ids:
        label = int(cl["label"])
        cids = [str(x) for x in cl["chunk_ids"]]
        child_id = f"root_c{label}"
        children.append(
            _build_subtree(
                loaded,
                node_id=child_id,
                chunk_ids=cids,
                depth=1,
                cluster_label=label,
            )
        )

    if top_result.noise_chunk_ids:
        children.append(
            {
                "node_id": "root_n",
                "depth": 1,
                "cluster_label": -1,
                "chunk_ids": list(top_result.noise_chunk_ids),
                "noise_chunk_ids": [],
                "children": [],
                "stopped_reason": "noise_bucket",
            }
        )

    tree: dict[str, Any] = {
        "node_id": "root",
        "depth": 0,
        "cluster_label": None,
        "chunk_ids": list(loaded.chunk_ids),
        "noise_chunk_ids": list(top_result.noise_chunk_ids),
        "children": children,
        "stopped_reason": None,
    }

    sub_params = _sub_cluster_params()
    nc, lc, md = _collect_tree_metrics(tree)

    return {
        "schema_version": 1,
        "mindmap_run_id": mindmap_run_id,
        "scope": scope,
        "params": {
            "top": top_result.params,
            "sub": sub_params,
            "limits": {
                "max_depth": get_settings().MINDMAP_MAX_DEPTH,
                "min_recurse_size": get_settings().MINDMAP_MIN_RECURSE_SIZE,
            },
        },
        "metrics": {
            "vector_count": len(loaded.chunk_ids),
            "top_cluster_count": int(top_result.metrics["cluster_count"]),
            "top_noise_count": int(top_result.metrics["noise_count"]),
            "tree_node_count": nc,
            "tree_leaf_count": lc,
            "tree_max_depth": md,
        },
        "tree": tree,
    }
