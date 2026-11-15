"""materialized coverage view

Revision ID: 8b1c4d2e6f7a
Revises: 7f6d2c1a9b4e
Create Date: 2026-11-06
"""
from __future__ import annotations

from alembic import op

revision = "8b1c4d2e6f7a"
down_revision = "7f6d2c1a9b4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW variable_coverage AS
        SELECT
            o.variable_code,
            o.source,
            v.name,
            v.unit,
            count(*) AS count,
            min(o.observed_on) AS start,
            max(o.observed_on) AS end
        FROM observations o
        JOIN variables v ON v.code = o.variable_code
        GROUP BY o.variable_code, o.source, v.name, v.unit
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX variable_coverage_key "
        "ON variable_coverage (variable_code, source)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS variable_coverage")
