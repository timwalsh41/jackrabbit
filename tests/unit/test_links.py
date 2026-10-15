"""Unit tests for ticket link functionality."""

import pytest
from jackrabbit.models import (
    LinkType,
    Project,
    TicketLink,
    TicketType,
)
from jackrabbit.services import LinkService, ProjectService, TicketService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select


def get_test_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


def get_test_session(engine):
    """Create a test session with initialized schema."""
    from jackrabbit.models import SQLModel

    SQLModel.metadata.create_all(engine)
    # Seed UNS project
    with Session(engine) as session:
        uns = Project(
            id=1,
            prefix="UNS",
            name="Unsorted",
            description="Default",
            color="#9ca3af",
            is_system=True,
        )
        session.add(uns)
        session.commit()
    return Session(engine)


@pytest.fixture
def session():
    engine = get_test_engine()
    session = get_test_session(engine)
    yield session
    session.close()


@pytest.fixture
def ticket_service(session):
    return TicketService(session)


@pytest.fixture
def project_service(session):
    return ProjectService(session)


@pytest.fixture
def link_service(session):
    return LinkService(session)


@pytest.fixture
def test_project(project_service):
    """Create a test project."""
    return project_service.create_project(prefix="TEST", name="Test Project")


@pytest.fixture
def epic_ticket(ticket_service, test_project):
    """Create an Epic ticket."""
    return ticket_service.create_ticket(
        project_id=test_project.id,
        title="Epic Ticket",
        type=TicketType.EPIC,
    )


@pytest.fixture
def story_ticket(ticket_service, test_project):
    """Create a Story ticket."""
    return ticket_service.create_ticket(
        project_id=test_project.id,
        title="Story Ticket",
        type=TicketType.STORY,
    )


@pytest.fixture
def bug_ticket(ticket_service, test_project):
    """Create a Bug ticket."""
    return ticket_service.create_ticket(
        project_id=test_project.id,
        title="Bug Ticket",
        type=TicketType.BUG,
    )


@pytest.fixture
def spike_ticket(ticket_service, test_project):
    """Create a Spike ticket."""
    return ticket_service.create_ticket(
        project_id=test_project.id,
        title="Spike Ticket",
        type=TicketType.SPIKE,
    )


