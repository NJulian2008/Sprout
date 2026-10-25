"""
LLM service: skill extraction and match reranking.

Architecture:
- LLMClient Protocol — one method: complete_json(system, prompt, timeout_s) -> str
- CopilotAdapter   — calls GitHub Copilot / OpenAI-compatible endpoint
- OffAdapter       — raises LLMUnavailable immediately (LLM_MODE=off)
- CachedAdapter    — reads from LLMCache table; raises on miss

Every call is logged (latency, cache hit, fallback used).
Results are cached in the LLMCache table with a versioned, taxonomy-aware key.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.services.prompts import (
    RERANK_SYSTEM,
    RERANK_USER_TEMPLATE,
    SKILL_EXTRACTION_SYSTEM,
    SKILL_EXTRACTION_USER_TEMPLATE,
    SKILL_GOAL_CONTEXT_INSTRUCTION,
)

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Raised when the LLM is off, timed out, or cache-missed."""


# ── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMClient(Protocol):
    def complete_json(
        self, system: str, prompt: str, timeout_s: float = 6.0
    ) -> str: ...


# ── Adapters ──────────────────────────────────────────────────────────────────

class OffAdapter:
    """Always raises LLMUnavailable — used when LLM_MODE=off."""
    def complete_json(self, system: str, prompt: str, timeout_s: float = 6.0) -> str:
        raise LLMUnavailable("LLM is disabled (LLM_MODE=off).")


