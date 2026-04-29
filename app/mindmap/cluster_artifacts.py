"""Artifact writer for top-level clustering outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.mindmap.clusterer import ClusterTopResult


def write_clusters_top_json(
    out_dir: str | Path,
    scope: dict[str, Any],
    result: ClusterTopResult,
    *,
    mindmap_run_id: str,
) -> Path:
    target_dir = Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "clusters_top.json"

    payload = {
        "schema_version": 1,
        "mindmap_run_id": mindmap_run_id,
        "scope": scope,
        "params": result.params,
        "vector_count": int(result.metrics["vector_count"]),
        "metrics": {
            "cluster_count": int(result.metrics["cluster_count"]),
            "noise_count": int(result.metrics["noise_count"]),
            "noise_ratio": float(result.metrics["noise_ratio"]),
            "mean_cluster_size": float(result.metrics["mean_cluster_size"]),
            "min_cluster_size": int(result.metrics["min_cluster_size"]),
            "max_cluster_size": int(result.metrics["max_cluster_size"]),
        },
        "chunk_ids": result.chunk_ids,
        "labels": result.labels,
        "clusters": result.cluster_to_chunk_ids,
        "noise_chunk_ids": result.noise_chunk_ids,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