class TestLinkCreation:
    """Tests for link creation and inverse creation."""

    def test_create_parent_link(self, link_service, epic_ticket, story_ticket):
        """Epic -> Story creates parent + child inverse."""
        link = link_service.create_link(epic_ticket.id, story_ticket.id, LinkType.PARENT)

        assert link.source_id == epic_ticket.id
        assert link.target_id == story_ticket.id
        assert link.link_type == LinkType.PARENT

        # Check inverse was created
        child_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == story_ticket.id,
                TicketLink.target_id == epic_ticket.id,
                TicketLink.link_type == LinkType.CHILD,
            )
        ).first()
        assert child_link is not None
        assert child_link.link_type == LinkType.CHILD

    def test_create_child_link(self, link_service, epic_ticket, story_ticket):
        """Story -> Epic creates child + parent inverse."""
        link = link_service.create_link(story_ticket.id, epic_ticket.id, LinkType.CHILD)

        assert link.source_id == story_ticket.id
        assert link.target_id == epic_ticket.id
        assert link.link_type == LinkType.CHILD

        # Check inverse was created
        parent_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == epic_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.PARENT,
            )
        ).first()
        assert parent_link is not None
        assert parent_link.link_type == LinkType.PARENT

    def test_create_blocks_link(self, link_service, story_ticket, bug_ticket):
        """Story -> Bug creates blocks + blocked_by inverse."""
        link = link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.BLOCKS)

        assert link.source_id == story_ticket.id
        assert link.target_id == bug_ticket.id
        assert link.link_type == LinkType.BLOCKS

        # Check inverse was created
        blocked_by_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == bug_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.BLOCKED_BY,
            )
        ).first()
        assert blocked_by_link is not None
        assert blocked_by_link.link_type == LinkType.BLOCKED_BY

    def test_create_blocked_by_link(self, link_service, story_ticket, bug_ticket):
        """Bug -> Story creates blocked_by + blocks inverse."""
        link = link_service.create_link(bug_ticket.id, story_ticket.id, LinkType.BLOCKED_BY)

        assert link.source_id == bug_ticket.id
        assert link.target_id == story_ticket.id
        assert link.link_type == LinkType.BLOCKED_BY

        # Check inverse was created
        blocks_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == story_ticket.id,
                TicketLink.target_id == bug_ticket.id,
                TicketLink.link_type == LinkType.BLOCKS,
            )
        ).first()
        assert blocks_link is not None
        assert blocks_link.link_type == LinkType.BLOCKS

    def test_create_relates_to_link(self, link_service, story_ticket, bug_ticket):
        """Story -> Bug creates symmetric relates_to links."""
        link = link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.RELATES_TO)

        assert link.source_id == story_ticket.id
        assert link.target_id == bug_ticket.id
        assert link.link_type == LinkType.RELATES_TO

        # Check symmetric link was created
        reverse_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == bug_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.RELATES_TO,
            )
        ).first()
        assert reverse_link is not None
        assert reverse_link.link_type == LinkType.RELATES_TO

    def test_prevent_self_link(self, link_service, story_ticket):
        """Cannot link a ticket to itself."""
        with pytest.raises(ValueError) as exc_info:
            link_service.create_link(story_ticket.id, story_ticket.id, LinkType.RELATES_TO)
        assert "Cannot link a ticket to itself" in str(exc_info.value)

    def test_prevent_duplicate_link(self, link_service, epic_ticket, story_ticket):
        """Duplicate links are not created, existing returned."""
        link1 = link_service.create_link(epic_ticket.id, story_ticket.id, LinkType.PARENT)
        link2 = link_service.create_link(epic_ticket.id, story_ticket.id, LinkType.PARENT)

        assert link1.id == link2.id

        # Only one link should exist
        links = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == epic_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.PARENT,
            )
        ).all()
        assert len(links) == 1

    def test_parent_link_validation_source_must_be_epic(
        self, link_service, story_ticket, bug_ticket
    ):
        """Parent link source must be Epic type."""
        with pytest.raises(ValueError) as exc_info:
            link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.PARENT)
        assert "Parent link source must be an Epic" in str(exc_info.value)

    def test_child_link_validation_target_must_be_epic(
        self, link_service, story_ticket, bug_ticket
    ):
        """Child link target must be Epic type."""
        with pytest.raises(ValueError) as exc_info:
            link_service.create_link(bug_ticket.id, story_ticket.id, LinkType.CHILD)
        assert "Child link target must be an Epic" in str(exc_info.value)

    def test_parent_link_epic_to_epic_allowed(
        self, link_service, epic_ticket, test_project, ticket_service
    ):
        """Epic can be parent of another Epic."""
        epic2 = ticket_service.create_ticket(
            project_id=test_project.id,
            title="Epic 2",
            type=TicketType.EPIC,
        )
        link = link_service.create_link(epic_ticket.id, epic2.id, LinkType.PARENT)
        assert link is not None

    def test_child_link_epic_to_epic_allowed(
        self, link_service, epic_ticket, test_project, ticket_service
    ):
        """Epic can be child of another Epic."""
        epic2 = ticket_service.create_ticket(
            project_id=test_project.id,
            title="Epic 2",
            type=TicketType.EPIC,
        )
        link = link_service.create_link(epic2.id, epic_ticket.id, LinkType.CHILD)
        assert link is not None


