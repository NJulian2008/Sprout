"""Integration tests proving the LLM fallback paths work."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.services import llm as llm_module
from app.services.llm import LLMUnavailable, extract_skills


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.close()


class FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def complete_json(self, system, prompt, timeout_s=6.0):
        if self._exc:
            raise self._exc
        return self._response


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(llm_module, "get_llm_client", lambda db: client)


def test_valid_json_parsed(monkeypatch, db):
    raw = (
        '{"skills": {"python": 0.8, "docker": 0.6}, '
        '"evidence": {"python": "Python", "docker": "Docker"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))
    result = extract_skills("Python and Docker resume text", db)
    assert result == {"python": 0.8, "docker": 0.6}


def test_malformed_json_falls_back(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient("{broken json"))
    # Fallback scans the text itself
    result = extract_skills("I know python and docker", db)
    assert "python" in result
    assert "docker" in result


def test_timeout_falls_back(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient(exc=TimeoutError("too slow")))
    result = extract_skills("python developer", db)
    assert "python" in result  # from fallback keyword scan


def test_unavailable_falls_back(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient(exc=LLMUnavailable("off")))
    result = extract_skills("python and react", db)
    assert "python" in result
    assert "react" in result


def test_unknown_skill_ids_dropped(monkeypatch, db):
    raw = (
        '{"skills": {"python": 0.8, "quantumwizardry": 0.9}, '
        '"evidence": {"python": "Python"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))
    result = extract_skills("Python resume", db)
    assert "python" in result
    assert "quantumwizardry" not in result


def test_confidence_clamped(monkeypatch, db):
    raw = (
        '{"skills": {"python": 1.5, "docker": -0.2}, '
        '"evidence": {"python": "Python", "docker": "Docker"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))
    result = extract_skills("Python and Docker resume", db)
    assert result["python"] == 1.0
    assert result["docker"] == 0.0


def test_model_skills_without_verbatim_evidence_are_dropped(monkeypatch, db):
    raw = (
        '{"skills": {"python": 0.95}, '
        '"evidence": {"python": "Built a machine learning model"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))

    assert extract_skills("I have no programming experience.", db) == {}


def test_model_skills_with_negated_evidence_are_dropped(monkeypatch, db):
    raw = (
        '{"skills": {"python": 0.95}, '
        '"evidence": {"python": "No experience with Python"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))

    assert extract_skills("No experience with Python.", db) == {}


def test_model_skills_require_evidence_field(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient('{"skills": {"python": 0.95}}'))

    result = extract_skills("Python developer", db)
    assert result == {"python": 0.3}


def test_model_goal_extraction_accepts_explicit_learning_target(monkeypatch, db):
    raw = (
        '{"skills": {"machine_learning": 0.8}, '
        '"evidence": {"machine_learning": "Build an ML project"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))

    result = extract_skills("Build an ML project", db, goal_context=True)
    assert result == {"machine_learning": 0.8}


# ───────────────────────────────────────────────────────────────────────────
# Bug condition exploration tests (spec: skill-extraction-data-corruption-fix)
#
# These tests target the CURRENT (unfixed) behavior described in the bugfix
# requirements. They are EXPECTED TO FAIL on unfixed code — their failure
# confirms the defect exists. They encode the post-fix expected behavior, so
# they will pass once the fixes are implemented.
#
# Scope:
#   - Stale cache: _cache_key ignores the taxonomy version (requirement 1.5)
#   - Fenced-but-valid JSON forced into fallback (requirement 1.7)
# ───────────────────────────────────────────────────────────────────────────


def test_bug_cache_key_ignores_taxonomy_version(monkeypatch):
    """Requirement 1.5 — _cache_key has no version/taxonomy component.

    When the taxonomy changes, the cache key must change so stale entries are
    not served. On unfixed code `_cache_key = sha256(system + prompt)` ignores
    the taxonomy entirely, so the key is identical before and after a taxonomy
    change — i.e. the stale entry would still be hit.

    EXPECTED (post-fix): the key changes when the taxonomy changes.
    EXPECTED (unfixed, failing): the key is unchanged.
    """
    from app.services.llm import _cache_key

    system = "SYSTEM PROMPT"
    prompt = "USER PROMPT"

    # Key with the original taxonomy.
    key_before = _cache_key(system, prompt)

    # Simulate a taxonomy change (different set of skill ids).
    monkeypatch.setattr(
        llm_module,
        "load_taxonomy",
        lambda: {"python": {}, "a_brand_new_skill": {}},
        raising=False,
    )
    # Also patch at the source module in case the key reads it from there.
    import app.services.skills as skills_module

    monkeypatch.setattr(
        skills_module,
        "load_taxonomy",
        lambda: {"python": {}, "a_brand_new_skill": {}},
    )
    skills_module.load_taxonomy.cache_clear() if hasattr(
        skills_module.load_taxonomy, "cache_clear"
    ) else None

    key_after = _cache_key(system, prompt)

    # Post-fix expectation (FAILS on unfixed code, which ignores taxonomy):
    assert key_before != key_after, (
        "cache key must change when the taxonomy changes so stale entries "
        "are not served"
    )


def test_bug_fenced_json_forced_into_fallback(monkeypatch, db):
    """Requirement 1.7 — valid JSON in markdown fences drops to fallback.

    The LLM returns valid skill JSON wrapped in a ```json ... ``` fence. The
    strict `json.loads(raw)` in extract_skills raises on the fence, the error
    is swallowed, and the weaker keyword fallback runs. Post-fix the fences are
    stripped and the JSON is parsed.

    We give the LLM a high (0.8) confidence that the conservative fallback
    cannot produce from a single mention (it assigns a fixed 0.3), so the
    two paths are distinguishable.

    EXPECTED (post-fix): fenced JSON parsed → {"python": 0.8}.
    EXPECTED (unfixed, failing): strict json.loads raises on the fence and the
    keyword fallback runs, returning a fallback-scored value (!= 0.8).
    """
    fenced = '```json\n{"skills": {"python": 0.8}, "evidence": {"python": "python"}}\n```'
    _patch_client(monkeypatch, FakeClient(fenced))

    # The keyword fallback scores "python" from literal mentions, not 0.8.
    result = extract_skills("python", db)

    # Post-fix expectation (FAILS on unfixed code, which falls back):
    assert result == {"python": 0.8}, (
        f"fenced-but-valid JSON must be parsed, not dropped to fallback; "
        f"got {result}"
    )


# ───────────────────────────────────────────────────────────────────────────
# Preservation property tests (spec: skill-extraction-data-corruption-fix)
#
# Property 5 (Preservation): Non-buggy inputs unchanged.
#
# Observation-first methodology: these capture the CURRENT (unfixed) behavior
# as the baseline to preserve. They MUST PASS on unfixed code, and must keep
# passing after the fixes (no regression).
#
# Scope here (llm.py paths):
#   - Bare JSON (no fences) parses and validates             (3.4)
#   - A cached response for an unchanged prompt is a hit      (3.5)
#   - LLM off falls back to fallback_extract keyword scores   (3.6)
# ───────────────────────────────────────────────────────────────────────────


class RecordingClient:
    """A client that records whether it was called and returns a fixed response."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = 0

    def complete_json(self, system, prompt, timeout_s=6.0):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._response


