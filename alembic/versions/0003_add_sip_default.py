"""add is_sip_default column to agents

Revision ID: 0003_add_sip_default
Revises: 0002_add_kb_chunks
Create Date: 2026-06-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_add_sip_default"
down_revision = "0002_add_kb_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("is_sip_default", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("agents", "is_sip_default")
