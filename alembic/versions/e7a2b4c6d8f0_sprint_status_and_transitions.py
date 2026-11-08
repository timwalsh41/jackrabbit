"""Sprint lifecycle: persisted status and transition history.

Revision ID: e7a2b4c6d8f0
Revises: a8c1e5f7b3d9
Create Date: 2024-01-05 00:00:00.000000

JRB-029 (ADR-0026): sprint status becomes a persisted state machine. The
``sprint.status`` column is the single source of truth, and the new
``sprinttransition`` table records every manual transition. Sprints that
already exist are backfilled from their dates (actual_finish -> Complete,
actual_start -> In Progress, otherwise Not Started); their history starts
empty — no synthetic rows are written for transitions that never happened.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e7a2b4c6d8f0"
down_revision = "a8c1e5f7b3d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sprint",
        sa.Column("status", sa.String(), nullable=False, server_default="Not Started"),
    )
    # Backfill from the dates (the pre-migration derived status): a sprint
    # with an actual finish is Complete, one with an actual start is In
    # Progress, anything else keeps the Not Started default.
    op.execute(
        "update sprint set status = 'In Progress' "
        "where actual_finish is null and actual_start is not null"
    )
    op.execute("update sprint set status = 'Complete' where actual_finish is not null")
    op.create_table(
        "sprinttransition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sprint_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sprint_id"],
            ["sprint.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sprinttransition_sprint_id"),
        "sprinttransition",
        ["sprint_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sprinttransition_sprint_id"), table_name="sprinttransition")
    op.drop_table("sprinttransition")
    op.drop_column("sprint", "status")
