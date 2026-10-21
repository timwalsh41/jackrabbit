"""Add labels and ticket-label attachments.

Revision ID: b2f6c1d4e7a9
Revises: dd5c9a836974
Create Date: 2024-01-02 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2f6c1d4e7a9"
down_revision = "dd5c9a836974"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Label registry: globally scoped, case-insensitive identity via name_key.
    op.create_table(
        "label",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("name_key", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_key", name="uq_label_name_key"),
    )
    op.create_index(op.f("ix_label_name"), "label", ["name"], unique=False)
    op.create_index(op.f("ix_label_name_key"), "label", ["name_key"], unique=False)

    # Attachments of labels to tickets.
    op.create_table(
        "ticketlabel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["label.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "label_id", name="uq_ticket_label_ticket_label"),
    )
    op.create_index(op.f("ix_ticketlabel_ticket_id"), "ticketlabel", ["ticket_id"], unique=False)
    op.create_index(op.f("ix_ticketlabel_label_id"), "ticketlabel", ["label_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticketlabel_label_id"), table_name="ticketlabel")
    op.drop_index(op.f("ix_ticketlabel_ticket_id"), table_name="ticketlabel")
    op.drop_table("ticketlabel")

    op.drop_index(op.f("ix_label_name_key"), table_name="label")
    op.drop_index(op.f("ix_label_name"), table_name="label")
    op.drop_table("label")
