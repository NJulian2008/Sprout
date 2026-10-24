"""
Deterministic mentor-matching service.

All functions are pure Python with no ORM or database dependency,
making them fast and easy to unit-test.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config_constants import (
    AVAIL_BLOCKS_FOR_FULL_SCORE,
    COVER_HEADROOM,
    LEVEL_FIT_LOWER_BOUND,
    LEVEL_FIT_MAX_GAP,
    LEVEL_FIT_MIN_GAP,
    LEVEL_FIT_UPPER_BOUND,
    SKILLS_FIT_COVERAGE_WEIGHT,
    SKILLS_FIT_LEVEL_WEIGHT,
    WEIGHT_AVAIL_FIT,
    WEIGHT_OUTCOME_FIT,
    WEIGHT_SKILLS_FIT,
)

# ── Data transfer objects (no ORM imports) ───────────────────────────────────

@dataclass
class StudentProfile:
    id: int
    goal_type: str                          # one of OUTCOMES
    skills_to_learn: list[str]             # taxonomy ids the student wants
    skill_scores: dict[str, float]         # current skills {id: confidence}
    experience_score: float
    availability: list[str]                # "Day-Part" strings


@dataclass
class MentorCandidate:
    id: int
    skill_scores: dict[str, float]
    experience_score: float
    outcomes: list[str]
    availability: list[str]
    active_students: int = 0
    max_students: int = 2
    schedule_needs_discussion: bool = False


# ── Core scoring functions ────────────────────────────────────────────────────

def cover(m: float, st: float) -> float:
    """Per-skill coverage score.

    ``m`` = mentor confidence in the skill (0–1).
    ``st`` = student's current confidence in the same skill (0–1).

    A deep mentor (well ahead of the student) scores high; a mentor only
    slightly ahead, or shallow, scores low.
    """
    return m * min(1.0, max(0.0, (m - st) / COVER_HEADROOM))


def level_fit(gap: float) -> float:
    """Overall experience-level fit from the mentor–student gap.

    Full credit for gap in [MIN_GAP, MAX_GAP]; falls linearly to 0
    outside that range.
    """
    if gap < LEVEL_FIT_MIN_GAP:
        # Mentor not sufficiently ahead (or behind) — linearly falls to 0
        return max(0.0, 1.0 - (LEVEL_FIT_MIN_GAP - gap) / (LEVEL_FIT_MIN_GAP - LEVEL_FIT_LOWER_BOUND))
    if gap > LEVEL_FIT_MAX_GAP:
        # Mentor so far ahead the project may be out of reach
        return max(0.0, 1.0 - (gap - LEVEL_FIT_MAX_GAP) / (LEVEL_FIT_UPPER_BOUND - LEVEL_FIT_MAX_GAP))
    return 1.0


def skills_fit(student: StudentProfile, mentor: MentorCandidate) -> tuple[float, dict]:
    """Composite skills fit: 0.7 * coverage + 0.3 * level_fit."""
    targets = student.skills_to_learn
    if not targets:
        cov = 0.0
    else:
        cov = sum(
            cover(
                mentor.skill_scores.get(s, 0.0),
                student.skill_scores.get(s, 0.0),
            )
            for s in targets
        ) / len(targets)

    lvl = level_fit(mentor.experience_score - student.experience_score)
    fit = SKILLS_FIT_COVERAGE_WEIGHT * cov + SKILLS_FIT_LEVEL_WEIGHT * lvl
    return fit, {"coverage": round(cov, 4), "level_fit": round(lvl, 4)}


def outcome_fit(student_goal_type: str, mentor_outcomes: list[str]) -> float:
    """1.0 if the student's goal type is in the mentor's outcome list, else 0.0."""
    return 1.0 if student_goal_type in mentor_outcomes else 0.0


def availability_fit(student_avail: list[str], mentor_avail: list[str]) -> float:
    """Fraction of perfect availability; capped at 1.0."""
    overlaps = len(set(student_avail) & set(mentor_avail))
    return min(1.0, overlaps / AVAIL_BLOCKS_FOR_FULL_SCORE)


def compute_score(
    student: StudentProfile, mentor: MentorCandidate
) -> tuple[float, dict]:
    """Weighted overall score (0–100) with full breakdown."""
    sf, sf_detail = skills_fit(student, mentor)
    of = outcome_fit(student.goal_type, mentor.outcomes)
    af = availability_fit(student.availability, mentor.availability)

    score = 100.0 * (
        WEIGHT_SKILLS_FIT * sf
        + WEIGHT_OUTCOME_FIT * of
        + WEIGHT_AVAIL_FIT * af
    )
    breakdown = {
        "skills_fit": round(sf, 4),
        "skills_fit_detail": sf_detail,
        "outcome_fit": round(of, 4),
        "availability_fit": round(af, 4),
    }
    return round(score, 4), breakdown


# ── Hard filters ─────────────────────────────────────────────────────────────

def apply_hard_filters(
    student: StudentProfile,
    mentors: list[MentorCandidate],
) -> list[MentorCandidate]:
    """Apply capacity and availability hard filters.

    1. Remove mentors who are at capacity (active_students >= max_students).
    2. Require at least one overlapping availability block.
       If fewer than 3 mentors pass, relax the availability filter and mark
       the remaining ones with ``schedule_needs_discussion=True``.
    """
    # Filter by capacity
    has_capacity = [m for m in mentors if m.active_students < m.max_students]

    # Filter by availability overlap
    has_overlap = [
        m for m in has_capacity
        if set(student.availability) & set(m.availability)
    ]

    if len(has_overlap) >= 3:
        return has_overlap

    # Relax availability — return all capacity-passing mentors, mark them
    for m in has_capacity:
        if not (set(student.availability) & set(m.availability)):
            m.schedule_needs_discussion = True
    return has_capacity


# ── Ranking ───────────────────────────────────────────────────────────────────

def rank(
    student: StudentProfile,
    mentors: list[MentorCandidate],
) -> list[tuple[MentorCandidate, float, dict]]:
    """Score all mentors, sort descending; ties broken by mentor id (asc).

    Returns a list of ``(mentor, score, breakdown)`` tuples.
    """
    scored = [
        (mentor, *compute_score(student, mentor))
        for mentor in mentors
    ]
    # Primary sort: score descending; secondary: mentor id ascending (tie-break)
    scored.sort(key=lambda x: (-x[1], x[0].id))
    return [(m, s, b) for m, s, b in scored]
