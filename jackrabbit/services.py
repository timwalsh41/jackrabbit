"""Business logic services for Jackrabbit."""

from datetime import UTC, datetime

from sqlmodel import Session, func, select

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


def utc_now() -> datetime:
    return datetime.now(UTC)


class TicketService:
    def __init__(self, session: Session):
        self.session = session

    def create_ticket(
        self,
        project_id: int,
        title: str,
        type: TicketType = TicketType.STORY,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        story_points: int | None = None,
    ) -> Ticket:
        # Get next ticket number for project
        max_num = self.session.exec(
            select(func.max(Ticket.number)).where(Ticket.project_id == project_id)
        ).first()
        next_number = (max_num or 0) + 1

        ticket = Ticket(
            project_id=project_id,
            number=next_number,
            type=type,
            title=title,
            description=description,
            priority=priority,
            story_points=story_points,
        )
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def get_ticket(self, ticket_id: int) -> Ticket | None:
        return self.session.get(Ticket, ticket_id)

    def get_ticket_by_full_id(self, project_prefix: str, number: int) -> Ticket | None:
        project = self.session.exec(select(Project).where(Project.prefix == project_prefix)).first()
        if not project:
            return None
        return self.session.exec(
            select(Ticket).where(
                Ticket.project_id == project.id,
                Ticket.number == number,
            )
        ).first()

    def update_status(self, ticket: Ticket, status: TicketStatus) -> Ticket:
        ticket.status = status
        ticket.updated_at = utc_now()
        if status == TicketStatus.COMPLETE:
            ticket.completed_at = utc_now()
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def list_tickets(
        self,
        project_id: int | None = None,
        status: TicketStatus | None = None,
        type: TicketType | None = None,
        sprint_id: int | None = None,
    ) -> list[Ticket]:
        query = select(Ticket)
        if project_id:
            query = query.where(Ticket.project_id == project_id)
        if status:
            query = query.where(Ticket.status == status)
        if type:
            query = query.where(Ticket.type == type)
        if sprint_id:
            query = query.where(Ticket.sprint_id == sprint_id)
        return list(self.session.exec(query).all())


class ProjectService:
    def __init__(self, session: Session):
        self.session = session

    def create_project(
        self,
        prefix: str,
        name: str,
        description: str = "",
        color: str = "#6366f1",
        is_system: bool = False,
    ) -> Project:
        project = Project(
            prefix=prefix.upper(),
            name=name,
            description=description,
            color=color,
            is_system=is_system,
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def get_project(self, project_id: int) -> Project | None:
        return self.session.get(Project, project_id)

    def get_project_by_prefix(self, prefix: str) -> Project | None:
        return self.session.exec(select(Project).where(Project.prefix == prefix.upper())).first()

    def list_projects(self) -> list[Project]:
        return list(self.session.exec(select(Project)).all())


class SprintService:
    def __init__(self, session: Session):
        self.session = session

    def create_sprint(
        self,
        number: str,
        name: str = "",
        description: str = "",
        planned_start: datetime | None = None,
        planned_end: datetime | None = None,
    ) -> Sprint:
        sprint = Sprint(
            number=number,
            name=name,
            description=description,
            planned_start=planned_start,
            planned_end=planned_end,
        )
        self.session.add(sprint)
        self.session.commit()
        self.session.refresh(sprint)
        return sprint

    def get_sprint(self, sprint_id: int) -> Sprint | None:
        return self.session.get(Sprint, sprint_id)

    def get_sprint_by_number(self, number: str) -> Sprint | None:
        return self.session.exec(select(Sprint).where(Sprint.number == number)).first()

    def list_sprints(self) -> list[Sprint]:
        return list(self.session.exec(select(Sprint)).all())


class LinkService:
    def __init__(self, session: Session):
        self.session = session

    def create_link(self, source_id: int, target_id: int, link_type: LinkType) -> TicketLink:
        # Check for duplicate
        existing = self.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == source_id,
                TicketLink.target_id == target_id,
                TicketLink.link_type == link_type,
            )
        ).first()
        if existing:
            return existing

        link = TicketLink(
            source_id=source_id,
            target_id=target_id,
            link_type=link_type,
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def delete_link(self, link_id: int) -> bool:
        link = self.session.get(TicketLink, link_id)
        if not link:
            return False
        self.session.delete(link)
        self.session.commit()
        return True

    def get_links_for_ticket(self, ticket_id: int) -> list[TicketLink]:
        return list(
            self.session.exec(
                select(TicketLink).where(
                    (TicketLink.source_id == ticket_id) | (TicketLink.target_id == ticket_id)
                )
            ).all()
        )
