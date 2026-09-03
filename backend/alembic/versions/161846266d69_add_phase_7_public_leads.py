"""add phase 7 public leads

Revision ID: 161846266d69
Revises: 4782a62b4927
Create Date: 2026-09-03 07:19:48.716227

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "161846266d69"
down_revision: str | None = "4782a62b4927"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new, standalone table — no existing table is touched, so unlike
    # 4782a62b4927 there is no NOT NULL-on-a-non-empty-table concern
    # requiring a server_default.
    op.create_table(
        "public_leads",
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("work_email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=False),
        sa.Column("company_size", sa.String(length=50), nullable=False),
        sa.Column("estimated_monthly_volume", sa.String(length=50), nullable=False),
        sa.Column("primary_use_case", sa.String(length=200), nullable=False),
        sa.Column("message", sa.String(length=5000), nullable=False),
        sa.Column("contact_consent", sa.Boolean(), nullable=False),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False),
        sa.Column("submitted_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_public_leads_normalized_email"), "public_leads", ["normalized_email"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_public_leads_normalized_email"), table_name="public_leads")
    op.drop_table("public_leads")
