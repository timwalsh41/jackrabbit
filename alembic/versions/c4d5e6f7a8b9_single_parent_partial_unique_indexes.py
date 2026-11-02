"""Single-parent enforcement: partial unique indexes on ticketlink.

JRB-019 review remediation: enforce at the DB level that a ticket can have at
most one parent. PARENT and CHILD are inverse links of the same relation, so
two partial unique indexes cover it from both directions:

- ``uq_ticket_link_parent_target``: at most one PARENT row per target ticket.
- ``uq_ticket_link_child_source``: at most one CHILD row per source ticket.

App-level enforcement (LinkService.create_link pre-check) already routes the
conflict to ``ParentLinkConflictError`` -> HTTP 409; these indexes backstop
concurrent writers that race past the pre-check, and the resulting
IntegrityError is mapped onto the same 409 path in create_link.

Revision ID: c4d5e6f7a8b9
Revises: b2f6c1d4e7a9
Create Date: 2024-01-03 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "b2f6c1d4e7a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy/SQLModel persist StrEnum columns as the member *name*
    # ('PARENT', 'CHILD'), so the WHERE clauses match both spellings.
    op.create_index(
        "uq_ticket_link_parent_target",
        "ticketlink",
        ["target_id"],
        unique=True,
        sqlite_where=sa.text("link_type IN ('PARENT', 'parent')"),
    )
    op.create_index(
        "uq_ticket_link_child_source",
        "ticketlink",
        ["source_id"],
        unique=True,
        sqlite_where=sa.text("link_type IN ('CHILD', 'child')"),
    )


def downgrade() -> None:
    op.drop_index("uq_ticket_link_child_source", table_name="ticketlink")
    op.drop_index("uq_ticket_link_parent_target", table_name="ticketlink")