def test_preserve_bare_json_parses_and_validates(monkeypatch, db):
    """3.4 — a bare JSON object (no markdown fences) parses and validates.

    Baseline captured on unfixed code: a bare `{"skills": {"python": 0.8}}`
    response is parsed by json.loads and validated by SkillScores, yielding the
    cleaned dict. This is the behavior that must be preserved after adding
    tolerant (fence-stripping) parsing.
    """
    bare = '{"skills": {"python": 0.8}, "evidence": {"python": "python"}}'
    _patch_client(monkeypatch, FakeClient(bare))

    result = extract_skills("python developer", db)

    # Baseline: bare JSON yields exactly the cleaned SkillScores dict.
    assert result == {"python": 0.8}


def test_preserve_cache_hit_for_unchanged_prompt(monkeypatch, db):
    """3.5 — a cached response for an unchanged prompt+taxonomy is a cache hit.

    Baseline captured on unfixed code: when a valid cached row exists under the
    key for the current system+prompt (unchanged taxonomy), extract_skills
    serves it WITHOUT calling the LLM client. We pre-seed the cache with the
    exact key extract_skills computes, then assert the cached value is returned
    and the client is never invoked.
    """
    from app.db.models import LLMCache
    from app.services.llm import (
        _cache_key,
        _read_cache,
    )
    from app.services.prompts import (
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE,
    )
    from app.services.skills import load_taxonomy

    text = "python and docker resume"
    taxonomy_ids = ", ".join(sorted(load_taxonomy().keys()))
    system = SKILL_EXTRACTION_SYSTEM
    prompt = SKILL_EXTRACTION_USER_TEMPLATE.format(taxonomy_ids=taxonomy_ids, text=text)
    key = _cache_key(system, prompt)

    # Seed the cache with a valid SkillScores JSON payload under that key.
    cached_payload = (
        '{"skills": {"python": 0.6, "docker": 0.5}, '
        '"evidence": {"python": "python", "docker": "docker"}}'
    )
    db.add(LLMCache(key=key, response=cached_payload))
    db.commit()

    # Baseline: the key resolves to the seeded row (a hit, not a miss).
    assert _read_cache(db, key) == cached_payload

    # A client that would blow up if it were ever called — proving the hit path
    # short-circuits before any LLM call.
    client = RecordingClient(exc=AssertionError("client must not be called on cache hit"))
    _patch_client(monkeypatch, client)

    result = extract_skills(text, db)

    # Baseline: cached content is returned, cleaned via SkillScores.
    assert result == {"python": 0.6, "docker": 0.5}
    assert client.calls == 0, "cache hit must not call the LLM client"


