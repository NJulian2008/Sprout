"""
Mentorship state machine.

Allowed transitions:
    requested → intro_scheduled → intro_held → active     → completed
                                       └──────→ ended  (either side declines)

All functions take the ORM ``Mentorship`` object, mutate it in-place,
and rely on the caller to commit the session.  This keeps the service
pure and independently testable.
"""
from __future__ import annotations

from datetime import UTC, datetime


class InvalidTransition(Exception):
    """Raised when a state transition is not permitted."""


def _assert_status(mentorship, expected: str) -> None:
    if mentorship.status != expected:
        raise InvalidTransition(
            f"Cannot perform this action when mentorship status is "
            f"'{mentorship.status}' (expected '{expected}')."
        )


def schedule(mentorship, slot: str) -> None:
    """Set the intro-meeting slot and advance to ``intro_scheduled``.

    Allowed from: ``requested``
    """
    _assert_status(mentorship, "requested")
    mentorship.agreed_slot = slot          # callers store this on the Meeting row
    mentorship.status = "intro_scheduled"


def hold(mentorship) -> None:
    """Mark the intro meeting as held and advance to ``intro_held``.

    Allowed from: ``intro_scheduled``
    """
    _assert_status(mentorship, "intro_scheduled")
    mentorship.status = "intro_held"


def decide(mentorship, side: str, choice: str) -> None:
    """Record one side's Confirm / Decline decision.

    Parameters
    ----------
    mentorship:
        The ``Mentorship`` ORM object.
    side:
        ``"mentor"`` or ``"student"``.
    choice:
        ``"confirm"`` or ``"decline"``.

    Side effects
    ------------
    * Sets ``mentor_decision`` or ``student_decision`` to
      ``"confirmed"`` or ``"declined"``.
    * If either side declines → ``status = "ended"``.
    * If both confirm → ``status = "active"``, ``started_at = utcnow()``.

    Allowed from: ``intro_held``
    """
    _assert_status(mentorship, "intro_held")

    if side not in ("mentor", "student"):
        raise InvalidTransition(f"Invalid side: '{side}'. Must be 'mentor' or 'student'.")
    if choice not in ("confirm", "decline"):
        raise InvalidTransition(f"Invalid choice: '{choice}'. Must be 'confirm' or 'decline'.")

    decision_value = "confirmed" if choice == "confirm" else "declined"
    setattr(mentorship, f"{side}_decision", decision_value)

    if "declined" in (mentorship.mentor_decision, mentorship.student_decision):
        mentorship.status = "ended"
    elif (
        mentorship.mentor_decision == "confirmed"
        and mentorship.student_decision == "confirmed"
    ):
        mentorship.status = "active"
        mentorship.started_at = datetime.now(UTC)


def complete(mentorship) -> None:
    """Mark a mentorship as completed after the student leaves a testimonial.

    Allowed from: ``active``
    """
    _assert_status(mentorship, "active")
    mentorship.status = "completed"
    mentorship.completed_at = datetime.now(UTC)
