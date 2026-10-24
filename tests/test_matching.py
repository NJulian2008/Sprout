"""Unit tests for the deterministic matching service."""
import pytest

from app.services.matching import (
    MentorCandidate,
    StudentProfile,
    apply_hard_filters,
    availability_fit,
    cover,
    level_fit,
    outcome_fit,
    rank,
)


# ── cover() ───────────────────────────────────────────────────────────────────

def test_cover_full_credit_when_mentor_well_ahead():
    assert cover(0.85, 0.30) == pytest.approx(0.85)


def test_cover_partial_when_mentor_slightly_ahead():
    # m=0.45, st=0.30 → 0.45 * min(1, 0.15/0.30) = 0.45 * 0.5 = 0.225
    assert cover(0.45, 0.30) == pytest.approx(0.225)


def test_cover_zero_when_mentor_absent():
    assert cover(0.0, 0.30) == 0.0


def test_cover_zero_when_mentor_not_ahead():
    assert cover(0.30, 0.30) == 0.0


# ── level_fit() ───────────────────────────────────────────────────────────────

def test_level_fit_full_credit_band():
    assert level_fit(0.15) == 1.0
    assert level_fit(0.30) == 1.0
    assert level_fit(0.45) == 1.0


def test_level_fit_partial_below_band():
    # gap=0 → 1 - (0.15-0)/0.30 = 0.5
    assert level_fit(0.0) == pytest.approx(0.5)


def test_level_fit_zero_when_mentor_behind():
    assert level_fit(-0.15) == 0.0
    assert level_fit(-0.20) == 0.0


def test_level_fit_zero_when_mentor_too_far_ahead():
    assert level_fit(0.85) == 0.0


def test_level_fit_partial_above_band():
    # gap=0.50 → 1 - (0.50-0.45)/(0.85-0.45) = 1 - 0.05/0.40 = 0.875
    assert level_fit(0.50) == pytest.approx(0.875)


# ── outcome_fit() ─────────────────────────────────────────────────────────────

def test_outcome_fit_match():
    assert outcome_fit("build_project", ["learn_skill", "build_project"]) == 1.0


def test_outcome_fit_mismatch():
    assert outcome_fit("research", ["learn_skill", "build_project"]) == 0.0


# ── availability_fit() ────────────────────────────────────────────────────────

def test_availability_fit_levels():
    assert availability_fit([], ["Mon-Evening"]) == 0.0
    assert availability_fit(["Mon-Evening"], ["Mon-Evening"]) == pytest.approx(1 / 3)
    assert availability_fit(
        ["Mon-Evening", "Tue-Evening", "Wed-Evening"],
        ["Mon-Evening", "Tue-Evening", "Wed-Evening"],
    ) == 1.0


def test_availability_fit_caps_at_one():
    a = ["Mon-Evening", "Tue-Evening", "Wed-Evening", "Thu-Evening"]
    assert availability_fit(a, a) == 1.0


# ── rank() determinism & shortlist ────────────────────────────────────────────

def _mentor_pool():
    return [
        MentorCandidate(3, {"python": 0.9, "machine_learning": 0.8}, 0.8, ["learn_skill"], ["Mon-Evening"]),
        MentorCandidate(1, {"python": 0.5}, 0.5, ["build_project"], ["Tue-Morning"]),
        MentorCandidate(2, {"python": 0.7, "machine_learning": 0.6}, 0.65, ["learn_skill"], ["Mon-Evening", "Tue-Evening"]),
    ]


def test_rank_is_deterministic():
    student = StudentProfile(1, "learn_skill", ["python", "machine_learning"], {"python": 0.3}, 0.3, ["Mon-Evening"])
    r1 = [m.id for m, _, _ in rank(student, _mentor_pool())]
    r2 = [m.id for m, _, _ in rank(student, _mentor_pool())]
    assert r1 == r2


def test_rank_ties_broken_by_mentor_id():
    # Two identical mentors with different ids — lower id must come first.
    student = StudentProfile(1, "learn_skill", ["python"], {}, 0.3, ["Mon-Evening"])
    mentors = [
        MentorCandidate(5, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"]),
        MentorCandidate(2, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"]),
    ]
    ranked = rank(student, mentors)
    assert ranked[0][0].id == 2


def test_beginner_vs_advanced_get_different_shortlists():
    # level_fit steers a beginner to a mentor who is a teachable step ahead and
    # an advanced student to a technically deep mentor.
    mentors = [
        MentorCandidate(1, {"python": 0.9, "machine_learning": 0.9}, 0.95, ["learn_skill"], ["Mon-Evening"]),   # very deep
        MentorCandidate(2, {"python": 0.65, "machine_learning": 0.6}, 0.55, ["learn_skill"], ["Mon-Evening"]),  # moderate step-up
    ]
    beginner = StudentProfile(10, "learn_skill", ["python", "machine_learning"], {"python": 0.2}, 0.2, ["Mon-Evening"])
    advanced = StudentProfile(11, "learn_skill", ["python", "machine_learning"], {"python": 0.6, "machine_learning": 0.55}, 0.7, ["Mon-Evening"])
    beg_top = rank(beginner, mentors)[0][0].id
    adv_top = rank(advanced, mentors)[0][0].id
    assert beg_top == 2   # beginner prefers the teachable step-up mentor
    assert adv_top == 1   # advanced student prefers the deep mentor
    assert beg_top != adv_top


# ── hard filters ──────────────────────────────────────────────────────────────

def test_capacity_filter_excludes_full_mentors():
    student = StudentProfile(1, "learn_skill", ["python"], {}, 0.3, ["Mon-Evening"])
    mentors = [
        MentorCandidate(1, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"], active_students=2, max_students=2),
        MentorCandidate(2, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"], active_students=0, max_students=2),
        MentorCandidate(3, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"], active_students=1, max_students=2),
        MentorCandidate(4, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"], active_students=0, max_students=2),
    ]
    result = apply_hard_filters(student, mentors)
    assert 1 not in [m.id for m in result]


def test_availability_relaxed_when_few_pass():
    student = StudentProfile(1, "learn_skill", ["python"], {}, 0.3, ["Sun-Night"])
    mentors = [
        MentorCandidate(1, {"python": 0.7}, 0.5, ["learn_skill"], ["Mon-Evening"]),
        MentorCandidate(2, {"python": 0.7}, 0.5, ["learn_skill"], ["Tue-Evening"]),
    ]
    result = apply_hard_filters(student, mentors)
    # No overlap at all, but relaxation returns all capacity-passing mentors
    assert len(result) == 2
    assert all(m.schedule_needs_discussion for m in result)