class TestLinkDeletion:
    """Tests for link deletion and inverse deletion."""

    def test_delete_parent_link_removes_child_inverse(
        self, link_service, epic_ticket, story_ticket
    ):
        """Deleting parent link removes child inverse."""
        link = link_service.create_link(epic_ticket.id, story_ticket.id, LinkType.PARENT)
        child_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == story_ticket.id,
                TicketLink.target_id == epic_ticket.id,
                TicketLink.link_type == LinkType.CHILD,
            )
        ).first()
        assert child_link is not None

        result = link_service.delete_link(link.id)
        assert result is True

        # Both links should be gone
        parent_link = link_service.session.get(TicketLink, link.id)
        assert parent_link is None

        child_link = link_service.session.get(TicketLink, child_link.id)
        assert child_link is None

    def test_delete_child_link_removes_parent_inverse(
        self, link_service, epic_ticket, story_ticket
    ):
        """Deleting child link removes parent inverse."""
        link = link_service.create_link(story_ticket.id, epic_ticket.id, LinkType.CHILD)
        parent_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == epic_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.PARENT,
            )
        ).first()
        assert parent_link is not None

        result = link_service.delete_link(link.id)
        assert result is True

        # Both links should be gone
        child_link = link_service.session.get(TicketLink, link.id)
        assert child_link is None

        parent_link = link_service.session.get(TicketLink, parent_link.id)
        assert parent_link is None

    def test_delete_blocks_link_removes_blocked_by_inverse(
        self, link_service, story_ticket, bug_ticket
    ):
        """Deleting blocks link removes blocked_by inverse."""
        link = link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.BLOCKS)
        blocked_by_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == bug_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.BLOCKED_BY,
            )
        ).first()
        assert blocked_by_link is not None

        result = link_service.delete_link(link.id)
        assert result is True

        # Both links should be gone
        blocks_link = link_service.session.get(TicketLink, link.id)
        assert blocks_link is None

        blocked_by_link = link_service.session.get(TicketLink, blocked_by_link.id)
        assert blocked_by_link is None

    def test_delete_blocked_by_link_removes_blocks_inverse(
        self, link_service, story_ticket, bug_ticket
    ):
        """Deleting blocked_by link removes blocks inverse."""
        link = link_service.create_link(bug_ticket.id, story_ticket.id, LinkType.BLOCKED_BY)
        blocks_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == story_ticket.id,
                TicketLink.target_id == bug_ticket.id,
                TicketLink.link_type == LinkType.BLOCKS,
            )
        ).first()
        assert blocks_link is not None

        result = link_service.delete_link(link.id)
        assert result is True

        # Both links should be gone
        blocked_by_link = link_service.session.get(TicketLink, link.id)
        assert blocked_by_link is None

        blocks_link = link_service.session.get(TicketLink, blocks_link.id)
        assert blocks_link is None

    def test_delete_relates_to_link_removes_symmetric(self, link_service, story_ticket, bug_ticket):
        """Deleting relates_to link removes symmetric relates_to."""
        link = link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.RELATES_TO)
        reverse_link = link_service.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == bug_ticket.id,
                TicketLink.target_id == story_ticket.id,
                TicketLink.link_type == LinkType.RELATES_TO,
            )
        ).first()
        assert reverse_link is not None

        result = link_service.delete_link(link.id)
        assert result is True

        # Both links should be gone
        forward_link = link_service.session.get(TicketLink, link.id)
        assert forward_link is None

        reverse_link = link_service.session.get(TicketLink, reverse_link.id)
        assert reverse_link is None

    def test_delete_nonexistent_link_returns_false(self, link_service):
        """Deleting non-existent link returns False."""
        result = link_service.delete_link(999)
        assert result is False


class TestGetLinksForTicket:
    """Tests for getting all links for a ticket."""

    def test_get_links_returns_both_directions(
        self, link_service, epic_ticket, story_ticket, bug_ticket
    ):
        """get_links_for_ticket returns both incoming and outgoing links."""
        link_service.create_link(epic_ticket.id, story_ticket.id, LinkType.PARENT)
        link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.BLOCKS)

        # Get links for story_ticket (middle ticket)
        links = link_service.get_links_for_ticket(story_ticket.id)

        assert (
            len(links) == 4
        )  # parent (incoming), child (outgoing), blocks (outgoing), blocked_by (incoming)

        link_types = {link.link_type for link in links}
        assert LinkType.PARENT in link_types
        assert LinkType.CHILD in link_types
        assert LinkType.BLOCKS in link_types
        assert LinkType.BLOCKED_BY in link_types

    def test_get_links_empty_for_no_links(self, link_service, story_ticket):
        """get_links_for_ticket returns empty list for ticket with no links."""
        links = link_service.get_links_for_ticket(story_ticket.id)
        assert links == []


