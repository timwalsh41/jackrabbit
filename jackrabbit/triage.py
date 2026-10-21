"""Triage roles recorded as labels (ADR-0024).

The five canonical triage roles are recorded as labels in a ``triage:``
namespace rather than as a keyword line in the ticket description. A ticket's
triage role is therefore visible in the interface, filterable and searchable,
and automation no longer has to parse a description to read it.

The vocabulary lives here, apart from the label machinery: the label rules
(``jackrabbit.labels``) decide what a legal label name is, this module decides
which names mean "this ticket is in this triage state".
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

# The namespace every triage label lives in.
TRIAGE_LABEL_PREFIX = "triage:"


class TriageRole(StrEnum):
    """The five canonical triage roles."""

    NEEDS_TRIAGE = "needs-triage"
    NEEDS_INFO = "needs-info"
    READY_FOR_AGENT = "ready-for-agent"
    READY_FOR_HUMAN = "ready-for-human"
    WONTFIX = "wontfix"

    @property
    def label_name(self) -> str:
        """The label that records this role (``triage:<role>``)."""
        return f"{TRIAGE_LABEL_PREFIX}{self.value}"


#: The canonical roles, in the order they are presented.
TRIAGE_ROLES: tuple[TriageRole, ...] = tuple(TriageRole)

#: The canonical label names, e.g. ``triage:ready-for-agent``.
TRIAGE_LABEL_NAMES: tuple[str, ...] = tuple(role.label_name for role in TRIAGE_ROLES)


def triage_label_name(role: str | TriageRole) -> str:
    """The label name that records the given triage role.

    Args:
        role: One of the five canonical roles.

    Returns:
        The namespaced label name, e.g. ``triage:ready-for-agent``.

    Raises:
        ValueError: If the role is not one of the five canonical roles.
    """
    return TriageRole(role).label_name


def is_triage_label_name(name: str) -> bool:
    """Whether a label name lives in the triage namespace."""
    return (name or "").strip().lower().startswith(TRIAGE_LABEL_PREFIX)


def triage_role_from_label_name(name: str) -> TriageRole | None:
    """The triage role a label name records, or None if it records none.

    Label identity is case-insensitive, so the lookup is too.
    """
    key = (name or "").strip().lower()
    if not key.startswith(TRIAGE_LABEL_PREFIX):
        return None
    try:
        return TriageRole(key[len(TRIAGE_LABEL_PREFIX) :])
    except ValueError:
        return None


def triage_role_from_labels(labels: Iterable[Any]) -> TriageRole | None:
    """The triage role recorded by a ticket's labels, or None.

    Args:
        labels: Label-like objects carrying a ``name`` (Label rows, or any
            object with a ``name`` attribute).
    """
    for label in labels or []:
        role = triage_role_from_label_name(getattr(label, "name", str(label)))
        if role is not None:
            return role
    return None
