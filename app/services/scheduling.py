"""
Availability slot suggestion service.

Pure function — no database dependency.
"""
from __future__ import annotations


def suggest_slots(
    student_avail: list[str],
    mentor_avail: list[str],
    limit: int = 3,
) -> list[str]:
    """Return up to *limit* overlapping availability strings.

    Availability strings have the form ``"Day-Part"`` e.g. ``"Mon-Evening"``.
    The order is determined by the intersection's natural set ordering,
    which is stable across calls for the same inputs.
    """
    overlap = sorted(set(student_avail) & set(mentor_avail))
    return overlap[:limit]
