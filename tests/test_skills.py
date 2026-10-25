"""Unit tests for the skills taxonomy and scoring service."""
import pytest

from app.services.skills import (
    experience_level,
    experience_score,
    fallback_extract,
    load_taxonomy,
    normalize_skill_id,
)

# ── experience_score() ────────────────────────────────────────────────────────

def test_experience_score_empty():
    assert experience_score({}) == 0.0


def test_experience_score_single():
    assert experience_score({"python": 0.8}) == pytest.approx(0.8)


def test_experience_score_uses_top_five():
    skills = {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6, "e": 0.5, "f": 0.1, "g": 0.1}
    # top 5 = 0.9+0.8+0.7+0.6+0.5 = 3.5 / 5 = 0.7
    assert experience_score(skills) == pytest.approx(0.7)


def test_experience_score_fewer_than_k():
    assert experience_score({"a": 0.6, "b": 0.4}) == pytest.approx(0.5)


# ── experience_level() ────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,level", [
    (0.0, "beginner"),
    (0.34, "beginner"),
    (0.35, "intermediate"),
    (0.64, "intermediate"),
    (0.65, "advanced"),
    (1.0, "advanced"),
])
def test_experience_level_thresholds(score, level):
    assert experience_level(score) == level


# ── normalize_skill_id() ──────────────────────────────────────────────────────

def test_normalize_canonical_id():
    assert normalize_skill_id("python") == "python"


def test_normalize_alias():
    assert normalize_skill_id("py") == "python"


def test_normalize_label_case_insensitive():
    assert normalize_skill_id("JavaScript") == "javascript"


def test_normalize_unknown_returns_none():
    assert normalize_skill_id("zzzznotaskill") is None


# ── fallback_extract() ────────────────────────────────────────────────────────

def test_fallback_extract_only_taxonomy_ids():
    taxonomy = load_taxonomy()
    result = fallback_extract("I use python, docker, and some react for projects")
    assert all(k in taxonomy for k in result)
    assert "python" in result
    assert "docker" in result


def test_fallback_extract_confidence_capped():
    # Many mentions of python should still cap at 0.7
    text = "python " * 20
    result = fallback_extract(text)
    assert result["python"] <= 0.7


def test_fallback_extract_empty_text():
    assert fallback_extract("") == {}


def test_fallback_extract_ignores_incidental_substrings():
    text = "I collaborated with colleagues and wrote a report during my internship."
    assert fallback_extract(text) == {}


def test_fallback_extract_ignores_short_ambiguous_aliases():
    assert fallback_extract("We are going to build a goal tracker.") == {}


def test_fallback_extract_keeps_explicit_long_skill_phrases():
    result = fallback_extract("I completed coursework in the C language and built with Python.")
    assert result == {"python": 0.3, "c": 0.3}


def test_fallback_extract_suppresses_negated_skills():
    assert fallback_extract("No experience with Python, Docker, or Git.") == {}


def test_fallback_extract_keeps_positive_skills_after_contrast():
    result = fallback_extract("No experience with Python, but I use Docker.")
    assert result == {"docker": 0.3}


def test_goal_fallback_keeps_explicit_learning_targets():
    result = fallback_extract("Build an ML project with Python.", goal_context=True)
    assert result == {"machine_learning": 0.5, "python": 0.5}


def test_goal_fallback_ignores_rejected_skills():
    assert fallback_extract("I don't want to learn Python.", goal_context=True) == {}


# ───────────────────────────────────────────────────────────────────────────
# _validated_scores() — posted mentor/student score validation
# (spec: skill-extraction-data-corruption-fix, Task 3.2)
#
# _validated_scores lives in app.routers.pages. It coerces each posted value
# with float() inside a try/except (skipping malformed entries) and routes the
# numeric map through SkillScores, so unknown ids drop, values clamp to
# [0.0, 1.0] and round to 2 decimals, and non-numeric entries are skipped
# without raising.
#
# Validates: Requirements 2.1, 2.2, 2.3; design Correctness Property 1.
# ───────────────────────────────────────────────────────────────────────────

