"""SQLAlchemy ORM models for PostgreSQL tables (ingest metadata, vectors, mindmap).

Aligned with:
- ``alembic/versions/fe2d643eff22_*`` (ingest_runs, page_index, chunk_index)
- ``alembic/versions/a1f0c3d9b101_*`` + ``b2d4e6f8c202_*`` (notebooklm_id, rag_chunks columns)
- ``app/vector/pgvector_repository.py`` (rag_chunks / VECTOR_TABLE baseline DDL)
- ``docs/MINDMAP.md`` §4.3 (mindmap_runs — add Alembic revision when implemented)

``app/models.py`` remains Pydantic-only for pipeline DTOs; this module is persistence shape.

If ``settings.VECTOR_TABLE`` is not ``rag_chunks``, ORM here still maps the default table name;
adjust ``RagChunk.__tablename__`` or use a concrete subclass if you run multiple vector tables.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType


class PgVector(UserDefinedType):
    """pgvector column type (no extra PyPI ``pgvector`` package required)."""

    cache_ok = True

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimension})"


class Base(DeclarativeBase):
    pass


class IngestRun(Base):
    """One crawl+ingest execution (``run_id`` xuyên suốt pipeline)."""

    __tablename__ = "ingest_runs"
    __table_args__ = (
        Index(
            "ix_ingest_runs_notebooklm_started",
            "notebooklm_id",
            "started_at",
            unique=False,
        ),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="running"
    )
    total_urls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    processed_urls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notebooklm_id: Mapped[str] = mapped_column(Text, nullable=False)


class PageIndex(Base):
    """Per-URL snapshot row: normalized URL + content hash + lifecycle."""

    __tablename__ = "page_index"
    __table_args__ = (
        Index("ix_page_index_normalized_url", "normalized_url", unique=True),
        Index("ix_page_index_last_run_id", "last_run_id", unique=False),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_run_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("ingest_runs.run_id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChunkIndex(Base):
    """Chunk-level metadata for incremental RAG (soft-delete via ``is_active`` / TTL)."""

    __tablename__ = "chunk_index"
    __table_args__ = (
        Index("ix_chunk_index_chunk_id", "chunk_id", unique=True),
        Index("ix_chunk_index_source_url", "source_url", unique=False),
        Index("ix_chunk_index_run_id", "run_id", unique=False),
        Index("ix_chunk_index_is_active", "is_active", unique=False),
        Index("ix_chunk_index_expires_at", "expires_at", unique=False),
        Index(
            "ix_chunk_index_notebooklm_active",
            "notebooklm_id",
            "is_active",
            unique=False,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("ingest_runs.run_id"), nullable=True
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notebooklm_id: Mapped[str] = mapped_column(Text, nullable=False)


# Default physical table per ``app.config.Settings.VECTOR_TABLE`` (usually ``rag_chunks``).
class RagChunk(Base):
    """pgvector row: embedding + JSON metadata; scope theo ``notebooklm_id`` (Phase 10)."""

    __tablename__ = "rag_chunks"
    __table_args__ = (
        Index("ix_rag_chunks_source_url", "source_url", unique=False),
        Index(
            "ix_rag_chunks_notebooklm_active",
            "notebooklm_id",
            "is_active",
            unique=False,
        ),
        Index(
            "ix_rag_chunks_notebooklm_source_url",
            "notebooklm_id",
            "source_url",
            unique=False,
        ),
    )

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Any] = mapped_column(PgVector(1536), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notebooklm_id: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class MindmapRun(Base):
    """One mindmap build job (vector → cluster → tree → OPML). Spec: ``docs/MINDMAP.md`` §4.3."""

    __tablename__ = "mindmap_runs"
    __table_args__ = (
        Index("ix_mindmap_runs_website", "website", unique=False),
        Index(
            "ix_mindmap_runs_notebook_started",
            "notebooklm_id",
            "started_at",
            unique=False,
        ),
    )

    mindmap_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    ingest_run_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("ingest_runs.run_id"), nullable=True
    )
    notebooklm_id: Mapped[str] = mapped_column(Text, nullable=False)
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="queued"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    cluster_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    leaf_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
