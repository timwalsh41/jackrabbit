"""Single-parent enforcement: partial unique indexes on ticketlink.

JRB-019 review remediation: enforce at the DB level that a ticket can have at
most one parent. PARENT and CHILD are inverse links of the same relation, so
two partial unique indexes cover it from both directions:

- ``uq_ticket_link_parent_target``: at most one PARENT row per target ticket.
- ``uq_ticket_link_child_source``: at most one CHILD row per source ticket.

App-level enforcement (LinkService.create_link pre-check) already routes the
conflict to ``ParentLinkConflictError`` -> HTTP 409 with the existing parent id;
these indexes backstop concurrent writers that race past the pre-check.

Databases upgraded from the previous revision (b2f6c1d4e7a9) may already
contain conflicting legacy links: the only pre-existing uniqueness was
(source_id, target_id, link_type), so multiple distinct PARENT rows for the
same target were legal. Creating the indexes over that data would fail with
an IntegrityError during application startup, so ``upgrade()`` first resolves
the conflicts (keeps the most recently created link per group and removes the
now-orphaned inverse rows); see the inline comments.

Revision ID: c4d5e6f7a8b9
Revises: b2f6c1d4e7a9
Create Date: 2024-01-03 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "b2f6c1d4e7a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Legacy databases may hold multiple distinct PARENT rows for the same
    # target ticket (legal before this revision). Creating the partial unique
    # indexes over that data would fail with an IntegrityError, aborting the
    # upgrade that runs during application startup. Resolve the conflicts
    # first: for each target ticket keep the most recently created PARENT row
    # (highest id) and delete the rest.
    conn.execute(
        text(
            """
            DELETE FROM ticketlink
            WHERE link_type IN ('PARENT', 'parent')
              AND id NOT IN (
                  SELECT MAX(id) FROM ticketlink
                  WHERE link_type IN ('PARENT', 'parent')
                  GROUP BY target_id
              )
            """
        )
    )
    # PARENT and CHILD are inverses of one relation (create_link always
    # inserts/removes them in pairs), so a CHILD row whose inverse PARENT no
    # longer exists is stale: it was orphaned by the deletion above or was
    # already unpaired in legacy data. Removing it both keeps the pair
    # invariant and guarantees the CHILD-side index can be created safely
    # (every surviving CHILD row's inverse PARENT survived the dedupe).
    conn.execute(
        text(
            """
            DELETE FROM ticketlink
            WHERE link_type IN ('CHILD', 'child')
              AND NOT EXISTS (
                  SELECT 1 FROM ticketlink AS parent
                  WHERE parent.link_type IN ('PARENT', 'parent')
                    AND parent.source_id = ticketlink.target_id
                    AND parent.target_id = ticketlink.source_id
              )
            """
        )
    )

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
    # Note: the legacy-conflict resolution above is one-way; downgrade only
    # drops the indexes and does not resurrect the removed duplicate rows.
    op.drop_index("uq_ticket_link_child_source", table_name="ticketlink")
    op.drop_index("uq_ticket_link_parent_target", table_name="ticketlink")
