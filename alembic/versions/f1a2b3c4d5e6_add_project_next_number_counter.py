"""Add the per-project ticket-number counter.

Revision ID: f1a2b3c4d5e6
Revises: e7a2b4c6d8f0
Create Date: 2024-01-06 00:00:00.000000

JRB-037: ticket numbers become a monotone per-project counter so a number is
never reissued, even after the highest-numbered ticket is deleted - a deleted
designator would otherwise silently point at a different ticket. The new
``project.next_number`` column is seeded to MAX(ticket.number)+1 per project
(1 for a project with no tickets); existing ticket numbers do not change.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e7a2b4c6d8f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
    )
    # Seed the counter past each project's highest existing ticket number so
    # the first post-migration allocation cannot collide (or reissue a deleted
    # number). Projects with no tickets keep the default 1.
    op.execute(
        "update project set next_number = "
        "coalesce((select max(number) from ticket where ticket.project_id = project.id), 0) + 1"
    )


def downgrade() -> None:
    op.drop_column("project", "next_number")
