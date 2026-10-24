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
