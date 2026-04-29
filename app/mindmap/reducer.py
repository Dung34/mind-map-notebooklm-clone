"""UMAP reducer for top-level mindmap clustering."""

from __future__ import annotations

from typing import Any

import numpy as np
import umap

from app.config import get_settings


def default_umap_params() -> dict[str, Any]:
    settings = get_settings()
    return {
        "n_neighbors": settings.MINDMAP_UMAP_N_NEIGHBORS,
        "n_components": settings.MINDMAP_UMAP_N_COMPONENTS,
        "min_dist": settings.MINDMAP_UMAP_MIN_DIST,
        "metric": "cosine",
        "random_state": settings.MINDMAP_UMAP_RANDOM_STATE,
    }


def reduce_umap(vectors: np.ndarray, params: dict[str, Any] | None = None) -> np.ndarray:
    if vectors.ndim != 2:
        raise ValueError(f"Expected 2D vectors, got shape={vectors.shape!r}")
    n_rows = int(vectors.shape[0])
    if n_rows == 0:
        raise ValueError("Cannot reduce empty vectors.")

    settings = get_settings()
    if n_rows < settings.MINDMAP_SMALL_N_THRESHOLD:
        return vectors

    cfg = default_umap_params()
    if params:
        cfg.update(params)

    reducer = umap.UMAP(
        n_neighbors=int(cfg["n_neighbors"]),
        n_components=int(cfg["n_components"]),
        min_dist=float(cfg["min_dist"]),
        metric=str(cfg.get("metric", "cosine")),
        random_state=int(cfg.get("random_state", 42)),
    )
    reduced = reducer.fit_transform(vectors)
    return np.asarray(reduced, dtype=np.float32)
