"""
Skills taxonomy loading, normalization, experience scoring, and fallback extraction.

All functions are pure (no database dependency) and unit-testable.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

try:
    from rapidfuzz import fuzz
    from rapidfuzz import process as rf_process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "skills_taxonomy.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict[str, dict]:
    """Return the skills taxonomy as ``{skill_id: entry}`` dict, cached."""
    with TAXONOMY_PATH.open() as f:
        items = json.load(f)
    return {item["id"]: item for item in items}


def _alias_map() -> dict[str, str]:
    """Build a flat ``{alias_lower: skill_id}`` map (cached via closure)."""
    taxonomy = load_taxonomy()
    mapping: dict[str, str] = {}
    for skill_id, entry in taxonomy.items():
        mapping[skill_id] = skill_id
        mapping[entry["label"].lower()] = skill_id
        for alias in entry["aliases"]:
            mapping[alias.lower()] = skill_id
    return mapping


# Cache the alias map at module level after first use
_ALIAS_MAP: dict[str, str] | None = None


def _get_alias_map() -> dict[str, str]:
    global _ALIAS_MAP
    if _ALIAS_MAP is None:
        _ALIAS_MAP = _alias_map()
    return _ALIAS_MAP


def normalize_skill_id(text: str) -> str | None:
    """Map a raw string to a canonical taxonomy skill id, or ``None``.

    Resolution order:
    1. Exact id match
    2. Exact alias / label match (case-insensitive)
    3. Rapidfuzz fuzzy match against all aliases (if rapidfuzz installed, score ≥ 85)
    """
    key = text.strip().lower()
    amap = _get_alias_map()

    # Steps 1 & 2 — exact lookup
    if key in amap:
        return amap[key]

    # Step 3 — fuzzy (optional)
    if RAPIDFUZZ_AVAILABLE:
        result = rf_process.extractOne(
            key,
            list(amap.keys()),
            scorer=fuzz.WRatio,
            score_cutoff=85,
        )
        if result:
            return amap[result[0]]

    return None


def experience_score(skills: dict[str, float], k: int = 5) -> float:
    """Mean of the top-*k* confidence values; 0.0 for an empty dict."""
    if not skills:
        return 0.0
    top = sorted(skills.values(), reverse=True)[:k]
    return sum(top) / len(top)


def experience_level(score: float) -> str:
    """Map an experience score to a level label.

    * score < 0.35  → ``"beginner"``
    * score < 0.65  → ``"intermediate"``
    * score ≥ 0.65  → ``"advanced"``
    """
    if score < 0.35:
        return "beginner"
    if score < 0.65:
        return "intermediate"
    return "advanced"


_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|lack|lacks|lacked|lacking|"
    r"don't|doesn't|didn't|haven't|hasn't|hadn't)\b",
    re.IGNORECASE,
)
_CONTRAST_SPLIT_RE = re.compile(
    r"[.!?;]+|\b(?:but|however|although|yet)\b",
    re.IGNORECASE,
)
_GOAL_INTENT_RE = re.compile(
    r"\b(?:want(?:s|ed)? to|would like to|hope to|aim to|plan to|"
    r"learn(?:ing)?|study|build|improve|practice|develop|explore|"
    r"focus on|interested in)\b",
    re.IGNORECASE,
)
_GOAL_REJECTION_RE = re.compile(
    r"\b(?:don't want to|do not want to|doesn't want to|does not want to|"
    r"never want to|not interested in|no desire to|avoid|rather not)\b",
    re.IGNORECASE,
)


def _skill_terms(skill_id: str, entry: dict) -> set[str]:
    terms = {skill_id, skill_id.replace("_", " "), entry["label"], *entry["aliases"]}
    return {term.strip().lower() for term in terms if term.strip()}


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    escaped = re.sub(r"(?:\\ |\\_)+", r"\\s+", escaped)
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _has_positive_skill_mention(skill_id: str, text: str, entry: dict) -> bool:
    """Check for an explicit, non-negated taxonomy phrase in the text."""
    segments = _CONTRAST_SPLIT_RE.split(text)
    terms = _skill_terms(skill_id, entry)

    for segment in segments:
        if _NEGATION_RE.search(segment):
            continue
        for term in terms:
            # Short aliases such as "c", "go", and "sh" are too ambiguous
            # for automatic extraction; the canonical full label remains usable.
            if len(re.sub(r"\W", "", term)) < 3:
                continue
            if _term_pattern(term).search(segment):
                return True

    return False


def _has_goal_skill_mention(skill_id: str, text: str, entry: dict) -> bool:
    """Find a named skill paired with positive learning/building intent."""
    terms = _skill_terms(skill_id, entry)
    for segment in _CONTRAST_SPLIT_RE.split(text):
        if not _GOAL_INTENT_RE.search(segment) or _GOAL_REJECTION_RE.search(segment):
            continue
        for term in terms:
            if _term_pattern(term).search(segment):
                return True
    return False


def fallback_extract(text: str, *, goal_context: bool = False) -> dict[str, float]:
    """Conservatively extract explicit positive skill mentions.

    Matching uses whole phrases, ignores ambiguous short aliases, and skips
    negated clauses. In goal context, only explicit positive learning/building
    intent is included. A mention alone cannot establish proficiency, so resume
    fallback scores remain at beginner-level confidence.
    """
    taxonomy = load_taxonomy()
    result: dict[str, float] = {}

    for skill_id, entry in taxonomy.items():
        if goal_context:
            found = _has_goal_skill_mention(skill_id, text, entry)
            confidence = 0.5
        else:
            found = _has_positive_skill_mention(skill_id, text, entry)
            confidence = 0.3
        if found:
            result[skill_id] = confidence

    return result
