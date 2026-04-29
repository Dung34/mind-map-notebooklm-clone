"""HDBSCAN clustering for top-level mindmap clusters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import hdbscan
import numpy as np

from app.config import get_settings
from app.mindmap.reducer import default_umap_params, reduce_umap


@dataclass
class ClusterTopResult:
    chunk_ids: list[str]
    labels: list[int]
    cluster_to_chunk_ids: list[dict[str, Any]]
    noise_chunk_ids: list[str]
    metrics: dict[str, float | int]
    params: dict[str, Any]


def _default_cluster_params() -> dict[str, Any]:
    settings = get_settings()
    return {
        "hdbscan": {
            "min_cluster_size": settings.MINDMAP_HDBSCAN_MIN_CLUSTER_SIZE,
            "min_samples": settings.MINDMAP_HDBSCAN_MIN_SAMPLES,
        },
        "small_n_threshold": settings.MINDMAP_SMALL_N_THRESHOLD,
    }


def cluster_top(
    vectors: np.ndarray,
    *,
    reduced: np.ndarray | None = None,
    params: dict[str, Any] | None = None,
    chunk_ids: list[str] | None = None,
) -> ClusterTopResult:
    if vectors.ndim != 2:
        raise ValueError(f"Expected 2D vectors, got shape={vectors.shape!r}")
    n_rows = int(vectors.shape[0])
    if n_rows == 0:
        raise ValueError("Cannot cluster empty vectors.")

    resolved_chunk_ids = chunk_ids or [str(i) for i in range(n_rows)]
    if len(resolved_chunk_ids) != n_rows:
        raise ValueError("chunk_ids length must match vectors row count.")

    cfg = _default_cluster_params()
    if params:
        cfg.update(params)
    cfg_umap = default_umap_params()
    cfg_umap.update((cfg.get("umap") or {}))

    small_n_threshold = int(cfg.get("small_n_threshold", get_settings().MINDMAP_SMALL_N_THRESHOLD))
    use_raw_cosine = n_rows < small_n_threshold
    if reduced is None:
        reduced = reduce_umap(vectors, cfg_umap)

    if use_raw_cosine:
        fit_data = vectors
        metric = "cosine"
        umap_applied = False
    else:
        fit_data = reduced
        metric = "euclidean"
        umap_applied = int(reduced.shape[1]) != int(vectors.shape[1])

    hdbscan_cfg = cfg.get("hdbscan") or {}
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=int(hdbscan_cfg.get("min_cluster_size", get_settings().MINDMAP_HDBSCAN_MIN_CLUSTER_SIZE)),
        min_samples=int(hdbscan_cfg.get("min_samples", get_settings().MINDMAP_HDBSCAN_MIN_SAMPLES)),
        metric=metric,
    )
    labels_array = clusterer.fit_predict(fit_data)
    labels = [int(x) for x in labels_array.tolist()]

    groups: dict[int, list[str]] = {}
    noise_chunk_ids: list[str] = []
    for cid, label in zip(resolved_chunk_ids, labels, strict=True):
        if label == -1:
            noise_chunk_ids.append(cid)
            continue
        groups.setdefault(label, []).append(cid)

    sorted_clusters = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    cluster_to_chunk_ids = [
        {"label": int(label), "size": len(cids), "chunk_ids": cids} for label, cids in sorted_clusters
    ]

    cluster_sizes = [len(item["chunk_ids"]) for item in cluster_to_chunk_ids]
    cluster_count = len(cluster_to_chunk_ids)
    noise_count = len(noise_chunk_ids)
    metrics: dict[str, float | int] = {
        "vector_count": n_rows,
        "cluster_count": cluster_count,
        "noise_count": noise_count,
        "noise_ratio": round(noise_count / max(1, n_rows), 6),
        "mean_cluster_size": round(float(np.mean(cluster_sizes)) if cluster_sizes else 0.0, 6),
        "min_cluster_size": int(min(cluster_sizes) if cluster_sizes else 0),
        "max_cluster_size": int(max(cluster_sizes) if cluster_sizes else 0),
    }

    resolved_params = {
        "umap": {
            "n_neighbors": int(cfg_umap["n_neighbors"]),
            "n_components": int(cfg_umap["n_components"]),
            "min_dist": float(cfg_umap["min_dist"]),
            "metric": str(cfg_umap.get("metric", "cosine")),
            "random_state": int(cfg_umap.get("random_state", 42)),
            "applied": bool(umap_applied),
        },
        "hdbscan": {
            "min_cluster_size": int(hdbscan_cfg.get("min_cluster_size", get_settings().MINDMAP_HDBSCAN_MIN_CLUSTER_SIZE)),
            "min_samples": int(hdbscan_cfg.get("min_samples", get_settings().MINDMAP_HDBSCAN_MIN_SAMPLES)),
            "metric": metric,
        },
        "small_n_threshold": small_n_threshold,
    }

    return ClusterTopResult(
        chunk_ids=resolved_chunk_ids,
        labels=labels,
        cluster_to_chunk_ids=cluster_to_chunk_ids,
        noise_chunk_ids=noise_chunk_ids,
        metrics=metrics,
        params=resolved_params,
    )
