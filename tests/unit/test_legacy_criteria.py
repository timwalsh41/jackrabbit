"""Unit tests for the legacy acceptance-criteria checkbox parser (JRB-024).

The migration that backfills ``ticketcriterion`` rows from legacy markdown
checkbox sections delegates all text handling to ``parse_legacy_criteria``,
a pure function: given a ticket description it reports the criteria in
document order and the description with the section removed, or the reasons
the section is malformed (in which case the description must be left
untouched so nothing is silently mis-shaped).
"""

from jackrabbit.legacy_criteria import parse_legacy_criteria

_LEGACY_DESCRIPTION = """\
## Parent

JRB-020 (Structured Acceptance Criteria epic)

## What to build

A one-time migration parses each ticket legacy markdown acceptance-criteria
checkboxes in the description into unchecked criterion rows.

## Acceptance criteria

- [ ] Legacy checkboxes import as unchecked rows, in order
- [x] The legacy section is removed; Agent Execution Evidence is preserved
- [ ] Malformed lists are reported in a dry-run and not silently mis-shaped

## Blocked by

Criteria storage, API CRUD, and Groomed transition gate

## Agent Execution Evidence

Work happened on branch `jrb-24-legacy-migration`.
"""


class TestCleanParse:
    def test_criteria_parsed_in_document_order(self):
        parsed = parse_legacy_criteria(_LEGACY_DESCRIPTION)
        assert parsed.criteria == (
            "Legacy checkboxes import as unchecked rows, in order",
            "The legacy section is removed; Agent Execution Evidence is preserved",
            "Malformed lists are reported in a dry-run and not silently mis-shaped",
        )
        assert parsed.warnings == ()

    def test_section_found(self):
        assert parse_legacy_criteria(_LEGACY_DESCRIPTION).section_found

    def test_section_removed_from_description(self):
        parsed = parse_legacy_criteria(_LEGACY_DESCRIPTION)
        text = parsed.description_without_section
        assert "## Acceptance criteria" not in text
        assert "- [ ]" not in text
        # Surrounding sections survive, in their original order.
        assert "## Parent" in text
        assert "## What to build" in text
        assert "## Blocked by" in text
        parent_index = text.index("## Parent")
        what_index = text.index("## What to build")
        blocked_index = text.index("## Blocked by")
        assert parent_index < what_index < blocked_index

    def test_agent_execution_evidence_preserved(self):
        text = parse_legacy_criteria(_LEGACY_DESCRIPTION).description_without_section
        assert "## Agent Execution Evidence" in text
        assert "Work happened on branch `jrb-24-legacy-migration`." in text
        assert text.index("## Blocked by") < text.index("## Agent Execution Evidence")

    def test_checked_boxes_import_like_unchecked_ones(self):
        """Legacy `- [x]` rows become criteria too; checkedness is not carried
        over (rows are created unchecked — ADR-0025)."""
        description = (
            "Intro\n\n## Acceptance criteria\n\n"
            "- [ ] first\n"
            "- [x] second\n\n## Agent Execution Evidence\n\ndone"
        )
        parsed = parse_legacy_criteria(description)
        assert parsed.criteria == ("first", "second")
        # The checkbox lines themselves are gone; the texts live on as rows.
        assert "- [x] second" not in parsed.description_without_section
        assert "Intro" in parsed.description_without_section
        assert "## Agent Execution Evidence" in parsed.description_without_section


class TestHeadingVariants:
    def test_any_heading_level_and_case(self):
        headings = (
            "### Acceptance criteria",
            "## ACCEPTANCE CRITERIA",
            "## Acceptance criteria:",
        )
        for heading in headings:
            description = f"Intro\n\n{heading}\n\n- [ ] only one\n\n## Outro"
            parsed = parse_legacy_criteria(description)
            assert parsed.criteria == ("only one",), heading
            assert "- [ ] only one" not in parsed.description_without_section
            assert heading not in parsed.description_without_section
            assert "Intro" in parsed.description_without_section
            assert "Outro" in parsed.description_without_section

    def test_other_headings_are_not_matched(self):
        description = "Intro\n\n## Acceptance Criteria Review Notes\n\n- [ ] keep me\n"
        parsed = parse_legacy_criteria(description)
        assert not parsed.section_found
        assert parsed.criteria == ()
        assert parsed.description_without_section == description


