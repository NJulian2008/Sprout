"""Unit tests for the mentorship state machine."""
import pytest

from app.services.mentorship import InvalidTransition, complete, decide, hold, schedule


class FakeMentorship:
    """Lightweight stand-in for the ORM Mentorship object."""
    def __init__(self, status="requested"):
        self.status = status
        self.mentor_decision = "pending"
        self.student_decision = "pending"
        self.started_at = None
        self.completed_at = None
        self.agreed_slot = ""


# ── happy path ────────────────────────────────────────────────────────────────

def test_schedule_transition():
    m = FakeMentorship("requested")
    schedule(m, "Tue-Evening")
    assert m.status == "intro_scheduled"


def test_hold_transition():
    m = FakeMentorship("intro_scheduled")
    hold(m)
    assert m.status == "intro_held"


def test_both_confirm_activates():
    m = FakeMentorship("intro_held")
    decide(m, "mentor", "confirm")
    assert m.status == "intro_held"  # still waiting on student
    decide(m, "student", "confirm")
    assert m.status == "active"
    assert m.started_at is not None


def test_complete_transition():
    m = FakeMentorship("active")
    complete(m)
    assert m.status == "completed"
    assert m.completed_at is not None


# ── decline paths ─────────────────────────────────────────────────────────────

def test_mentor_decline_ends():
    m = FakeMentorship("intro_held")
    decide(m, "mentor", "decline")
    assert m.status == "ended"


def test_student_decline_ends():
    m = FakeMentorship("intro_held")
    decide(m, "student", "decline")
    assert m.status == "ended"


def test_decline_after_one_confirm_still_ends():
    m = FakeMentorship("intro_held")
    decide(m, "mentor", "confirm")
    decide(m, "student", "decline")
    assert m.status == "ended"


# ── invalid transitions ───────────────────────────────────────────────────────

def test_schedule_from_wrong_state_raises():
    m = FakeMentorship("intro_held")
    with pytest.raises(InvalidTransition):
        schedule(m, "Mon-Morning")


def test_decide_from_requested_raises():
    m = FakeMentorship("requested")
    with pytest.raises(InvalidTransition):
        decide(m, "mentor", "confirm")


def test_hold_from_wrong_state_raises():
    m = FakeMentorship("requested")
    with pytest.raises(InvalidTransition):
        hold(m)


def test_complete_from_wrong_state_raises():
    m = FakeMentorship("intro_held")
    with pytest.raises(InvalidTransition):
        complete(m)


def test_invalid_side_raises():
    m = FakeMentorship("intro_held")
    with pytest.raises(InvalidTransition):
        decide(m, "teacher", "confirm")


def test_invalid_choice_raises():
    m = FakeMentorship("intro_held")
    with pytest.raises(InvalidTransition):
        decide(m, "mentor", "maybe")
