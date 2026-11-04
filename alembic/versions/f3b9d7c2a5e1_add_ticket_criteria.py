"""Add ticket acceptance criteria.

Revision ID: f3b9d7c2a5e1
Revises: c4d5e6f7a8b9
Create Date: 2024-01-03 00:00:00.000000

Structured acceptance criteria rows (ADR-0025): one row per criterion with its
ordinal position, text, and the verifier's sign-off state. Table name follows
the existing SQLModel default pattern (cf. `ticketlabel`, `ticketlink`).

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f3b9d7c2a5e1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticketcriterion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticketcriterion_ticket_id"), "ticketcriterion", ["ticket_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticketcriterion_ticket_id"), table_name="ticketcriterion")
    op.drop_table("ticketcriterion")
