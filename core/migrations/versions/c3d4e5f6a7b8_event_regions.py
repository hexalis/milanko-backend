"""event to region assignments

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_regions",
        sa.Column(
            "event_id",
            sa.String(120),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("region_code", sa.Integer, primary_key=True),
        sa.Column("first_date", sa.Date),
        sa.Column("last_date", sa.Date),
        sa.Column("n_geometries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "event_regions_region_idx",
        "event_regions",
        ["region_code", "first_date"],
    )


def downgrade() -> None:
    op.drop_index("event_regions_region_idx", table_name="event_regions")
    op.drop_table("event_regions")
