"""Load vectors from ``rag_chunks`` with notebook-scoped filters."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


@dataclass
class LoadedVectors:
    chunk_ids: list[str]
    vectors: np.ndarray
    meta_by_id: dict[str, dict[str, Any]]


class VectorLoaderError(RuntimeError):
    """Base error for vector loading."""


class NotFoundVectorsError(VectorLoaderError):
    """Raised when scope returns no vectors."""


def _db_dsn() -> str:
    settings = get_settings()
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")


def _table_name() -> str:
    return get_settings().VECTOR_TABLE


def _parse_vector(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [float(v) for v in raw]
    if isinstance(raw, tuple):
        return [float(v) for v in raw]
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            body = s[1:-1].strip()
            if not body:
                return []
            return [float(x) for x in body.split(",")]
    if hasattr(raw, "__iter__"):
        try:
            return [float(v) for v in raw]
        except TypeError:
            pass
    raise VectorLoaderError(f"Unsupported vector payload type: {type(raw)!r}")


def _validate_vectors(vectors: list[list[float]]) -> np.ndarray:
    if not vectors:
        raise NotFoundVectorsError("Scope returned zero vectors.")

    dim = len(vectors[0])
    if dim == 0:
        raise VectorLoaderError("Vector dimension cannot be zero.")

    for i, v in enumerate(vectors):
        if len(v) != dim:
            raise VectorLoaderError(
                f"Inconsistent vector dimensions at row {i}: expected {dim}, got {len(v)}"
            )
        if any(math.isnan(x) or math.isinf(x) for x in v):
            raise VectorLoaderError(f"Invalid numeric value (NaN/Inf) at row {i}.")

    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim != 2:
        raise VectorLoaderError(f"Expected 2D matrix, got shape {arr.shape!r}")
    return arr


def _execute(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    with psycopg.connect(_db_dsn(), row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        return list(cur.fetchall())


def _to_loaded(rows: list[dict[str, Any]]) -> LoadedVectors:
    if not rows:
        raise NotFoundVectorsError("Scope returned zero vectors.")

    chunk_ids: list[str] = []
    vectors_raw: list[list[float]] = []
    meta_by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        cid = str(r["chunk_id"])
        chunk_ids.append(cid)
        vectors_raw.append(_parse_vector(r["embedding"]))
        metadata = r.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {"raw": metadata}
        meta_by_id[cid] = {
            "chunk_id": cid,
            "notebooklm_id": r.get("notebooklm_id"),
            "source_url": r.get("source_url"),
            "chunk_text": r.get("chunk_text"),
            "metadata": metadata if isinstance(metadata, dict) else {"value": metadata},
        }
    return LoadedVectors(chunk_ids=chunk_ids, vectors=_validate_vectors(vectors_raw), meta_by_id=meta_by_id)


def load_vectors_by_website(*, notebooklm_id: str, website: str) -> LoadedVectors:
    host = website.replace("https://", "").replace("http://", "").strip().lower().strip("/")
    pattern = f"%{host}%"
    query = f"""
    SELECT chunk_id, notebooklm_id, source_url, chunk_text, metadata, embedding
    FROM {_table_name()}
    WHERE notebooklm_id = %(notebooklm_id)s
      AND is_active = true
      AND source_url ILIKE %(host_pattern)s
    ORDER BY chunk_id;
    """
    rows = _execute(query, {"notebooklm_id": notebooklm_id, "host_pattern": pattern})
    return _to_loaded(rows)


def load_vectors_by_run_id(*, notebooklm_id: str, run_id: str) -> LoadedVectors:
    query = f"""
    SELECT chunk_id, notebooklm_id, source_url, chunk_text, metadata, embedding
    FROM {_table_name()}
    WHERE notebooklm_id = %(notebooklm_id)s
      AND is_active = true
      AND metadata->>'run_id' = %(run_id)s
    ORDER BY chunk_id;
    """
    rows = _execute(query, {"notebooklm_id": notebooklm_id, "run_id": run_id})
    return _to_loaded(rows)


def load_vectors_by_chunk_ids(*, notebooklm_id: str, chunk_ids: list[str]) -> LoadedVectors:
    if not chunk_ids:
        raise NotFoundVectorsError("chunk_ids is empty.")
    query = f"""
    SELECT chunk_id, notebooklm_id, source_url, chunk_text, metadata, embedding
    FROM {_table_name()}
    WHERE notebooklm_id = %(notebooklm_id)s
      AND is_active = true
      AND chunk_id = ANY(%(chunk_ids)s)
    ORDER BY chunk_id;
    """
    rows = _execute(query, {"notebooklm_id": notebooklm_id, "chunk_ids": chunk_ids})
    return _to_loaded(rows)

