"""Unit tests for branch and PR tracking utilities."""

import pytest
from jackrabbit.models import Project, Ticket, TicketType
from jackrabbit.services import (
    detect_git_host,
    generate_branch_name,
    slugify,
    validate_pr_url,
)


class TestSlugify:
    """Tests for slugify function."""

    def test_simple_text(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_characters(self):
        assert slugify("Fix login bug!") == "fix-login-bug"
        assert slugify("Add @user authentication") == "add-user-authentication"
        assert slugify("Test #123: Feature") == "test-123-feature"

    def test_multiple_spaces(self):
        assert slugify("Multiple   spaces") == "multiple-spaces"
        assert slugify("Tabs\tand\nnewlines") == "tabs-and-newlines"

    def test_leading_trailing_spaces(self):
        assert slugify("  trim me  ") == "trim-me"

    def test_max_length(self):
        long_text = "a" * 100
        result = slugify(long_text, max_length=50)
        assert len(result) == 50
        assert result == "a" * 50

    def test_max_length_truncates_at_hyphen(self):
        result = slugify("this-is-a-very-long-title-that-exceeds-limit", max_length=20)
        assert len(result) <= 20
        assert not result.endswith("-")

    def test_empty_string(self):
        assert slugify("") == ""

    def test_only_special_chars(self):
        assert slugify("!!!") == ""

    def test_numbers_preserved(self):
        assert slugify("Ticket 123") == "ticket-123"
        assert slugify("v2.0 Release") == "v2-0-release"

    def test_unicode(self):
        assert slugify("Café résumé") == "caf-r-sum"


class TestGenerateBranchName:
    """Tests for generate_branch_name function."""

    def create_ticket(self, **kwargs):
        """Helper to create a ticket with defaults."""
        defaults = {
            "id": 1,
            "project_id": 1,
            "number": 1,
            "type": TicketType.STORY,
            "title": "Test Ticket",
        }
        defaults.update(kwargs)

        # Create a mock project
        project = Project(prefix="UNS", name="Unsorted")

        ticket = Ticket(**defaults)
        ticket.project = project
        return ticket

    def test_story_type(self):
        ticket = self.create_ticket(type=TicketType.STORY, number=1, title="Fix login bug")
        branch = generate_branch_name(ticket)
        assert branch == "feature/UNS-001-fix-login-bug"

    def test_bug_type(self):
        ticket = self.create_ticket(type=TicketType.BUG, number=5, title="Memory leak in parser")
        branch = generate_branch_name(ticket)
        assert branch == "fix/UNS-005-memory-leak-in-parser"

    def test_epic_type(self):
        ticket = self.create_ticket(type=TicketType.EPIC, number=10, title="User dashboard")
        branch = generate_branch_name(ticket)
        assert branch == "epic/UNS-010-user-dashboard"

    def test_spike_type(self):
        ticket = self.create_ticket(type=TicketType.SPIKE, number=3, title="Research new framework")
        branch = generate_branch_name(ticket)
        assert branch == "spike/UNS-003-research-new-framework"

    def test_custom_project_prefix(self):
        ticket = self.create_ticket(project_id=2, number=1, title="Test")
        ticket.project = Project(prefix="WEB", name="Web Project")
        branch = generate_branch_name(ticket)
        assert branch == "feature/WEB-001-test"

    def test_special_chars_in_title(self):
        ticket = self.create_ticket(title="Fix @user's login & auth!")
        branch = generate_branch_name(ticket)
        # Apostrophe becomes hyphen, so user's -> user-s
        assert branch == "feature/UNS-001-fix-user-s-login-auth"

    def test_long_title_truncated(self):
        ticket = self.create_ticket(
            title=(
                "This is a very long title that should be truncated to fit "
                "within the maximum length"
            )
        )
        branch = generate_branch_name(ticket)
        # branch name should be valid and not too long
        assert len(branch) <= 100  # reasonable limit

    def test_branch_format_matches_validation(self):
        """Generated branch names should match the validation regex."""
        import re

        pattern = r"^[a-zA-Z0-9/_-]+$"

        ticket = self.create_ticket(type=TicketType.STORY, title="Fix login bug!")
        branch = generate_branch_name(ticket)
        assert re.match(pattern, branch), f"Branch name '{branch}' doesn't match pattern"

    def test_unknown_type_defaults_to_feature(self):
        """Unknown ticket types should default to 'feature' prefix."""
        ticket = self.create_ticket(type="Unknown")
        branch = generate_branch_name(ticket)
        assert branch.startswith("feature/")


class TestValidatePRUrl:
    """Tests for validate_pr_url function."""

    def test_valid_github_url(self):
        valid, error = validate_pr_url("https://github.com/org/repo/pull/123")
        assert valid
        assert error is None

    def test_valid_gitlab_url(self):
        valid, error = validate_pr_url("https://gitlab.com/org/repo/-/merge_requests/456")
        assert valid
        assert error is None

    def test_valid_bitbucket_url(self):
        valid, error = validate_pr_url("https://bitbucket.org/org/repo/pull-requests/789")
        assert valid
        assert error is None

    def test_valid_azure_url(self):
        valid, error = validate_pr_url(
            "https://dev.azure.com/org/project/_git/repo/pullrequest/123"
        )
        assert valid
        assert error is None

    def test_valid_generic_https(self):
        valid, error = validate_pr_url("https://custom-git.example.com/pull/123")
        assert valid
        assert error is None

    def test_invalid_no_protocol(self):
        valid, error = validate_pr_url("github.com/org/repo/pull/123")
        assert not valid
        assert "HTTP/HTTPS" in error

    def test_invalid_ftp(self):
        valid, error = validate_pr_url("ftp://github.com/org/repo/pull/123")
        assert not valid
        assert "HTTP/HTTPS" in error

    def test_invalid_empty(self):
        valid, error = validate_pr_url("")
        assert not valid
        assert "required" in error

    def test_invalid_whitespace(self):
        valid, error = validate_pr_url("   ")
        assert not valid
        assert "required" in error

    def test_invalid_no_domain(self):
        valid, error = validate_pr_url("https:///pull/123")
        assert not valid
        assert "domain" in error

    def test_invalid_not_url(self):
        valid, error = validate_pr_url("not a url at all")
        assert not valid
        assert "HTTP/HTTPS" in error


class TestDetectGitHost:
    """Tests for detect_git_host function."""

    def test_github(self):
        assert detect_git_host("https://github.com/org/repo/pull/123") == "github"
        assert detect_git_host("https://GITHUB.COM/org/repo/pull/123") == "github"

    def test_gitlab(self):
        assert detect_git_host("https://gitlab.com/org/repo/-/merge_requests/123") == "gitlab"
        assert (
            detect_git_host("https://gitlab.example.com/org/repo/-/merge_requests/123") == "gitlab"
        )

    def test_bitbucket(self):
        assert detect_git_host("https://bitbucket.org/org/repo/pull-requests/123") == "bitbucket"

    def test_azure(self):
        assert (
            detect_git_host("https://dev.azure.com/org/project/_git/repo/pullrequest/123")
            == "azure"
        )
        assert (
            detect_git_host("https://visualstudio.com/org/project/_git/repo/pullrequest/123")
            == "azure"
        )

    def test_unknown(self):
        assert detect_git_host("https://custom-git.example.com/pull/123") is None
        assert detect_git_host("") is None
        assert detect_git_host(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
