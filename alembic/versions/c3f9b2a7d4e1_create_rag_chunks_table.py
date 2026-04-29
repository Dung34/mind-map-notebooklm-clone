"""baseline schema for ingest metadata and vector storage

Revision ID: c3f9b2a7d4e1
Revises:
Create Date: 2026-04-29 09:47:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f9b2a7d4e1"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("total_urls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_urls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notebooklm_id", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_ingest_runs_notebooklm_started",
        "ingest_runs",
        ["notebooklm_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "page_index",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("last_run_id", sa.String(length=64), sa.ForeignKey("ingest_runs.run_id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_page_index_normalized_url", "page_index", ["normalized_url"], unique=True)
    op.create_index("ix_page_index_last_run_id", "page_index", ["last_run_id"], unique=False)

    op.create_table(
        "chunk_index",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chunk_id", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("ingest_runs.run_id"), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("notebooklm_id", sa.Text(), nullable=False),
    )
    op.create_index("ix_chunk_index_chunk_id", "chunk_index", ["chunk_id"], unique=True)
    op.create_index("ix_chunk_index_source_url", "chunk_index", ["source_url"], unique=False)
    op.create_index("ix_chunk_index_run_id", "chunk_index", ["run_id"], unique=False)
    op.create_index("ix_chunk_index_is_active", "chunk_index", ["is_active"], unique=False)
    op.create_index("ix_chunk_index_expires_at", "chunk_index", ["expires_at"], unique=False)
    op.create_index(
        "ix_chunk_index_notebooklm_active",
        "chunk_index",
        ["notebooklm_id", "is_active"],
        unique=False,
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute(
        """
        CREATE TABLE rag_chunks (
            chunk_id TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            embedding vector(1536) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notebooklm_id TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true
        );
        """
    )
    op.create_index("ix_rag_chunks_source_url", "rag_chunks", ["source_url"], unique=False)
    op.create_index(
        "ix_rag_chunks_notebooklm_active",
        "rag_chunks",
        ["notebooklm_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_rag_chunks_notebooklm_source_url",
        "rag_chunks",
        ["notebooklm_id", "source_url"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_notebooklm_source_url", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_notebooklm_active", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_source_url", table_name="rag_chunks")
    op.drop_table("rag_chunks")

    op.drop_index("ix_chunk_index_notebooklm_active", table_name="chunk_index")
    op.drop_index("ix_chunk_index_expires_at", table_name="chunk_index")
    op.drop_index("ix_chunk_index_is_active", table_name="chunk_index")
    op.drop_index("ix_chunk_index_run_id", table_name="chunk_index")
    op.drop_index("ix_chunk_index_source_url", table_name="chunk_index")
    op.drop_index("ix_chunk_index_chunk_id", table_name="chunk_index")
    op.drop_table("chunk_index")

    op.drop_index("ix_page_index_last_run_id", table_name="page_index")
    op.drop_index("ix_page_index_normalized_url", table_name="page_index")
    op.drop_table("page_index")

    op.drop_index("ix_ingest_runs_notebooklm_started", table_name="ingest_runs")
    op.drop_table("ingest_runs")
