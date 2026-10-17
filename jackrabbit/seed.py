"""Deterministic demo dataset for exploring and exercising Jackrabbit locally.

`uv run server.py seed` (also `make db-seed`) fills a database with data that
touches every screen and every state the app can render: all six ticket
statuses, all four ticket types, an epic with children, a blocking dependency,
tickets inside and outside sprints, three sprints (active, current, planned)
dated relative to today, and one ticket that has been moved between projects so
the "Formerly" badge has something to show.

Seeding is **idempotent**: entities are found by their natural key (project
prefix, sprint name, ticket title, link triple) and only missing pieces are
created, so a second run changes nothing. Statuses are reached by walking the
real guarded transitions through :meth:`TicketService.transition`, so the demo
data carries genuine audit history instead of a faked status column.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, select

from jackrabbit.models import (
    LinkType,
    Priority,
    Project,
    Sprint,
    Ticket,
    TicketLink,
    TicketStatus,
    TicketType,
)
from jackrabbit.services import LinkService, ProjectService, SprintService, TicketService

# Written into every seeded ticket's description so seeded rows stay
# recognisable next to hand-created ones.
DEMO_NOTE = "Seeded demo data"

# The four structured fields a ticket needs before it can be Groomed (ADR-0008).
GROOMING_FIELDS = {
    "approach": "Extend the existing service layer and keep the API contract stable.",
    "files_to_change": "jackrabbit/services.py, jackrabbit/api.py, tests/unit/test_seed.py",
    "test_plan": "Unit tests for the new branch, plus an integration test per endpoint.",
    "validation_steps": "make test, then walk the flow in the browser.",
}

_PR_URL = "https://github.com/timwalsh41/jackrabbit/pull/1"

# Ordered chain used to walk a ticket forward, so history reads like real work.
_FORWARD_CHAIN = (
    TicketStatus.GROOMED,
    TicketStatus.IN_PROGRESS,
    TicketStatus.READY_FOR_REVIEW,
    TicketStatus.COMPLETE,
)

PROJECTS: tuple[tuple[str, str, str], ...] = (
    ("WEB", "Web Application", "#6366f1"),
    ("API", "Backend API", "#10b981"),
    ("MSC", "Misc", "#f59e0b"),
)

SPRINT_NAMES: tuple[str, ...] = tuple(
    f"{DEMO_NOTE}: {label} sprint" for label in ("current", "next", "later")
)

# (planned_start_offset, planned_end_offset, actual_start_offset or None)
_SPRINT_WINDOWS: tuple[tuple[int, int, int | None], ...] = (
    (-4, 6, -4),
    (7, 21, None),
    (28, 42, None),
)


@dataclass(frozen=True)
class TicketSpec:
    """One demo ticket: what it is, and how far it has been worked."""

    project: str
    title: str
    type: TicketType = TicketType.STORY
    priority: Priority = Priority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    story_points: int | None = None
    sprint: int | None = None  # index into SPRINT_NAMES
    detail: str = ""
    children: tuple[str, ...] = ()  # epic -> child ticket titles (PARENT links)
    moved_to: str | None = None  # project the ticket is moved to after creation


@dataclass(frozen=True)
class LinkSpec:
    """A non-hierarchy link between two demo tickets, addressed by project+title."""

    source: tuple[str, str]
    target: tuple[str, str]
    link_type: LinkType


_TICKETS: tuple[TicketSpec, ...] = (
    TicketSpec(
        project="WEB",
        title="Customer portal revamp",
        type=TicketType.EPIC,
        detail="umbrella epic for the portal work",
        children=(
            "Add SSO login",
            "Show session timeout banner",
            "Send password reset email",
            "Export billing history",
        ),
    ),
    TicketSpec(
        project="WEB",
        title="Add SSO login",
        status=TicketStatus.GROOMED,
        story_points=5,
        sprint=0,
        priority=Priority.HIGH,
        detail="OIDC against the corporate identity provider",
    ),
    TicketSpec(
        project="WEB",
        title="Show session timeout banner",
        status=TicketStatus.IN_PROGRESS,
        story_points=3,
        sprint=0,
        detail="warn 60s before expiry, extend with one click",
    ),
    TicketSpec(
        project="WEB",
        title="Send password reset email",
        status=TicketStatus.READY_FOR_REVIEW,
        story_points=3,
        sprint=0,
        detail="signed one-time link with a 15 minute TTL",
    ),
    TicketSpec(
        project="WEB",
        title="Export billing history",
        status=TicketStatus.COMPLETE,
        story_points=8,
        priority=Priority.LOW,
        detail="CSV export of the last 24 months",
    ),
    TicketSpec(
        project="WEB",
        title="Add invoice PDF preview",
        story_points=5,
        sprint=1,
        priority=Priority.HIGH,
        detail="inline preview before download",
    ),
    TicketSpec(
        project="WEB",
        title="Recurring invoice total is wrong",
        type=TicketType.BUG,
        priority=Priority.CRITICAL,
        sprint=1,
        detail="proration is applied twice on an upgrade",
    ),
    TicketSpec(
        project="WEB",
        title="Evaluate audit-log storage options",
        type=TicketType.SPIKE,
        story_points=2,
        detail="compare SQLite, Postgres and object storage",
    ),
    TicketSpec(
        project="API",
        title="Rate-limit middleware",
        status=TicketStatus.GROOMED,
        story_points=5,
        sprint=1,
        detail="token bucket keyed on the API key",
    ),
    TicketSpec(
        project="API",
        title="Idempotency keys for ticket creation",
        story_points=8,
        sprint=2,
        detail="Idempotency-Key header with a 24 hour window",
    ),
    TicketSpec(
        project="API",
        title="Deprecate v0 endpoints",
        priority=Priority.LOW,
        status=TicketStatus.REJECTED,
        detail="no consumers left to migrate",
    ),
    TicketSpec(
        project="MSC",
        title="Investigate flaky backlog filter test",
        detail="fails only on the second run of the suite",
        moved_to="WEB",
    ),
    TicketSpec(
        project="UNS",
        title="Triage: inbound support request",
        detail="sits in the system project until it is sorted",
    ),
)

_LINKS: tuple[LinkSpec, ...] = (
    LinkSpec(
        source=("WEB", "Recurring invoice total is wrong"),
        target=("WEB", "Add invoice PDF preview"),
        link_type=LinkType.BLOCKS,
    ),
    LinkSpec(
        source=("WEB", "Evaluate audit-log storage options"),
        target=("API", "Rate-limit middleware"),
        link_type=LinkType.RELATES_TO,
    ),
)

# Tickets with `moved_to` set are moved into that project once, to exercise
# renumbering and the "Formerly" badge (see TicketSpec.moved_to).


@dataclass
class SeedResult:
    """What a seeding run created -- all empty on a repeat run."""

    projects: list[str] = field(default_factory=list)
    sprints: list[int] = field(default_factory=list)
    tickets: list[str] = field(default_factory=list)
    links: int = 0
    transitions: int = 0
    moves: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.projects or self.sprints or self.tickets or self.links or self.moves)

    def summary(self) -> str:
        if not self.changed:
            return "Demo data already present - nothing to do."
        return (
            f"Seeded {len(self.tickets)} ticket(s), {len(self.projects)} project(s), "
            f"{len(self.sprints)} sprint(s), {self.links} link(s) and {self.moves} move(s) "
            f"across {self.transitions} recorded transition(s)."
        )


def _day_offset(days: int) -> datetime:
    """Naive midnight `days` from today (Sprint date columns are NaiveDatetime)."""
    return datetime.combine(date.today() + timedelta(days=days), time(0, 0))


def _find_ticket(session: Session, project: Project, title: str) -> Ticket | None:
    return session.exec(
        select(Ticket).where(Ticket.project_id == project.id, Ticket.title == title)
    ).first()


def _link_exists(session: Session, source: Ticket, target: Ticket, link_type: LinkType) -> bool:
    return (
        session.exec(
            select(TicketLink).where(
                TicketLink.source_id == source.id,
                TicketLink.target_id == target.id,
                TicketLink.link_type == link_type,
            )
        ).first()
        is not None
    )


class _Seeder:
    """Holds the services and the running tally so the helpers stay small."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.result = SeedResult()
        self.projects = ProjectService(session)
        self.sprints = SprintService(session)
        self.tickets = TicketService(session)
        self.links = LinkService(session)
        self._project_by_prefix: dict[str, Project] = {}
        self._sprint_by_index: dict[int, Sprint] = {}

    # -- projects ---------------------------------------------------------
    def ensure_projects(self) -> None:
        for prefix, name, color in PROJECTS:
            project = self.projects.get_project_by_prefix(prefix)
            if project is None:
                project = self.projects.create_project(prefix=prefix, name=name, color=color)
                self.result.projects.append(prefix)
            self._project_by_prefix[prefix] = project

        # UNS is created by migration 0001 (ADR-0017); seed never makes it.
        uns = self.projects.get_project_by_prefix("UNS")
        if uns is None:
            raise RuntimeError("UNS system project is missing; run init-db before seeding")
        self._project_by_prefix["UNS"] = uns

    # -- sprints ----------------------------------------------------------
    def ensure_sprints(self) -> None:
        existing = {sprint.name: sprint for sprint in self.sprints.list_sprints()}
        for index, (start, end, actual) in enumerate(_SPRINT_WINDOWS):
            name = SPRINT_NAMES[index]
            sprint = existing.get(name)
            if sprint is None:
                sprint = self.sprints.create_sprint(
                    name=name,
                    description=f"{DEMO_NOTE}: sprint used for local exploration",
                    planned_start=_day_offset(start),
                    planned_end=_day_offset(end),
                    planned_duration_days=end - start,
                    actual_start=_day_offset(actual) if actual is not None else None,
                )
                self.result.sprints.append(sprint.number)
            self._sprint_by_index[index] = sprint

    # -- tickets ----------------------------------------------------------
    def ensure_ticket(self, spec: TicketSpec) -> Ticket:
        project = self._project_by_prefix[spec.project]
        ticket = _find_ticket(self.session, project, spec.title)
        if ticket is None and spec.moved_to:
            # Already moved by an earlier run: it now lives in the target project.
            ticket = _find_ticket(self.session, self._project_by_prefix[spec.moved_to], spec.title)
        if ticket is None:
            ticket = self.tickets.create_ticket(
                project_id=project.id or 0,
                title=spec.title,
                type=spec.type,
                priority=spec.priority,
                story_points=spec.story_points,
                description=f"{DEMO_NOTE}: {spec.detail}" if spec.detail else DEMO_NOTE,
            )
            self.result.tickets.append(f"{project.prefix}-{ticket.number:03d}")

        self._advance(ticket, spec.status)

        if spec.sprint is not None:
            sprint = self._sprint_by_index[spec.sprint]
            if ticket.sprint_id != sprint.id:
                self.sprints.assign_ticket_to_sprint(sprint.id or 0, ticket.id or 0)
        return ticket

    def _advance(self, ticket: Ticket, target: TicketStatus) -> None:
        """Drive a ticket to ``target`` through the guarded transitions."""
        if ticket.status == target:
            return
        if target == TicketStatus.REJECTED:
            self.tickets.transition(
                ticket, TicketStatus.REJECTED, reason="deferred: no capacity this sprint"
            )
            self.result.transitions += 1
            return

        for status in _FORWARD_CHAIN[: _FORWARD_CHAIN.index(target) + 1]:
            if self._rank(ticket.status) >= self._rank(status):
                continue
            if status == TicketStatus.GROOMED:
                self.tickets.update_ticket(ticket, **GROOMING_FIELDS)
            elif status == TicketStatus.READY_FOR_REVIEW:
                self.tickets.update_ticket(ticket, pr_url=_PR_URL)
            self.tickets.transition(ticket, status, reason=f"seeded: now {status.value}")
            self.result.transitions += 1

    @staticmethod
    def _rank(status: TicketStatus) -> int:
        return _FORWARD_CHAIN.index(status) + 1 if status in _FORWARD_CHAIN else 0

    # -- links ------------------------------------------------------------
    def ensure_link(self, source: Ticket, target: Ticket, link_type: LinkType) -> None:
        if _link_exists(self.session, source, target, link_type):
            return
        self.links.create_link(source.id or 0, target.id or 0, link_type)
        self.result.links += 1

    def ensure_hierarchies(self) -> None:
        """Epic -> story hierarchy is expressed with links, not schema (ADR-0007)."""
        for spec in _TICKETS:
            if not spec.children:
                continue
            project = self._project_by_prefix[spec.project]
            epic = _find_ticket(self.session, project, spec.title)
            if epic is None:  # pragma: no cover - just created above
                continue
            for child_title in spec.children:
                child = _find_ticket(self.session, project, child_title)
                if child is not None:
                    self.ensure_link(epic, child, LinkType.PARENT)

    def ensure_links(self) -> None:
        for spec in _LINKS:
            source = self._ticket_by_key(spec.source)
            target = self._ticket_by_key(spec.target)
            if source is not None and target is not None:
                self.ensure_link(source, target, spec.link_type)

    def _ticket_by_key(self, key: tuple[str, str]) -> Ticket | None:
        return _find_ticket(self.session, self._project_by_prefix[key[0]], key[1])

    # -- project move -----------------------------------------------------
    def ensure_moves(self) -> None:
        """Move each `moved_to` ticket exactly once, leaving original_id set.

        After the move the ticket no longer resolves in its source project, so a
        repeat run has nothing to do -- which is also why `ensure_ticket` looks
        for moved tickets in their destination project before creating one.
        """
        for spec in _TICKETS:
            if not spec.moved_to:
                continue
            source = self._project_by_prefix[spec.project]
            target = self._project_by_prefix[spec.moved_to]
            ticket = _find_ticket(self.session, source, spec.title)
            if ticket is None:
                continue  # already moved
            self.tickets.move_ticket_to_project(ticket.id or 0, target.id or 0)
            self.result.moves += 1


def seed_demo_data(session: Session) -> SeedResult:
    """Create (or top up) the demo dataset in the database behind ``session``."""
    seeder = _Seeder(session)
    seeder.ensure_projects()
    seeder.ensure_sprints()
    for spec in _TICKETS:
        seeder.ensure_ticket(spec)
    seeder.ensure_hierarchies()
    seeder.ensure_links()
    seeder.ensure_moves()
    return seeder.result
