"""Legacy acceptance-criteria checkbox parser (JRB-024, ADR-0025).

Before structured criteria (JRB-021), tickets carried their acceptance
criteria as markdown checkboxes (``- [ ]`` / ``- [x]``) in an
"Acceptance criteria" section of the description. This module is the pure
text layer of the one-time data migration: it extracts those checkbox items
in document order and produces the description with the section removed,
leaving every other section — notably "Agent Execution Evidence" — untouched.

Malformed sections (prose inside the list, empty checkbox items, several
matching headings) are reported as warnings and the description is returned
unchanged, so callers can neither silently mis-shape nor silently drop
content. The dry-run report command (``report-legacy-criteria``) and the
Alembic data migration both go through this parser.
"""

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s*(.*?)\s*$")
_SECTION_TITLE = "acceptance criteria"


@dataclass(frozen=True)
class LegacyCriteriaParse:
    """The result of scanning one ticket description for a legacy section.

    ``criteria`` holds the checkbox texts in document order (checked and
    unchecked boxes alike — rows are always created unchecked per ADR-0025).
    ``warnings`` is empty exactly when the section is clean; when it is not,
    ``description_without_section`` is the *unchanged* input so no content is
    silently dropped. ``section_found`` is False when the description has no
    matching heading at all (nothing to migrate, no warning).
    """

    section_found: bool
    criteria: tuple[str, ...]
    description_without_section: str
    warnings: tuple[str, ...]


def _normalize_heading_title(title: str) -> str:
    """Case- and colon-insensitive heading text: '### Acceptance criteria:'."""
    return title.strip().rstrip(":").strip().casefold()


def _is_heading(line: str) -> bool:
    return _HEADING_RE.match(line) is not None


def _remove_section(lines: list[str], start: int, end: int) -> str:
    """Join the description back together without ``lines[start:end]``.

    Blank lines at the seam are collapsed to a single separator so the
    sections that bracket the removed one stay properly spaced.
    """
    before = lines[:start]
    after = lines[end:]
    while before and not before[-1].strip():
        before.pop()
    while after and not after[0].strip():
        after.pop(0)
    if before and after:
        return "\n".join([*before, "", *after]).rstrip("\n")
    return "\n".join(before + after).rstrip("\n")


def parse_legacy_criteria(description: str) -> LegacyCriteriaParse:
    """Extract legacy markdown criteria checkboxes from a ticket description.

    A single heading titled "Acceptance criteria" (any level, case- and
    colon-insensitive) opens the section, which runs to the next heading of
    any level. Only checkbox lines are converted to criteria; anything else
    non-blank inside the section makes the section malformed, and malformed
    sections are reported in ``warnings`` with the description returned
    unchanged.
    """
    lines = description.split("\n")
    matches = [
        index
        for index, line in enumerate(lines)
        if (heading := _HEADING_RE.match(line)) is not None
        and _normalize_heading_title(heading.group(2)) == _SECTION_TITLE
    ]

    if not matches:
        return LegacyCriteriaParse(
            section_found=False,
            criteria=(),
            description_without_section=description,
            warnings=(),
        )

    if len(matches) > 1:
        line_numbers = ", ".join(str(index + 1) for index in matches)
        return LegacyCriteriaParse(
            section_found=True,
            criteria=(),
            description_without_section=description,
            warnings=(
                f"multiple 'Acceptance criteria' sections (lines {line_numbers}); "
                "the description was left untouched",
            ),
        )

    start = matches[0]
    end = next(
        (index for index in range(start + 1, len(lines)) if _is_heading(lines[index])),
        len(lines),
    )

    criteria: list[str] = []
    warnings: list[str] = []
    for offset, line in enumerate(lines[start + 1 : end], start=start + 2):
        if not line.strip():
            continue
        if checkbox := _CHECKBOX_RE.match(line):
            text = checkbox.group(2).strip()
            if not text:
                warnings.append(f"empty checkbox item on line {offset}")
            else:
                criteria.append(text)
        else:
            warnings.append(
                f"non-checkbox content on line {offset} ({line.strip()!r}) "
                "would not map to a criterion row"
            )

    if warnings:
        return LegacyCriteriaParse(
            section_found=True,
            criteria=(),
            description_without_section=description,
            warnings=tuple(warnings),
        )

    if not criteria:
        # A heading with no list under it: nothing to import, nothing to drop.
        return LegacyCriteriaParse(
            section_found=True,
            criteria=(),
            description_without_section=description,
            warnings=(),
        )

    return LegacyCriteriaParse(
        section_found=True,
        criteria=tuple(criteria),
        description_without_section=_remove_section(lines, start, end),
        warnings=(),
    )