class CachedAdapter:
    """Serves responses from LLMCache; raises LLMUnavailable on a miss."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def complete_json(self, system: str, prompt: str, timeout_s: float = 6.0) -> str:
        from app.db.models import LLMCache
        key = _cache_key(system, prompt)
        row = self._db.query(LLMCache).filter(LLMCache.key == key).first()
        if row is None:
            raise LLMUnavailable("LLM cache miss.")
        return row.response


class CopilotAdapter:
    """Calls a GitHub Copilot / OpenAI-compatible chat endpoint."""

    def __init__(self, token: str) -> None:
        self._token = token

    def complete_json(self, system: str, prompt: str, timeout_s: float = 6.0) -> str:
        import httpx
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        # Try GitHub Copilot endpoint; fall back to generic OpenAI-compatible
        url = "https://api.githubcopilot.com/chat/completions"
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMUnavailable(f"Copilot request failed: {exc}") from exc


# ── Factory ───────────────────────────────────────────────────────────────────

def get_llm_client(db: Session) -> LLMClient:
    """Return the appropriate adapter based on LLM_MODE setting."""
    from app.settings import settings
    mode = settings.llm_mode.lower()
    if mode == "off":
        return OffAdapter()
    if mode == "cached":
        return CachedAdapter(db)
    # "live"
    return CopilotAdapter(settings.copilot_token)


# ── Cache helpers ─────────────────────────────────────────────────────────────

CACHE_VERSION = "v3"


def _taxonomy_signature() -> str:
    """Return a short sha256 of the sorted taxonomy ids.

    Folded into the cache key so a taxonomy change invalidates stale entries.
    """
    from app.services.skills import load_taxonomy
    ids = ",".join(sorted(load_taxonomy().keys()))
    return hashlib.sha256(ids.encode()).hexdigest()[:12]


def _cache_key(system: str, prompt: str) -> str:
    material = f"{CACHE_VERSION}\x00{_taxonomy_signature()}\x00{system}\x00{prompt}"
    return hashlib.sha256(material.encode()).hexdigest()


def _read_cache(db: Session, key: str) -> str | None:
    from app.db.models import LLMCache
    row = db.query(LLMCache).filter(LLMCache.key == key).first()
    return row.response if row else None


def _write_cache(db: Session, key: str, response: str) -> None:
    from app.db.models import LLMCache
    existing = db.query(LLMCache).filter(LLMCache.key == key).first()
    if existing is None:
        db.add(LLMCache(key=key, response=response))
        db.commit()


# ── Parsing helpers ───────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _loads_tolerant(raw: str):
    """json.loads after stripping an optional surrounding markdown code fence."""
    match = _FENCE_RE.match(raw)
    candidate = match.group(1) if match else raw
    return json.loads(candidate)


def _grounded_skill_scores(
    payload: dict, text: str, *, goal_context: bool = False
) -> dict[str, float]:
    """Keep model scores only when backed by an exact, explicit text quote."""
    from app.schemas.ai import SkillScores
    from app.services.skills import (
        _has_goal_skill_mention,
        _has_positive_skill_mention,
        load_taxonomy,
    )

    validated = SkillScores.model_validate(payload)
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("skill extraction response must include an evidence object")

    taxonomy = load_taxonomy()
    text_folded = text.casefold()
    mention_check = _has_goal_skill_mention if goal_context else _has_positive_skill_mention
    grounded: dict[str, float] = {}
    discarded_count = 0
    raw_skills = payload.get("skills")
    if isinstance(raw_skills, dict):
        discarded_count += len(set(raw_skills) - set(validated.skills))

    for skill_id, confidence in validated.skills.items():
        quote = evidence.get(skill_id)
        if not isinstance(quote, str) or not quote.strip() or quote.casefold() not in text_folded:
            discarded_count += 1
            continue
        if mention_check(skill_id, quote, taxonomy[skill_id]) and mention_check(
            skill_id, text, taxonomy[skill_id]
        ):
            grounded[skill_id] = confidence
        else:
            discarded_count += 1
    if discarded_count:
        logger.warning(
            "extract_skills: discarded %d model skill(s) without valid positive evidence",
            discarded_count,
        )
    return grounded


# ── Public API ────────────────────────────────────────────────────────────────

def extract_skills(
    text: str, db: Session, *, goal_context: bool = False
) -> dict[str, float]:
    """Extract skill confidences or explicit learning targets from text.

    Uses the LLM with the skill-extraction prompt, validates with SkillScores,
    and falls back to conservative phrase matching on any failure. Set
    ``goal_context`` for student learning-goal extraction.
    Returns {skill_id: confidence}.
    """
    from app.services.skills import fallback_extract, load_taxonomy

    taxonomy_ids = ", ".join(sorted(load_taxonomy().keys()))
    system = SKILL_EXTRACTION_SYSTEM
    prompt = SKILL_EXTRACTION_USER_TEMPLATE.format(
        taxonomy_ids=taxonomy_ids, text=text
    )
    if goal_context:
        prompt = f"{SKILL_GOAL_CONTEXT_INSTRUCTION}\n{prompt}"
    key = _cache_key(system, prompt)

    # Check cache first
    cached = _read_cache(db, key)
    if cached:
        logger.info("extract_skills: cache hit")
        try:
            return _grounded_skill_scores(
                _loads_tolerant(cached), text, goal_context=goal_context
            )
        except Exception:
            pass

    client = get_llm_client(db)
    for attempt in range(2):
        t0 = time.monotonic()
        try:
            raw = client.complete_json(system, prompt, timeout_s=6.0)
            latency = time.monotonic() - t0
            logger.info("extract_skills: LLM latency=%.2fs attempt=%d", latency, attempt + 1)
            validated = _grounded_skill_scores(
                _loads_tolerant(raw), text, goal_context=goal_context
            )
            _write_cache(db, key, raw)
            return validated
        except LLMUnavailable:
            break
        except Exception as exc:
            logger.warning("extract_skills: attempt %d failed: %s", attempt + 1, exc)
            if attempt == 1:
                break

    logger.warning("extract_skills: LLM extraction unavailable — using keyword fallback")
    return fallback_extract(text, goal_context=goal_context)


def rerank_and_explain(
    student_json: str, candidates_json: str, db: Session
) -> list[dict]:
    """Re-rank top-5 matches to 3 and write explanations using the LLM.

    Falls back to template explanations on any failure.
    Returns list of {mentor_id, rank, explanation} dicts.
    """
    from app.schemas.match import MatchExplanations

    system = RERANK_SYSTEM
    prompt = RERANK_USER_TEMPLATE.format(
        student_json=student_json, candidates_json=candidates_json
    )
    key = _cache_key(system, prompt)

    # Check cache first
    cached = _read_cache(db, key)
    if cached:
        logger.info("rerank_and_explain: cache hit")
        try:
            result = MatchExplanations.model_validate_json(cached)
            return [m.model_dump() for m in result.matches]
        except Exception:
            pass

    client = get_llm_client(db)
    for attempt in range(2):
        t0 = time.monotonic()
        try:
            raw = client.complete_json(system, prompt, timeout_s=6.0)
            latency = time.monotonic() - t0
            logger.info("rerank_and_explain: LLM latency=%.2fs attempt=%d", latency, attempt + 1)
            result = MatchExplanations.model_validate(_loads_tolerant(raw))
            # Validate mentor ids are among the top-5
            top5_ids = {
                str(c["mentor_id"])
                for c in json.loads(candidates_json)
            }
            for match in result.matches:
                if str(match.mentor_id) not in top5_ids:
                    raise ValueError(f"mentor_id {match.mentor_id!r} not in top-5 candidates")
            _write_cache(db, key, raw)
            return [m.model_dump() for m in result.matches]
        except LLMUnavailable:
            break
        except Exception as exc:
            logger.warning("rerank_and_explain: attempt %d failed: %s", attempt + 1, exc)
            if attempt == 1:
                break

    logger.warning("rerank_and_explain: LLM rerank unavailable — using template fallback")
    return _fallback_explanations(candidates_json)


def _fallback_explanations(candidates_json: str) -> list[dict]:
    """Generate template explanations for the top 3 candidates."""
    try:
        candidates = json.loads(candidates_json)[:3]
    except Exception:
        return []

    result = []
    for i, c in enumerate(candidates, start=1):
        mentor_level = c.get("experience_level", "experienced")
        student_level = c.get("student_level", "developing")
        shared = c.get("shared_skills", [])
        shared_str = ", ".join(shared[:3]) if shared else "relevant skills"
        overlap = c.get("overlap_summary", "some overlapping availability")
        name = c.get("mentor_name", "This mentor")
        explanation = (
            f"{name} is {mentor_level} in {shared_str}, a good step up from your "
            f"{student_level} level, and is free {overlap}, which fits your schedule."
        )
        result.append({
            "mentor_id": str(c.get("mentor_id", "")),
            "rank": i,
            "explanation": explanation,
        })
    return result
