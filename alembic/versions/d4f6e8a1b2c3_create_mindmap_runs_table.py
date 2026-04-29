"""create mindmap_runs table

Revision ID: d4f6e8a1b2c3
Revises: c3f9b2a7d4e1
Create Date: 2026-04-29 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4f6e8a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c3f9b2a7d4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mindmap_runs",
        sa.Column("mindmap_run_id", sa.Text(), primary_key=True),
        sa.Column("ingest_run_id", sa.Text(), sa.ForeignKey("ingest_runs.run_id"), nullable=True),
        sa.Column("notebooklm_id", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("scope_mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cluster_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leaf_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("params", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mindmap_runs_website", "mindmap_runs", ["website"], unique=False)
    op.create_index(
        "ix_mindmap_runs_notebook_started",
        "mindmap_runs",
        ["notebooklm_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mindmap_runs_notebook_started", table_name="mindmap_runs")
    op.drop_index("ix_mindmap_runs_website", table_name="mindmap_runs")
    op.drop_table("mindmap_runs")