class TestMalformedInput:
    def test_non_checkbox_content_in_section_is_malformed_and_left_untouched(self):
        description = (
            "Intro\n\n## Acceptance criteria\n\n"
            "- [ ] clean one\n"
            "This prose line is not a checkbox.\n"
            "- [ ] another\n\n## Agent Execution Evidence\n\nevidence"
        )
        parsed = parse_legacy_criteria(description)
        assert parsed.warnings
        assert "This prose line is not a checkbox." in parsed.warnings[0]
        # Nothing is silently dropped: the description is returned unchanged.
        assert parsed.description_without_section == description

    def test_multiple_sections_are_malformed_and_left_untouched(self):
        description = (
            "## Acceptance criteria\n\n- [ ] first section\n\n"
            "## Middle\n\n## Acceptance criteria\n\n- [ ] second section\n"
        )
        parsed = parse_legacy_criteria(description)
        assert parsed.warnings
        assert parsed.description_without_section == description

    def test_empty_checkbox_item_is_malformed(self):
        description = "## Acceptance criteria\n\n- [ ] \n- [ ] real one\n"
        parsed = parse_legacy_criteria(description)
        assert parsed.warnings
        assert parsed.description_without_section == description

    def test_prose_only_section_is_left_untouched(self):
        """A criteria section without checkboxes carries prose acceptance
        criteria; converting it to rows would mis-shape it, so it is reported
        instead of touched."""
        description = "## Acceptance criteria\n\nThe ticket works.\n"
        parsed = parse_legacy_criteria(description)
        assert parsed.warnings
        assert parsed.description_without_section == description

    def test_checkboxes_outside_the_section_are_untouched(self):
        """Only the acceptance-criteria section is migrated; checkbox lists
        elsewhere in the description stay exactly as written."""
        description = (
            "## Notes\n\n- [ ] not acceptance criteria\n\n"
            "## Agent Execution Evidence\n\n- [x] also not\n"
        )
        parsed = parse_legacy_criteria(description)
        assert not parsed.section_found
        assert parsed.description_without_section == description


class TestNoSection:
    def test_description_without_section_is_returned_unchanged(self):
        description = "Just some prose.\n\n- [ ] loose checkbox stays\n"
        parsed = parse_legacy_criteria(description)
        assert not parsed.section_found
        assert parsed.criteria == ()
        assert parsed.warnings == ()
        assert parsed.description_without_section == description

    def test_empty_description(self):
        parsed = parse_legacy_criteria("")
        assert not parsed.section_found
        assert parsed.criteria == ()
        assert parsed.description_without_section == ""


class TestIdempotenceAndFormatting:
    def test_second_parse_of_migrated_description_is_a_noop(self):
        """After the migration, the section is gone; re-parsing (e.g. an
        upgrade rerun on an already-migrated database) changes nothing."""
        once = parse_legacy_criteria(_LEGACY_DESCRIPTION)
        twice = parse_legacy_criteria(once.description_without_section)
        assert not twice.section_found
        assert twice.criteria == ()
        assert twice.warnings == ()
        assert twice.description_without_section == once.description_without_section

    def test_removal_keeps_single_blank_line_between_sections(self):
        text = parse_legacy_criteria(_LEGACY_DESCRIPTION).description_without_section
        assert "## What to build\n\nA one-time migration" in text
        assert (
            "checkboxes in the description into unchecked criterion rows.\n\n## Blocked by" in text
        )

    def test_section_at_end_of_description(self):
        description = "Intro\n\n## Acceptance criteria\n\n- [ ] only section\n"
        parsed = parse_legacy_criteria(description)
        assert parsed.criteria == ("only section",)
        assert parsed.description_without_section == "Intro"

    def test_section_at_start_of_description(self):
        description = "## Acceptance criteria\n\n- [ ] first thing\n\n## Then\n\nbody"
        parsed = parse_legacy_criteria(description)
        assert parsed.criteria == ("first thing",)
        assert parsed.description_without_section == "## Then\n\nbody"