def test_preserve_llm_off_returns_fallback_keyword_scores(monkeypatch, db):
    """3.6 — LLM_MODE=off returns fallback_extract keyword scores.

    Baseline captured on unfixed code: with the LLM unavailable, extract_skills
    returns exactly what fallback_extract produces for the same text. We drive
    the "off" path via a client that raises LLMUnavailable and compare against
    fallback_extract directly.
    """
    from app.services.skills import fallback_extract

    _patch_client(monkeypatch, FakeClient(exc=LLMUnavailable("off")))

    text = "I use python, docker, and react every day"
    result = extract_skills(text, db)
    expected = fallback_extract(text)

    # Baseline: the LLM-off result is identical to the keyword fallback.
    assert result == expected
    # Sanity: fallback did find keyword skills (not an empty baseline).
    assert "python" in result
    assert "docker" in result
    assert "react" in result

# ───────────────────────────────────────────────────────────────────────────
# Versioned cache key unit tests (spec: skill-extraction-data-corruption-fix)
#
# Task 5.2 — Fix 3 (_cache_key, _taxonomy_signature, CACHE_VERSION, _write_cache
# in app/services/llm.py). _cache_key now hashes
#   f"{CACHE_VERSION}\x00{_taxonomy_signature()}\x00{system}\x00{prompt}"
# so changing the version, the taxonomy ids, the system, or the prompt each
# changes the key, while identical inputs yield identical keys. _write_cache is
# reached only AFTER schema validation succeeds.
#
# Covers requirements 2.5, 2.6 and preservation 3.5; design Correctness
# Property 3.
# ───────────────────────────────────────────────────────────────────────────


def _patch_taxonomy(monkeypatch, taxonomy):
    """Patch load_taxonomy at the source module and clear its lru_cache.

    _taxonomy_signature imports load_taxonomy from app.services.skills inside
    the function, so patching there (and clearing the cache) is what the key
    actually reads. Mirrors test_bug_cache_key_ignores_taxonomy_version.
    """
    import app.services.skills as skills_module

    monkeypatch.setattr(skills_module, "load_taxonomy", lambda: taxonomy)
    if hasattr(skills_module.load_taxonomy, "cache_clear"):
        skills_module.load_taxonomy.cache_clear()


def test_cache_key_changes_when_cache_version_changes(monkeypatch):
    """2.5 — bumping CACHE_VERSION changes the key (stale entries invalidated)."""
    from app.services.llm import _cache_key

    system = "SYSTEM PROMPT"
    prompt = "USER PROMPT"

    key_before = _cache_key(system, prompt)

    monkeypatch.setattr(llm_module, "CACHE_VERSION", "v999")
    key_after = _cache_key(system, prompt)

    assert key_before != key_after, (
        "bumping CACHE_VERSION must change the cache key"
    )


def test_cache_key_changes_when_prompt_changes(monkeypatch):
    """2.5 — changing the prompt changes the key."""
    from app.services.llm import _cache_key

    system = "SYSTEM PROMPT"
    key_before = _cache_key(system, "USER PROMPT A")
    key_after = _cache_key(system, "USER PROMPT B")

    assert key_before != key_after, "a different prompt must yield a different key"


