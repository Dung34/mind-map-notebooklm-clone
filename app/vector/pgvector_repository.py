"""PostgreSQL pgvector repository (upsert/delete by chunk_id)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


@dataclass
class VectorRecord:
    chunk_id: str
    source_url: str
    embedding_model: str
    dim: int
    vector: list[float]
    metadata: dict


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"


class PgVectorRepository:
    def __init__(
        self,
        *,
        database_url: str | None = None,
        table_name: str | None = None,
        vector_dim: int = 1536,
    ) -> None:
        settings = get_settings()
        db_url = database_url or settings.DATABASE_URL
        self.database_url = db_url.replace("postgresql+psycopg://", "postgresql://")
        self.table_name = table_name or settings.VECTOR_TABLE
        self.vector_dim = vector_dim

    def _connect(self):
        return psycopg.connect(self.database_url, autocommit=False, row_factory=dict_row)

    def ensure_table(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    chunk_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    embedding vector({self.vector_dim}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{self.table_name}_source_url
                ON {self.table_name}(source_url);
                """
            )
            conn.commit()

    def upsert_embeddings(self, rows: Iterable[VectorRecord]) -> int:
        rows_list = list(rows)
        if not rows_list:
            return 0
        with self._connect() as conn, conn.cursor() as cur:
            for r in rows_list:
                cur.execute(
                    f"""
                    INSERT INTO {self.table_name}
                    (chunk_id, source_url, embedding_model, dim, embedding, metadata, updated_at)
                    VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb, NOW())
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        source_url = EXCLUDED.source_url,
                        embedding_model = EXCLUDED.embedding_model,
                        dim = EXCLUDED.dim,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW();
                    """,
                    (
                        r.chunk_id,
                        r.source_url,
                        r.embedding_model,
                        r.dim,
                        _vector_literal(r.vector),
                        json.dumps(r.metadata, ensure_ascii=False),
                    ),
                )
            conn.commit()
        return len(rows_list)

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> int:
        ids = [x for x in chunk_ids if x]
        if not ids:
            return 0
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.table_name} WHERE chunk_id = ANY(%s);", (ids,))
            deleted = cur.rowcount
            conn.commit()
        return deleted

    def count_rows(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM {self.table_name};")
            row = cur.fetchone() or {"c": 0}
            return int(row["c"])

