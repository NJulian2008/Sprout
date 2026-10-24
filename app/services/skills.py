"""
Skills taxonomy loading, normalization, experience scoring, and fallback extraction.

All functions are pure (no database dependency) and unit-testable.
"""
from __future__ import annotations

import json
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


def fallback_extract(text: str) -> dict[str, float]:
    """Keyword-scan fallback when the LLM is unavailable.

    Counts all mentions of each skill's id, label, and aliases in *text*
    (case-insensitive) and maps to a confidence:
    ``confidence = min(0.7, 0.3 + 0.1 * total_mentions)``

    Only canonical taxonomy ids are returned; no unknown keys.
    """
    text_lower = text.lower()
    taxonomy = load_taxonomy()
    result: dict[str, float] = {}

    for skill_id, entry in taxonomy.items():
        terms = (
            [skill_id]
            + [entry["label"].lower()]
            + [a.lower() for a in entry["aliases"]]
        )
        total = sum(text_lower.count(term) for term in terms)
        if total > 0:
            result[skill_id] = round(min(0.7, 0.3 + 0.1 * total), 2)

    return result
