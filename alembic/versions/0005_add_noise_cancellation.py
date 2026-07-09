"""add noise cancellation columns

Revision ID: 0005_add_noise_cancellation
Revises: 0004_add_call_transfer_number
Create Date: 2026-06-23

Additive only. Both columns have server defaults, so existing rows are filled in
automatically and nothing breaks. Default keeps noise cancellation OFF, so agent
behaviour is unchanged until it is explicitly enabled from the Agent Builder.
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_add_noise_cancellation"
down_revision = "0004_add_call_transfer_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "noise_cancellation_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "noise_cancellation_provider",
            sa.String(64),
            server_default="quail",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "noise_cancellation_provider")
    op.drop_column("agents", "noise_cancellation_enabled")