class TestBlockerQueries:
    """Tests for get_blockers and get_blocked methods."""

    def test_get_blockers(self, link_service, story_ticket, bug_ticket, spike_ticket):
        """get_blockers returns tickets that block the given ticket."""
        link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.BLOCKS)
        link_service.create_link(spike_ticket.id, bug_ticket.id, LinkType.BLOCKS)

        blockers = link_service.get_blockers(bug_ticket.id)

        assert len(blockers) == 2
        blocker_sources = {b.source_id for b in blockers}
        assert story_ticket.id in blocker_sources
        assert spike_ticket.id in blocker_sources
        assert all(b.link_type == LinkType.BLOCKS for b in blockers)

    def test_get_blocked(self, link_service, story_ticket, bug_ticket, spike_ticket):
        """get_blocked returns tickets blocked by the given ticket."""
        link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.BLOCKS)
        link_service.create_link(story_ticket.id, spike_ticket.id, LinkType.BLOCKS)

        blocked = link_service.get_blocked(story_ticket.id)

        assert len(blocked) == 2
        blocked_targets = {b.target_id for b in blocked}
        assert bug_ticket.id in blocked_targets
        assert spike_ticket.id in blocked_targets
        assert all(b.link_type == LinkType.BLOCKS for b in blocked)

    def test_get_blockers_empty(self, link_service, bug_ticket):
        """get_blockers returns empty for ticket with no blockers."""
        blockers = link_service.get_blockers(bug_ticket.id)
        assert blockers == []

    def test_get_blocked_empty(self, link_service, story_ticket):
        """get_blocked returns empty for ticket that blocks nothing."""
        blocked = link_service.get_blocked(story_ticket.id)
        assert blocked == []

    def test_blocker_queries_only_return_blocks_type(
        self, link_service, story_ticket, bug_ticket, epic_ticket
    ):
        """Blocker queries only return BLOCKS type links, not other types."""
        link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.BLOCKS)
        link_service.create_link(epic_ticket.id, story_ticket.id, LinkType.PARENT)  # Not a blocker
        link_service.create_link(
            story_ticket.id, epic_ticket.id, LinkType.RELATES_TO
        )  # Not a blocker

        blockers = link_service.get_blockers(bug_ticket.id)
        blocked = link_service.get_blocked(story_ticket.id)

        assert len(blockers) == 1
        assert blockers[0].source_id == story_ticket.id
        assert blockers[0].link_type == LinkType.BLOCKS

        assert len(blocked) == 1
        assert blocked[0].target_id == bug_ticket.id
        assert blocked[0].link_type == LinkType.BLOCKS