def test_cache_key_changes_when_system_changes(monkeypatch):
    """2.5 — changing the system prompt changes the key."""
    from app.services.llm import _cache_key

    prompt = "USER PROMPT"
    key_before = _cache_key("SYSTEM A", prompt)
    key_after = _cache_key("SYSTEM B", prompt)

    assert key_before != key_after, "a different system must yield a different key"


def test_cache_key_changes_when_taxonomy_ids_change(monkeypatch):
    """2.5 — changing the taxonomy ids changes the key.

    Folds _taxonomy_signature into the key, so a taxonomy change invalidates
    stale entries. Patches app.services.skills.load_taxonomy (the module the
    signature actually reads) and clears the lru_cache.
    """
    from app.services.llm import _cache_key

    system = "SYSTEM PROMPT"
    prompt = "USER PROMPT"

    _patch_taxonomy(monkeypatch, {"python": {}, "docker": {}})
    key_before = _cache_key(system, prompt)

    _patch_taxonomy(monkeypatch, {"python": {}, "a_brand_new_skill": {}})
    key_after = _cache_key(system, prompt)

    assert key_before != key_after, (
        "cache key must change when the taxonomy ids change"
    )


def test_cache_key_identical_inputs_are_deterministic(monkeypatch):
    """3.5 — identical version + taxonomy + system + prompt give identical keys."""
    from app.services.llm import _cache_key

    system = "SYSTEM PROMPT"
    prompt = "USER PROMPT"

    _patch_taxonomy(monkeypatch, {"python": {}, "docker": {}})

    key_a = _cache_key(system, prompt)
    key_b = _cache_key(system, prompt)

    assert key_a == key_b, "identical inputs must produce identical keys"


def test_write_cache_not_reached_on_invalid_json(monkeypatch, db):
    """2.6 — invalid JSON triggers fallback and writes nothing to the cache.

    _write_cache is only reached after SkillScores validation succeeds. When
    the LLM returns unparseable JSON, extract_skills falls back to the keyword
    scan and must not persist any LLMCache row for the computed key.
    """
    from app.db.models import LLMCache
    from app.services.llm import (
        _cache_key,
        extract_skills as _extract,
    )
    from app.services.prompts import (
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE,
    )
    from app.services.skills import load_taxonomy

    text = "I know python and docker"
    taxonomy_ids = ", ".join(sorted(load_taxonomy().keys()))
    key = _cache_key(
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE.format(taxonomy_ids=taxonomy_ids, text=text),
    )

    _patch_client(monkeypatch, FakeClient("{broken json"))
    _extract(text, db)

    row = db.query(LLMCache).filter(LLMCache.key == key).first()
    assert row is None, "nothing should be cached when the LLM response is invalid"


def test_write_cache_not_reached_on_schema_invalid_content(monkeypatch, db):
    """2.6 — schema-invalid content (parseable JSON, wrong shape) writes nothing.

    The JSON parses but fails SkillScores validation, so extract_skills falls
    back and no LLMCache row is written for the key.
    """
    from app.db.models import LLMCache
    from app.services.llm import (
        _cache_key,
        extract_skills as _extract,
    )
    from app.services.prompts import (
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE,
    )
    from app.services.skills import load_taxonomy

    text = "I know python and docker"
    taxonomy_ids = ", ".join(sorted(load_taxonomy().keys()))
    key = _cache_key(
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE.format(taxonomy_ids=taxonomy_ids, text=text),
    )

    # Valid JSON, but the wrong schema (SkillScores expects a "skills" mapping
    # of {id: number}; here "skills" is a string, which fails validation).
    _patch_client(monkeypatch, FakeClient('{"skills": "not a mapping"}'))
    _extract(text, db)

    row = db.query(LLMCache).filter(LLMCache.key == key).first()
    assert row is None, (
        "nothing should be cached when the LLM response fails schema validation"
    )


def test_write_cache_reached_after_valid_content(monkeypatch, db):
    """2.6 (contrast) — valid content IS written to the cache after validation."""
    from app.db.models import LLMCache
    from app.services.llm import (
        _cache_key,
        extract_skills as _extract,
    )
    from app.services.prompts import (
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE,
    )
    from app.services.skills import load_taxonomy

    text = "python and docker resume"
    taxonomy_ids = ", ".join(sorted(load_taxonomy().keys()))
    raw = (
        '{"skills": {"python": 0.8, "docker": 0.6}, '
        '"evidence": {"python": "python", "docker": "docker"}}'
    )
    key = _cache_key(
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE.format(taxonomy_ids=taxonomy_ids, text=text),
    )

    _patch_client(monkeypatch, FakeClient(raw))
    result = _extract(text, db)

    assert result == {"python": 0.8, "docker": 0.6}
    row = db.query(LLMCache).filter(LLMCache.key == key).first()
    assert row is not None, "valid content must be written to the cache after validation"
    assert row.response == raw, "the validated raw response is what gets cached"

