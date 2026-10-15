"""Initial migration - create all tables and seed UNS project.

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create project table
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prefix", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("color", sa.String(), nullable=False, server_default="#6366f1"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prefix"),
    )
    op.create_index(op.f("ix_project_prefix"), "project", ["prefix"], unique=True)

    # Create sprint table
    op.create_table(
        "sprint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_duration_days", sa.Integer(), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index(op.f("ix_sprint_number"), "sprint", ["number"], unique=True)

    # Create ticket table
    op.create_table(
        "ticket",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False, server_default="Story"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Open"),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="Medium"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("story_points", sa.Integer(), nullable=True),
        sa.Column("sprint_id", sa.Integer(), nullable=True),
        sa.Column("branch_name", sa.String(), nullable=True),
        sa.Column("pr_url", sa.String(), nullable=True),
        sa.Column("original_id", sa.String(), nullable=True),
        sa.Column("approach", sa.String(), nullable=False, server_default=""),
        sa.Column("files_to_change", sa.String(), nullable=False, server_default=""),
        sa.Column("test_plan", sa.String(), nullable=False, server_default=""),
        sa.Column("validation_steps", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.ForeignKeyConstraint(
            ["sprint_id"],
            ["sprint.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "number", name="uq_ticket_project_number"),
    )
    op.create_index(op.f("ix_ticket_project_id"), "ticket", ["project_id"], unique=False)
    op.create_index(op.f("ix_ticket_sprint_id"), "ticket", ["sprint_id"], unique=False)
    op.create_index(op.f("ix_ticket_status"), "ticket", ["status"], unique=False)
    op.create_index(op.f("ix_ticket_priority"), "ticket", ["priority"], unique=False)
    op.create_index(op.f("ix_ticket_original_id"), "ticket", ["original_id"], unique=False)

    # Create ticket_link table
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

    # Create ticket_transition table
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

    # Seed UNS project
    op.execute(
        "INSERT INTO project (id, prefix, name, description, color, is_system, "
        "created_at, updated_at) VALUES (1, 'UNS', 'Unsorted', "
        "'Default project for unsorted tickets', '#9ca3af', 1, "
        "datetime('now'), datetime('now'))"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_transition_ticket_id"), table_name="ticket_transition")
    op.drop_table("ticket_transition")
    op.drop_index(op.f("ix_ticket_link_target_id"), table_name="ticket_link")
    op.drop_index(op.f("ix_ticket_link_source_id"), table_name="ticket_link")
    op.drop_table("ticket_link")
    op.drop_index(op.f("ix_ticket_original_id"), table_name="ticket")
    op.drop_index(op.f("ix_ticket_priority"), table_name="ticket")
    op.drop_index(op.f("ix_ticket_status"), table_name="ticket")
    op.drop_index(op.f("ix_ticket_sprint_id"), table_name="ticket")
    op.drop_index(op.f("ix_ticket_project_id"), table_name="ticket")
    op.drop_table("ticket")
    op.drop_index(op.f("ix_sprint_number"), table_name="sprint")
    op.drop_table("sprint")
    op.drop_index(op.f("ix_project_prefix"), table_name="project")
    op.drop_table("project")