class TestLinkTypeConstraints:
    """Tests for all link type constraints systematically."""

    @pytest.mark.parametrize(
        "link_type,valid_source_types,valid_target_types",
        [
            (
                LinkType.PARENT,
                [TicketType.EPIC],
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
            ),
            (
                LinkType.CHILD,
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
                [TicketType.EPIC],
            ),
            (
                LinkType.BLOCKS,
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
            ),
            (
                LinkType.BLOCKED_BY,
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
            ),
            (
                LinkType.RELATES_TO,
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
                [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
            ),
        ],
    )
    def test_link_type_source_target_constraints(
        self,
        link_service,
        ticket_service,
        test_project,
        link_type,
        valid_source_types,
        valid_target_types,
    ):
        """Test all valid source/target type combinations for each link type."""
        for source_type in valid_source_types:
            for target_type in valid_target_types:
                if source_type == target_type == TicketType.EPIC and link_type in (
                    LinkType.PARENT,
                    LinkType.CHILD,
                ):
                    # Epic to Epic is allowed for parent/child
                    pass

                source = ticket_service.create_ticket(
                    project_id=test_project.id,
                    title=f"Source {source_type.value}",
                    type=source_type,
                )
                target = ticket_service.create_ticket(
                    project_id=test_project.id,
                    title=f"Target {target_type.value}",
                    type=target_type,
                )

                link = link_service.create_link(source.id, target.id, link_type)
                assert (
                    link is not None
                ), f"Failed for {source_type} -> {target_type} with {link_type}"

                # Clean up for next iteration
                link_service.delete_link(link.id)

    @pytest.mark.parametrize(
        "link_type,invalid_source_types",
        [
            (LinkType.PARENT, [TicketType.STORY, TicketType.BUG, TicketType.SPIKE]),
            (LinkType.CHILD, []),  # No invalid source types for CHILD
        ],
    )
    def test_link_type_invalid_sources(
        self, link_service, ticket_service, test_project, link_type, invalid_source_types
    ):
        """Test invalid source types for constrained link types."""
        # For CHILD, test invalid target instead
        if link_type == LinkType.CHILD:
            ticket_service.create_ticket(
                project_id=test_project.id, title="Epic", type=TicketType.EPIC
            )
            story = ticket_service.create_ticket(
                project_id=test_project.id, title="Story", type=TicketType.STORY
            )
            for invalid_target_type in [TicketType.STORY, TicketType.BUG, TicketType.SPIKE]:
                invalid_target = ticket_service.create_ticket(
                    project_id=test_project.id,
                    title=f"Invalid {invalid_target_type.value}",
                    type=invalid_target_type,
                )
                with pytest.raises(ValueError):
                    link_service.create_link(story.id, invalid_target.id, LinkType.CHILD)
                link_service.session.expunge(invalid_target)
        else:
            target = ticket_service.create_ticket(
                project_id=test_project.id, title="Target", type=TicketType.STORY
            )
            for invalid_source_type in invalid_source_types:
                invalid_source = ticket_service.create_ticket(
                    project_id=test_project.id,
                    title=f"Invalid {invalid_source_type.value}",
                    type=invalid_source_type,
                )
                with pytest.raises(ValueError):
                    link_service.create_link(invalid_source.id, target.id, link_type)
                link_service.session.expunge(invalid_source)


class TestComplexLinkScenarios:
    """Tests for complex link scenarios."""

    def test_epic_with_multiple_children(
        self, link_service, epic_ticket, test_project, ticket_service
    ):
        """Epic can have multiple children."""
        stories = []
        for i in range(3):
            story = ticket_service.create_ticket(
                project_id=test_project.id,
                title=f"Story {i + 1}",
                type=TicketType.STORY,
            )
            stories.append(story)
            link_service.create_link(epic_ticket.id, story.id, LinkType.PARENT)

        links = link_service.get_links_for_ticket(epic_ticket.id)
        child_links = [link for link in links if link.link_type == LinkType.PARENT]
        assert len(child_links) == 3

    def test_ticket_with_multiple_blockers(
        self, link_service, story_ticket, test_project, ticket_service
    ):
        """Ticket can have multiple blockers."""
        blockers = []
        for i in range(3):
            blocker = ticket_service.create_ticket(
                project_id=test_project.id,
                title=f"Blocker {i + 1}",
                type=TicketType.STORY,
            )
            blockers.append(blocker)
            link_service.create_link(blocker.id, story_ticket.id, LinkType.BLOCKS)

        blockers_result = link_service.get_blockers(story_ticket.id)
        assert len(blockers_result) == 3

    def test_ticket_blocks_multiple(self, link_service, story_ticket, test_project, ticket_service):
        """Ticket can block multiple tickets."""
        blocked = []
        for i in range(3):
            target = ticket_service.create_ticket(
                project_id=test_project.id,
                title=f"Blocked {i + 1}",
                type=TicketType.BUG,
            )
            blocked.append(target)
            link_service.create_link(story_ticket.id, target.id, LinkType.BLOCKS)

        blocked_result = link_service.get_blocked(story_ticket.id)
        assert len(blocked_result) == 3

    def test_chain_of_blocks(self, link_service, test_project, ticket_service):
        """A -> B -> C chain of blocks."""
        a = ticket_service.create_ticket(
            project_id=test_project.id, title="A", type=TicketType.STORY
        )
        b = ticket_service.create_ticket(
            project_id=test_project.id, title="B", type=TicketType.STORY
        )
        c = ticket_service.create_ticket(
            project_id=test_project.id, title="C", type=TicketType.STORY
        )

        link_service.create_link(a.id, b.id, LinkType.BLOCKS)
        link_service.create_link(b.id, c.id, LinkType.BLOCKS)

        # A blocks B, B blocks C
        assert len(link_service.get_blocked(a.id)) == 1  # A blocks B
        assert len(link_service.get_blockers(b.id)) == 1  # B blocked by A
        assert len(link_service.get_blocked(b.id)) == 1  # B blocks C
        assert len(link_service.get_blockers(c.id)) == 1  # C blocked by B

    def test_bidirectional_relates_to(self, link_service, story_ticket, bug_ticket, spike_ticket):
        """relates_to creates bidirectional links between multiple tickets."""
        link_service.create_link(story_ticket.id, bug_ticket.id, LinkType.RELATES_TO)
        link_service.create_link(bug_ticket.id, spike_ticket.id, LinkType.RELATES_TO)
        link_service.create_link(spike_ticket.id, story_ticket.id, LinkType.RELATES_TO)

        # Each ticket has 4 relates_to links (2 outgoing + 2 incoming) due to
        # cycle + symmetric creation: story->bug out, bug->story in,
        # spike->story in, and story->spike out (from spike's symmetric link)
        story_links = [
            link
            for link in link_service.get_links_for_ticket(story_ticket.id)
            if link.link_type == LinkType.RELATES_TO
        ]
        bug_links = [
            link
            for link in link_service.get_links_for_ticket(bug_ticket.id)
            if link.link_type == LinkType.RELATES_TO
        ]
        spike_links = [
            link
            for link in link_service.get_links_for_ticket(spike_ticket.id)
            if link.link_type == LinkType.RELATES_TO
        ]

        assert len(story_links) == 4
        assert len(bug_links) == 4
        assert len(spike_links) == 4


class TestGetEpicsWithChildren:
    """Tests for LinkService.get_epics_with_children (Plan view)."""

    def test_returns_epics_with_children(self, link_service, ticket_service, test_project):
        epic = ticket_service.create_ticket(
            project_id=test_project.id, title="Epic A", type=TicketType.EPIC
        )
        story = ticket_service.create_ticket(
            project_id=test_project.id, title="Story A1", type=TicketType.STORY
        )
        bug = ticket_service.create_ticket(
            project_id=test_project.id, title="Bug B1", type=TicketType.BUG
        )
        ticket_service.create_ticket(
            project_id=test_project.id, title="Plain Story", type=TicketType.STORY
        )
        link_service.create_link(epic.id, story.id, LinkType.PARENT)
        link_service.create_link(epic.id, bug.id, LinkType.PARENT)

        result = link_service.get_epics_with_children()

        assert len(result) == 1
        entry = result[0]
        assert entry["epic"].id == epic.id
        child_ids = {c.id for c in entry["children"]}
        assert child_ids == {story.id, bug.id}

    def test_includes_epics_without_children(self, link_service, ticket_service, test_project):
        epic = ticket_service.create_ticket(
            project_id=test_project.id, title="Lonely Epic", type=TicketType.EPIC
        )

        result = link_service.get_epics_with_children()

        assert len(result) == 1
        assert result[0]["epic"].id == epic.id
        assert result[0]["children"] == []

    def test_no_epics_returns_empty(self, link_service):
        assert link_service.get_epics_with_children() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
