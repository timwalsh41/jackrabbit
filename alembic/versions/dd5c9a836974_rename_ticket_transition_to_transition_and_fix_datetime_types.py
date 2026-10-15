"""Rename ticket_transition to transition and fix datetime types.

Revision ID: dd5c9a836974
Revises: 0001
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "dd5c9a836974"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create new ticketlink table (replaces ticket_link)
    op.create_table(
        "ticketlink",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["ticket.id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "target_id", "link_type", name="uq_ticketlink_source_target_type"
        ),
    )
    op.create_index(op.f("ix_ticketlink_source_id"), "ticketlink", ["source_id"], unique=False)
    op.create_index(op.f("ix_ticketlink_target_id"), "ticketlink", ["target_id"], unique=False)

    # Create new transition table (replaces ticket_transition)
    op.create_table(
        "transition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transition_ticket_id"), "transition", ["ticket_id"], unique=False)

    # Copy data from ticket_link to ticketlink
    op.execute(
        "INSERT INTO ticketlink (id, source_id, target_id, link_type, created_at) "
        "SELECT id, source_id, target_id, link_type, created_at FROM ticket_link"
    )

    # Copy data from ticket_transition to transition
    op.execute(
        "INSERT INTO transition (id, ticket_id, from_status, to_status, reason, at) "
        "SELECT id, ticket_id, from_status, to_status, reason, at FROM ticket_transition"
    )

    # Drop old tables
    op.drop_index(op.f("ix_ticket_link_target_id"), table_name="ticket_link")
    op.drop_index(op.f("ix_ticket_link_source_id"), table_name="ticket_link")
    op.drop_table("ticket_link")
    op.drop_index(op.f("ix_ticket_transition_ticket_id"), table_name="ticket_transition")
    op.drop_table("ticket_transition")

    # Note: SQLite doesn't support ALTER COLUMN TYPE for enums, so we leave the string columns as-is
    # The application layer will handle enum validation


def downgrade() -> None:
    # Recreate ticket_link table
    op.create_table(
        "ticket_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["ticket.id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "target_id", "link_type", name="uq_ticket_link_source_target_type"
        ),
    )
    op.create_index(op.f("ix_ticket_link_source_id"), "ticket_link", ["source_id"], unique=False)
    op.create_index(op.f("ix_ticket_link_target_id"), "ticket_link", ["target_id"], unique=False)

    # Recreate ticket_transition table
    op.create_table(
        "ticket_transition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_transition_ticket_id"), "ticket_transition", ["ticket_id"], unique=False
    )

    # Copy data back
    op.execute(
        "INSERT INTO ticket_link (id, source_id, target_id, link_type, created_at) "
        "SELECT id, source_id, target_id, link_type, created_at FROM ticketlink"
    )
    op.execute(
        "INSERT INTO ticket_transition (id, ticket_id, from_status, to_status, reason, at) "
        "SELECT id, ticket_id, from_status, to_status, reason, at FROM transition"
    )

    # Drop new tables
    op.drop_index(op.f("ix_ticketlink_target_id"), table_name="ticketlink")
    op.drop_index(op.f("ix_ticketlink_source_id"), table_name="ticketlink")
    op.drop_table("ticketlink")
    op.drop_index(op.f("ix_transition_ticket_id"), table_name="transition")
    op.drop_table("transition")
