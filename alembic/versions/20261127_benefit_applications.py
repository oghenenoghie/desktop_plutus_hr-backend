"""Create employee benefit applications.

Revision ID: 20261127benefitapp
Revises: 20261126loan
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261127benefitapp"
down_revision: Union[str, Sequence[str], None] = "20261126loan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE approval_request_type ADD VALUE IF NOT EXISTS 'benefit_application'")

    application_status = postgresql.ENUM(
        "pending", "approved", "rejected",
        name="benefit_application_status",
        create_type=False,
    )
    application_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "benefit_applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("requested_effective_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("status", application_status, nullable=False),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("benefit_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_by_account_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["benefit_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["benefit_id"], ["benefits.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["reviewed_by_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_benefit_applications_employee_id",
        "benefit_applications",
        ["employee_id"],
    )
    op.create_index(
        "ix_benefit_applications_status",
        "benefit_applications",
        ["status"],
    )
    op.execute("ALTER TABLE benefit_applications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE benefit_applications FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY benefit_applications_tenant_isolation ON benefit_applications "
        "USING (org_id = NULLIF(current_setting('app.current_org', true), '')::uuid)"
    )


def downgrade() -> None:
    op.drop_table("benefit_applications")
    op.execute("DROP TYPE IF EXISTS benefit_application_status")
    # PostgreSQL enum values cannot be removed safely from approval_request_type.
