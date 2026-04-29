"""Pick representative chunk_ids near cluster centroid (cosine similarity)."""

from __future__ import annotations

import numpy as np

from app.mindmap.vector_loader import LoadedVectors


def representative_chunk_ids(
    loaded: LoadedVectors,
    cluster_chunk_ids: list[str],
    *,
    top_k: int,
) -> list[str]:
    if not cluster_chunk_ids or top_k <= 0:
        return []

    id_to_row = {cid: i for i, cid in enumerate(loaded.chunk_ids)}
    rows: list[int] = []
    ordered_ids: list[str] = []
    for cid in cluster_chunk_ids:
        r = id_to_row.get(cid)
        if r is None:
            continue
        rows.append(r)
        ordered_ids.append(cid)

    if not rows:
        return []

    sub = loaded.vectors[rows].astype(np.float64, copy=False)
    centroid = np.mean(sub, axis=0)
    c_norm = np.linalg.norm(centroid)
    if c_norm < 1e-12:
        return ordered_ids[: min(top_k, len(ordered_ids))]

    sims: list[float] = []
    for i in range(sub.shape[0]):
        v = sub[i]
        vn = np.linalg.norm(v)
        if vn < 1e-12:
            sims.append(0.0)
        else:
            sims.append(float(np.dot(v, centroid) / (vn * c_norm)))

    order = np.argsort(-np.asarray(sims, dtype=np.float64))
    k = min(top_k, len(order))
    return [ordered_ids[int(order[j])] for j in range(k)]
