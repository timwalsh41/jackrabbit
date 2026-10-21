"""Label vocabulary rules: name normalisation and derived colour (ADR-0024).

Labels are a single, globally scoped vocabulary. A label's identity is the
lower-cased name (``name_key``); its display name is the spelling first typed.
Names are trimmed, at most 50 characters, and restricted to letters, digits,
spaces, hyphens, underscores and colons (colons allow namespaced families such
as ``triage:ready-for-agent``).

The colour of a label is derived deterministically from its identity key onto a
fixed palette: the same label always looks the same, and there is no stored or
user-editable colour.
"""

import re
from collections.abc import Sequence

# Maximum length of a label name.
LABEL_NAME_MAX_LENGTH = 50

# The match modes of the label filter: a ticket must carry *all* the selected
# labels, or *any* of them.
LABEL_MATCH_MODES: tuple[str, ...] = ("all", "any")

# The default match mode.
LABEL_MATCH_DEFAULT = "all"

# Human-readable description of the allowed character set, used in error messages.
LABEL_NAME_ALLOWED_CHARS = "letters, digits, spaces, hyphens, underscores and colons"

# The allowed character set for a label name.
LABEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _:-]+$")

# Fixed palette for derived label colours.
LABEL_PALETTE: tuple[str, ...] = (
    "#6366f1",  # indigo
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#0ea5e9",  # sky
    "#ec4899",  # pink
    "#14b8a6",  # teal
    "#f97316",  # orange
    "#64748b",  # slate
)


def normalize_label_name(name: str) -> str:
    """Trim and validate a label name, returning the display spelling.

    Args:
        name: The name as typed by the user.

    Returns:
        The trimmed, validated display name.

    Raises:
        ValueError: If the name is empty, longer than
            ``LABEL_NAME_MAX_LENGTH`` characters, or uses characters outside
            the allowed set. The message explains the rule that was broken.
    """
    trimmed = (name or "").strip()
    if not trimmed:
        raise ValueError("Label name cannot be empty")
    if len(trimmed) > LABEL_NAME_MAX_LENGTH:
        raise ValueError(f"Label name must be at most {LABEL_NAME_MAX_LENGTH} characters")
    if not LABEL_NAME_PATTERN.match(trimmed):
        raise ValueError(f"Label name may only contain {LABEL_NAME_ALLOWED_CHARS}")
    return trimmed


def label_identity_key(name: str) -> str:
    """The case-insensitive identity key of a label name."""
    return normalize_label_name(name).lower()


def _fnv1a(text: str) -> int:
    """FNV-1a 32-bit hash — a stable, portable hash (the browser mirrors it)."""
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def label_color(name_key: str) -> str:
    """Derive a label's colour from its identity key.

    The derivation is deterministic (a stable hash, not Python's randomised
    ``hash``), so the same label always gets the same colour. The browser
    mirrors this derivation, so a label looks the same in the form as on the
    ticket page.
    """
    return LABEL_PALETTE[_fnv1a(name_key) % len(LABEL_PALETTE)]


def parse_label_ids(values: Sequence[str] | None) -> list[int]:
    """Parse the label ids of a filter request.

    A label filter travels as a repeated query parameter
    (``label_ids=1&label_ids=2``) and may also be written as a comma-separated
    list (``label_ids=1,2``); both are accepted. Duplicates are dropped, and
    the order of the ids is kept.

    Args:
        values: The raw query values.

    Returns:
        The label ids, in order, without duplicates.

    Raises:
        ValueError: If a value is not an integer.
    """
    ids: list[int] = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError as e:
                raise ValueError(f"label id must be an integer: {part!r}") from e
    return list(dict.fromkeys(ids))


def parse_label_match(value: str | None) -> str:
    """Parse the match mode of the label filter.

    Args:
        value: The raw query value.

    Returns:
        ``"all"`` (the default) or ``"any"``.

    Raises:
        ValueError: If the value is not a known match mode.
    """
    mode = (value or LABEL_MATCH_DEFAULT).strip().lower()
    if mode not in LABEL_MATCH_MODES:
        raise ValueError(f"label match mode must be one of: {', '.join(LABEL_MATCH_MODES)}")
    return mode
