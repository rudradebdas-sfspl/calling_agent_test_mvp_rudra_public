"""add call_transfer_number to agents

Revision ID: 0004_add_call_transfer_number
Revises: 0003_add_sip_default
Create Date: 2026-06-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_add_call_transfer_number"
down_revision = "0003_add_sip_default"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("call_transfer_number", sa.String(length=32), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("agents", "call_transfer_number")
