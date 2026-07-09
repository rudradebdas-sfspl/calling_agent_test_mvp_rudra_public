"""add kb_chunks table for per-agent knowledgebase

Revision ID: 0002_add_kb_chunks
Revises: 0001_add_agent_runtime_config
Create Date: 2026-06-22
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_add_kb_chunks"
down_revision = "0001_add_agent_runtime_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_kb_chunks_agent_id", "kb_chunks", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_kb_chunks_agent_id", table_name="kb_chunks")
    op.drop_table("kb_chunks")