from app.routers.pages import _validated_scores


def test_validated_scores_drops_unknown_ids():
    """2.1 — ids not in the taxonomy are dropped."""
    result = _validated_scores({"python": 0.8, "quantum_telepathy": 0.9})
    assert "quantum_telepathy" not in result
    assert result == {"python": 0.8}


def test_validated_scores_clamps_above_range():
    """2.2 — a confidence above 1.0 is clamped to 1.0."""
    result = _validated_scores({"python": 1.7})
    assert result["python"] == 1.0


def test_validated_scores_clamps_below_range():
    """2.2 — a negative confidence is clamped to 0.0."""
    result = _validated_scores({"python": -0.2})
    assert result["python"] == 0.0


def test_validated_scores_rounds_to_two_decimals():
    """2.2 — in-range values are rounded to 2 decimal places."""
    result = _validated_scores({"python": 0.123456})
    assert result["python"] == 0.12


def test_validated_scores_skips_non_numeric_without_raising():
    """2.3 — a non-numeric value is skipped, not raised."""
    # "expert" cannot be coerced by float(); it must be ignored while the
    # valid entry survives.
    result = _validated_scores({"python": 0.5, "docker": "expert"})
    assert result == {"python": 0.5}
    assert "docker" not in result


def test_validated_scores_non_numeric_only_returns_empty():
    """2.3 — an all-malformed map returns an empty dict without raising."""
    assert _validated_scores({"python": "expert"}) == {}


def test_validated_scores_coerces_numeric_strings():
    """float() accepts numeric strings, so "0.8" coerces like 0.8."""
    result = _validated_scores({"python": "0.8"})
    assert result == {"python": 0.8}


def test_validated_scores_empty_input():
    assert _validated_scores({}) == {}


def test_validated_scores_property_random_mixed_maps():
    """Property-based (Correctness Property 1): random {id: value} maps mixing
    known/unknown ids, in/out-of-range, and non-numeric values always yield an
    output whose keys are all taxonomy ids, whose values are all within
    [0.0, 1.0], and that raises no exception.

    Hypothesis is not a project dependency, so we drive a seeded stdlib random
    loop over many generated inputs (matching the preservation property test
    `test_preserve_random_valid_mentor_scores_persist_cleaned`).

    Validates: Requirements 2.1, 2.2, 2.3
    """
    import random

    taxonomy = load_taxonomy()
    known_ids = sorted(taxonomy.keys())
    unknown_ids = [f"not_a_skill_{i}" for i in range(10)]

    def random_value(rng):
        kind = rng.choice(["in_range", "above", "below", "non_numeric", "numeric_str"])
        if kind == "in_range":
            return round(rng.uniform(0.0, 1.0), 4)
        if kind == "above":
            return rng.uniform(1.0001, 5.0)
        if kind == "below":
            return rng.uniform(-5.0, -0.0001)
        if kind == "numeric_str":
            return str(round(rng.uniform(0.0, 1.0), 2))
        # non_numeric
        return rng.choice(["expert", "n/a", "", None, "high"])

    rng = random.Random(20240607)  # seeded for reproducibility
    for _ in range(300):
        n = rng.randint(0, 8)
        posted = {}
        for _ in range(n):
            key = rng.choice(known_ids + unknown_ids)
            posted[key] = random_value(rng)

        # Must never raise, regardless of malformed/unknown/out-of-range input.
        result = _validated_scores(posted)

        # Output keys are all valid taxonomy ids.
        assert all(k in taxonomy for k in result), (
            f"output keys must all be taxonomy ids; posted={posted} result={result}"
        )
        # Output values are all within [0.0, 1.0].
        assert all(0.0 <= v <= 1.0 for v in result.values()), (
            f"output values must be within [0.0, 1.0]; posted={posted} result={result}"
        )
