"""Migrate legacy description checkboxes into criteria rows.

JRB-024 one-time data migration (ADR-0025): parse the legacy markdown
"Acceptance criteria" checkbox section of every ticket description into
unchecked ``ticketcriterion`` rows in document order, remove that section
from the description, and leave everything else — notably "Agent Execution
Evidence" — untouched. Legacy ``- [x]`` boxes import as unchecked rows too.

Malformed checkbox lists (prose inside the list, empty items, several
matching headings) are *not* touched: their descriptions stay exactly as
they were and each case is logged as a warning, so nothing is silently
mis-shaped. Run ``report-legacy-criteria`` (CLI dry-run report) before
upgrading to review them; see ``jackrabbit/legacy_criteria.py`` for the
exact parsing rules.

The downgrade is a no-op: checkbox markdown cannot be faithfully
reconstructed from criterion rows, so migrated data is kept.

Revision ID: d9c3f7b1a5e8
Revises: f3b9d7c2a5e1
Create Date: 2024-01-04 00:00:00.000000

"""

import logging

import sqlalchemy as sa
from alembic import op
from jackrabbit.legacy_criteria import parse_legacy_criteria

_logger = logging.getLogger("alembic.d9c3f7b1a5e8")

# revision identifiers, used by Alembic.
revision = "d9c3f7b1a5e8"
down_revision = "f3b9d7c2a5e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, description FROM ticket ORDER BY id")).all()

    for ticket_id, description in rows:
        parsed = parse_legacy_criteria(description)
        if parsed.warnings:
            for warning in parsed.warnings:
                _logger.warning(
                    "Ticket %s: legacy acceptance-criteria section left untouched: %s",
                    ticket_id,
                    warning,
                )
            continue
        if not parsed.criteria:
            continue
        for position, criterion_text in enumerate(parsed.criteria):
            conn.execute(
                sa.text(
                    "INSERT INTO ticketcriterion (ticket_id, position, text, "
                    "verified, created_at) VALUES (:tid, :position, :criterion_text, "
                    "0, CURRENT_TIMESTAMP)"
                ),
                {"tid": ticket_id, "position": position, "criterion_text": criterion_text},
            )
        conn.execute(
            sa.text("UPDATE ticket SET description = :description WHERE id = :tid"),
            {"description": parsed.description_without_section, "tid": ticket_id},
        )


def downgrade() -> None:
    # Data migration: legacy checkbox markdown cannot be reconstructed from
    # criterion rows, so the downgrade intentionally keeps migrated data.
    pass
