"""Add criterion audit history.

Revision ID: a8c1e5f7b3d9
Revises: f3b9d7c2a5e1
Create Date: 2024-01-04 00:00:00.000000

Audit entries for criterion adds, edits, and sign-offs (ADR-0025): one row
per change, carrying the criterion text and the timestamp. Entries belong to
the ticket, so they survive a criterion row being deleted. Table name follows
the existing SQLModel default pattern (cf. ``ticketcriterion``).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a8c1e5f7b3d9"
down_revision = "f3b9d7c2a5e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticketcriterionhistory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticketcriterionhistory_ticket_id"),
        "ticketcriterionhistory",
        ["ticket_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticketcriterionhistory_ticket_id"), table_name="ticketcriterionhistory")
    op.drop_table("ticketcriterionhistory")
