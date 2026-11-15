"""region monthly aggregates

Revision ID: b2c3d4e5f6a7
Revises: 8b1c4d2e6f7a
Create Date: 2026-11-07
"""
from __future__ import annotations

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "8b1c4d2e6f7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW region_monthly AS
        SELECT
            o.location_id,
            o.source,
            o.variable_code,
            date_trunc('month', o.observed_on)::date AS month,
            avg(o.value) AS value,
            min(o.value) AS min,
            max(o.value) AS max,
            avg(o.valid_fraction) AS valid_fraction,
            count(*) AS n
        FROM observations o
        WHERE o.value IS NOT NULL
        GROUP BY o.location_id, o.source, o.variable_code, date_trunc('month', o.observed_on)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX region_monthly_key "
        "ON region_monthly (location_id, source, variable_code, month)"
    )
    op.execute(
        "CREATE INDEX region_monthly_var_month_idx "
        "ON region_monthly (source, variable_code, month)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS region_monthly")