# ───────────────────────────────────────────────────────────────────────────
# Tolerant parsing + fallback-signal tests (spec: skill-extraction-data-corruption-fix)
#
# Task 6.2 — Fix 4 (_loads_tolerant, _FENCE_RE, and the upgraded fallback
# warning in app/services/llm.py). _loads_tolerant(raw) strips an optional
# surrounding markdown code fence (```json ... ``` or ``` ... ```) via _FENCE_RE
# then json.loads the inner content; a bare object passes through unchanged and
# non-JSON still raises. Both fallback logs were upgraded to logger.warning so a
# keyword-fallback result is clearly distinguished from a successful extraction.
#
# Covers requirements 2.7, 2.8 and preservation 3.4; design Correctness
# Property 4.
# ───────────────────────────────────────────────────────────────────────────

import json
import logging
import random


def test_loads_tolerant_fenced_json_language_fence():
    """2.7 — a ```json ... ``` fenced payload parses to the inner object."""
    from app.services.llm import _loads_tolerant

    fenced = '```json\n{"skills": {"python": 0.8, "docker": 0.6}}\n```'
    assert _loads_tolerant(fenced) == {"skills": {"python": 0.8, "docker": 0.6}}


def test_loads_tolerant_fenced_json_bare_fence():
    """2.7 — a ``` ... ``` (no language) fenced payload parses to the inner object."""
    from app.services.llm import _loads_tolerant

    fenced = '```\n{"skills": {"python": 0.8, "docker": 0.6}}\n```'
    assert _loads_tolerant(fenced) == {"skills": {"python": 0.8, "docker": 0.6}}


def test_loads_tolerant_bare_object():
    """3.4 — a bare object (no fences) parses exactly like json.loads."""
    from app.services.llm import _loads_tolerant

    bare = '{"skills": {"python": 0.8, "docker": 0.6}}'
    assert _loads_tolerant(bare) == {"skills": {"python": 0.8, "docker": 0.6}}


def test_loads_tolerant_all_forms_agree():
    """2.7 / 3.4 — fenced (json), fenced (bare), and unfenced all parse equal."""
    from app.services.llm import _loads_tolerant

    obj = {"skills": {"python": 0.8, "react": 0.5}}
    payload = json.dumps(obj)
    forms = [
        payload,
        f"```json\n{payload}\n```",
        f"```\n{payload}\n```",
    ]
    results = [_loads_tolerant(f) for f in forms]
    assert all(r == obj for r in results), results


def test_loads_tolerant_non_json_still_raises():
    """2.7 — malformed JSON still raises (json.JSONDecodeError / ValueError)."""
    from app.services.llm import _loads_tolerant

    with pytest.raises(ValueError):
        _loads_tolerant("{broken json")


def test_loads_tolerant_non_json_inside_fence_still_raises():
    """2.7 — a fence wrapping malformed JSON still raises after fence strip."""
    from app.services.llm import _loads_tolerant

    with pytest.raises(ValueError):
        _loads_tolerant("```json\n{broken json\n```")


def test_fallback_path_emits_warning_record(monkeypatch, db, caplog):
    """2.8 — the keyword-fallback path emits a WARNING-level record.

    Drive extract_skills with a client that is unavailable so it falls through
    to the keyword fallback, and assert a WARNING record mentioning the fallback
    is present (not merely an info-level log).
    """
    _patch_client(monkeypatch, FakeClient(exc=LLMUnavailable("off")))

    with caplog.at_level(logging.WARNING, logger="app.services.llm"):
        result = extract_skills("I know python and docker", db)

    # The fallback actually ran (keyword scores present).
    assert "python" in result

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "the fallback path must emit at least one WARNING record"
    assert any("fallback" in r.getMessage().lower() for r in warnings), (
        f"expected a warning mentioning the fallback; got "
        f"{[r.getMessage() for r in warnings]}"
    )


