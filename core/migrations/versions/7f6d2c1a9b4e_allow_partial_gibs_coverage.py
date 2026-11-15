"""allow partial GIBS coverage

Revision ID: 7f6d2c1a9b4e
Revises: e2fa4a394f02
Create Date: 2026-11-05
"""
from __future__ import annotations

from alembic import op

revision = "7f6d2c1a9b4e"
down_revision = "e2fa4a394f02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("observations_quality_check", "observations", type_="check")
    op.create_check_constraint(
        "observations_quality_check",
        "observations",
        "quality IN ('ok', 'partial', 'fill', 'missing', 'no_data', 'estimated', 'error')",
    )


def downgrade() -> None:
    op.drop_constraint("observations_quality_check", "observations", type_="check")
    op.create_check_constraint(
        "observations_quality_check",
        "observations",
        "quality IN ('ok', 'fill', 'missing', 'no_data', 'estimated', 'error')",
    )
