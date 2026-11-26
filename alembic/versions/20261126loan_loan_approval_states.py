"""Add pending/rejected loan states and loan approvals.

Revision ID: 20261126loan
Revises: b8d4f0a6c2e9
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20261126loan"
down_revision: Union[str, Sequence[str], None] = "b8d4f0a6c2e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing active loans remain active; only newly submitted loans are pending.
    op.execute("ALTER TYPE loan_status ADD VALUE IF NOT EXISTS 'pending'")
    op.execute("ALTER TYPE loan_status ADD VALUE IF NOT EXISTS 'rejected'")
    op.execute("ALTER TYPE approval_request_type ADD VALUE IF NOT EXISTS 'loan'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place. Keep the
    # additive values so a downgrade does not invalidate persisted decisions.
    pass