def test_successful_extraction_emits_no_warning(monkeypatch, db, caplog):
    """2.8 (contrast) — a successful LLM extraction logs no WARNING record.

    The happy path logs latency at info level; it must not surface a warning,
    so a warning unambiguously signals the weaker keyword path.
    """
    raw = (
        '{"skills": {"python": 0.8, "docker": 0.6}, '
        '"evidence": {"python": "python", "docker": "docker"}}'
    )
    _patch_client(monkeypatch, FakeClient(raw))

    with caplog.at_level(logging.WARNING, logger="app.services.llm"):
        result = extract_skills("python and docker resume", db)

    assert result == {"python": 0.8, "docker": 0.6}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not warnings, (
        f"a successful extraction must not emit warnings; got "
        f"{[r.getMessage() for r in warnings]}"
    )


def _random_skill_json_object(rng):
    """Build a random valid skill JSON object using a seeded stdlib rng.

    Keys are arbitrary (they need not be taxonomy ids — _loads_tolerant is a
    pure parser and does no validation), values are rounded floats in [0, 1].
    """
    pool = ["python", "docker", "react", "sql", "aws", "go", "rust", "kotlin"]
    n = rng.randint(0, len(pool))
    chosen = rng.sample(pool, n)
    skills = {sid: round(rng.random(), 2) for sid in chosen}
    return {"skills": skills}


def test_loads_tolerant_property_fenced_and_unfenced_recover_same_object():
    """Property 4 — _loads_tolerant recovers the same object fenced or unfenced.

    Generate random valid skill JSON objects (seeded stdlib random, matching the
    existing non-Hypothesis pattern), serialize them, wrap half in fences (mixing
    ```json and bare ```), and assert _loads_tolerant recovers the original object
    in both fenced and unfenced forms.

    **Validates: Requirements 2.7**
    """
    from app.services.llm import _loads_tolerant

    rng = random.Random(20240217)
    for i in range(200):
        obj = _random_skill_json_object(rng)
        payload = json.dumps(obj)

        # Unfenced always recovers the object.
        assert _loads_tolerant(payload) == obj

        # Wrap half the cases in a fence, alternating fence style.
        if i % 2 == 0:
            fence = "json" if (i % 4 == 0) else ""
            fenced = f"```{fence}\n{payload}\n```"
            assert _loads_tolerant(fenced) == obj, (
                f"fenced form must recover the same object; iter={i} "
                f"fence={fence!r} obj={obj}"
            )


def test_fenced_llm_response_parsed_validated_and_cached(monkeypatch, db):
    """Integration — a fenced LLM response is parsed, validated, and cached.

    A fenced ```json ... ``` response from the client is recovered by
    _loads_tolerant on the LLM-response path, validated by SkillScores, returned
    as the cleaned dict, AND written to the cache as the raw fenced string. A
    second identical call still returns the correct skills.

    Fenced cached responses use the same tolerant parser as fresh LLM responses,
    so the second call should return the cached result without another request.

    **Validates: Requirements 2.7, 2.8, 3.4**
    """
    from app.db.models import LLMCache
    from app.services.llm import (
        _cache_key,
        extract_skills as _extract,
    )
    from app.services.prompts import (
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE,
    )
    from app.services.skills import load_taxonomy

    text = "python and docker resume"
    taxonomy_ids = ", ".join(sorted(load_taxonomy().keys()))
    key = _cache_key(
        SKILL_EXTRACTION_SYSTEM,
        SKILL_EXTRACTION_USER_TEMPLATE.format(taxonomy_ids=taxonomy_ids, text=text),
    )

    fenced_raw = (
        '```json\n{"skills": {"python": 0.8, "docker": 0.6}, '
        '"evidence": {"python": "python", "docker": "docker"}}\n```'
    )
    client = RecordingClient(fenced_raw)
    _patch_client(monkeypatch, client)

    # First call: fenced response parsed via _loads_tolerant, validated, returned.
    first = _extract(text, db)
    assert first == {"python": 0.8, "docker": 0.6}
    assert client.calls == 1, "first call must hit the LLM-response path"

    # The raw fenced string is written to the cache verbatim after validation.
    row = db.query(LLMCache).filter(LLMCache.key == key).first()
    assert row is not None, "a validated fenced response must be cached"
    assert row.response == fenced_raw, "the raw fenced response is cached verbatim"

    # Second identical call: still returns the correct skills. Because the cache
    # branch uses model_validate_json on the fenced raw (which raises on the
    # fence), it falls through and the fence-tolerant LLM path serves it again.
    second = _extract(text, db)
    assert second == {"python": 0.8, "docker": 0.6}
    assert client.calls == 1, "a valid fenced response should be served from cache"
