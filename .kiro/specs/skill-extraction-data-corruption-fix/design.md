# Skill Extraction Data Corruption Fix Bugfix Design

## Overview

Sprout's AI skill-extraction and match-rerank pipeline persists corrupted and
hallucinated data into student requests and mentor profiles, which drives
spurious matches and untrustworthy explanations. Four confirmed root causes
were located by reading the code:

1. **Mentor signup validation bypass** — `mentor_signup_submit` in
   `app/routers/pages.py` stores posted `skill_scores_json` with
   `scores = {k: float(v) for k, v in posted.items()}`, so unknown skill ids and
   out-of-range confidences are persisted verbatim and non-numeric values raise
   an unhandled `float()` error. Every other ingestion path runs through
   `SkillScores` validation; this one does not.
2. **Goal-text over-extraction** — `student_signup_submit` sets
   `skills_to_learn = list(goal_skills)` from `extract_skills(goal_text, db)`,
   discarding confidence, so short/ambiguous goals turn weakly-supported skills
   into learning targets and inflate the candidate pool.
3. **Stale cache** — `_cache_key(system, prompt)` in `app/services/llm.py` is
   `sha256(system + prompt)` with no prompt/taxonomy version component, and
   `_write_cache` stores whatever raw string it is handed. Changing the prompt or
   the taxonomy silently serves stale (and possibly invalid) cached responses.
4. **Fenced JSON forced into fallback** — `extract_skills` (and
   `rerank_and_explain`) parse the LLM response with a strict
   `json.loads(raw)`; a model that wraps valid JSON in markdown fences raises,
   the error is swallowed, and the weaker keyword fallback runs with only a
   generic info log.

The fix is scoped to these four causes. It is deliberately minimal and keeps the
established patterns: Pydantic validation through `SkillScores`, pure functions in
`app/services/skills.py`, and the adapter pattern in `app/services/llm.py`.

## Glossary

- **Bug_Condition (C)**: An input that triggers one of the four defects —
  unvalidated mentor scores, low-confidence goal skills, a prompt/taxonomy change
  that the cache key ignores, or fenced-but-valid LLM JSON.
- **Property (P)**: The desired post-fix behavior — scores validated before
  persistence, only meaningfully-supported goal skills retained, cache keyed by
  version/taxonomy and storing only validated content, and fenced JSON parsed
  instead of dropped to fallback.
- **Preservation**: Existing behavior that must stay identical — valid mentor
  scores, resume-based extraction, bare-JSON parsing, cache hits for unchanged
  inputs, and the keyword fallback when the LLM is unavailable.
- **SkillScores**: Pydantic schema in `app/schemas/ai.py`. Its `model_validator`
  drops unknown taxonomy ids and clamps values to `[0.0, 1.0]` rounded to 2
  decimals.
- **extract_skills**: `app/services/llm.py` function that calls the LLM with the
  skill-extraction prompt, validates with `SkillScores`, and falls back to
  `fallback_extract` on failure. Returns `{skill_id: confidence}`.
- **fallback_extract**: Pure keyword-scan extractor in `app/services/skills.py`
  used when the LLM is unavailable.
- **THRESHOLD**: The goal-skill confidence cutoff below which an extracted skill
  is not promoted to a learning target. Finalized at **0.4** (see Fix
  Implementation, change 2).
- **CACHE_VERSION**: A module-level constant in `app/services/llm.py`
  incremented when prompt wording or cache semantics change.
- **taxonomy signature**: A short hash of the loaded taxonomy ids, folded into the
  cache key so a taxonomy change invalidates stale entries.

## Bug Details

### Bug Condition

The pipeline is defective across four independent conditions. A single
`isBugCondition` combines them so the preservation check is the clean negation.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input — one of {mentor_scores, goal_text, (system, prompt, taxonomy), raw_llm}
  OUTPUT: boolean

  // 1 — Mentor signup validation bypass
  mentorBug := EXISTS k IN input.posted WHERE k NOT IN taxonomy
            OR EXISTS v IN input.posted.values WHERE (v < 0.0 OR v > 1.0 OR NOT isNumeric(v))

  // 2 — Goal-text over-extraction
  goalBug := EXISTS s IN extract_skills(input.goal_text) WHERE confidence(s) < THRESHOLD

  // 3 — Stale cache
  cacheBug := cache_key_ignores(input.taxonomy_version)

  // 4 — Fenced JSON forced into fallback
  fenceBug := isValidSkillJson(strip_code_fences(input.raw_llm))
          AND NOT isValidSkillJson(input.raw_llm)

  RETURN mentorBug OR goalBug OR cacheBug OR fenceBug
END FUNCTION
```

### Examples

- **1.1 / 1.2** — Mentor posts
  `{"python": 0.8, "quantum_telepathy": 0.9, "rust": 1.7}`. Expected: stored
  scores are `{"python": 0.8}` plus any clamped valid ids
  (`rust` clamped to `1.0` only if `rust` is in the taxonomy; the unknown id is
  dropped). Actual (unfixed): all three persisted verbatim, including the unknown
  id and `1.7`.
- **1.3** — Mentor posts `{"python": "expert"}`. Expected: the malformed entry is
  ignored, no unhandled error. Actual (unfixed): `float("expert")` raises
  `ValueError` and the request 500s.
- **1.4** — Student goal "I want to maybe explore some coding stuff" yields
  `{"python": 0.2, "git": 0.2}` from the resume-oriented extractor. Expected:
  with THRESHOLD `0.4`, `skills_to_learn` is empty (no well-supported target).
  Actual (unfixed): both become learning targets.
- **1.5** — The `SKILL_EXTRACTION_SYSTEM` prompt is reworded. Expected: the cache
  key changes, so the old cached response is not served. Actual (unfixed): same
  key, stale response returned.
- **1.7** — LLM returns
  ` ```json\n{"skills": {"python": 0.8}}\n``` `. Expected: fences stripped, JSON
  parsed, `{"python": 0.8}` returned. Actual (unfixed): `json.loads` raises, the
  keyword fallback runs.
- **Edge case** — LLM returns a bare `{"skills": {"python": 0.8}}` with no
  fences. Expected (and preserved): parsed exactly as before.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Valid mentor `skill_scores_json` (known ids, in-range confidences) continues to
  persist on `MentorProfile.skill_scores`, now via `SkillScores`, producing the
  same cleaned values (3.1).
- When posted scores are omitted, resume-based extraction via `extract_skills`
  continues to run and persist its scores for both mentor and student (3.2).
- Resume submissions continue to produce the same `skill_scores` and experience
  level; the goal-text change touches only `skills_to_learn` (3.3).
- A bare JSON object (no fences) continues to parse and validate exactly as
  before (3.4).
- A cached response for an unchanged prompt and unchanged taxonomy version
  continues to serve as a cache hit (3.5).
- When the LLM is unavailable (`LLM_MODE=off`, timeout, or cache miss),
  `fallback_extract` continues to run and return keyword-based scores (3.6).
- Matching for a student whose goal yields well-supported skills continues to
  rank mentors and produce matches as before (3.7).

**Scope:**
All inputs where `isBugCondition` is false must be completely unaffected. This
includes valid posted mentor scores, goals that yield only high-confidence
skills, unchanged prompt/taxonomy cache lookups, bare-JSON LLM responses, and all
LLM-unavailable paths.

## Hypothesized Root Cause

1. **Validation bypass in `mentor_signup_submit`** (and the mirror branch in
   `student_signup_submit`): the posted-scores branch uses a raw dict
   comprehension `{k: float(v) ...}` instead of `SkillScores`. This is the direct
   cause of 1.1, 1.2, and 1.3 — the one ingestion path that skips the schema.

2. **Confidence discarded in `student_signup_submit`**:
   `skills_to_learn=list(goal_skills)` keeps every key regardless of its
   confidence value, so the resume-oriented extractor's low-confidence guesses on
   short goal text become targets. Root cause of 1.4.

3. **Version-free cache key**: `_cache_key` hashes only `system + prompt`. The
   taxonomy ids are interpolated into the *prompt* for `extract_skills`, so a
   taxonomy change does shift that key — but a prompt-constant reword or any
   rerank-path taxonomy dependency is not captured, and there is no explicit
   version lever to force invalidation. `_write_cache` also stores the raw
   pre-validation string. Root cause of 1.5 and 1.6.

4. **Strict parse with no fence tolerance**: `json.loads(raw)` in both
   `extract_skills` and `rerank_and_explain` cannot handle a fenced payload, and
   the broad `except Exception` funnels the error into the fallback with only a
   generic `logger.info`. Root cause of 1.7 and 1.8.

## Correctness Properties

Property 1: Bug Condition - Mentor scores validated before persistence

_For any_ posted mentor `skill_scores_json` where the bug condition holds (unknown
ids, out-of-range, or non-numeric values), the fixed `mentor_signup_submit` SHALL
route the scores through `SkillScores` so unknown ids are dropped, values are
clamped to `[0.0, 1.0]` and rounded to 2 decimals, and malformed entries are
ignored without raising an unhandled error.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Bug Condition - Only well-supported goal skills become targets

_For any_ goal text whose extraction yields skills below THRESHOLD, the fixed
`student_signup_submit` SHALL set `skills_to_learn` to only the skills whose
confidence meets THRESHOLD, so ambiguous goals no longer over-produce learning
targets.

**Validates: Requirements 2.4**

Property 3: Bug Condition - Cache invalidates on prompt/taxonomy change and stores only validated content

_For any_ prompt or taxonomy change, the fixed `_cache_key` SHALL incorporate a
version and taxonomy-signature component so stale entries are not returned, and
`_write_cache` SHALL be called only after the response validates against its
schema.

**Validates: Requirements 2.5, 2.6**

Property 4: Bug Condition - Fenced-but-valid JSON is parsed, not dropped to fallback

_For any_ LLM response that is valid skill JSON wrapped in markdown code fences,
the fixed `extract_skills` SHALL strip the fences and parse the JSON successfully
rather than falling back, and SHALL clearly log/signal when the keyword fallback
is actually used.

**Validates: Requirements 2.7, 2.8**

Property 5: Preservation - Non-buggy inputs unchanged

_For any_ input where the bug condition does NOT hold (valid mentor scores,
high-confidence goals, unchanged prompt/taxonomy, bare-JSON responses, and
LLM-unavailable paths), the fixed pipeline SHALL produce the same result as the
original pipeline.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

#### Change 1 — Validate posted mentor/student scores through `SkillScores`

**File**: `app/routers/pages.py`
**Functions**: `mentor_signup_submit`, `student_signup_submit`

Replace the raw comprehension in both handlers:

```python
# before
if posted:
    scores = {k: float(v) for k, v in posted.items()}
```

with a small helper that coerces values defensively and routes through the
schema, so unknown ids drop, values clamp/round, and non-numeric entries are
skipped instead of raising:

```python
def _validated_scores(posted: dict) -> dict[str, float]:
    """Coerce posted skill scores and run them through SkillScores.

    Non-numeric values are skipped (not raised); unknown ids are dropped and
    valid values clamped to [0.0, 1.0] and rounded by SkillScores.
    """
    from app.schemas.ai import SkillScores

    numeric: dict[str, float] = {}
    for k, v in posted.items():
        try:
            numeric[k] = float(v)
        except (TypeError, ValueError):
            continue  # malformed entry ignored (2.3)
    return SkillScores(skills=numeric).skills
```

```python
# after (both handlers)
if posted:
    scores = _validated_scores(posted)
```

This makes the posted-scores path behave exactly like `extract_skills`, which
already returns a `SkillScores`-cleaned dict. Satisfies 2.1, 2.2, 2.3; preserves
3.1 (valid ids produce the same cleaned values) and 3.2.

#### Change 2 — Threshold goal skills before they become learning targets

**File**: `app/routers/pages.py`
**Function**: `student_signup_submit`

`extract_skills` already returns confidences. Filter by a threshold instead of
taking every key:

```python
GOAL_SKILL_THRESHOLD = 0.4

goal_skills = extract_skills(goal_text, db)
skills_to_learn = [
    skill_id
    for skill_id, confidence in goal_skills.items()
    if confidence >= GOAL_SKILL_THRESHOLD
]
# ...
skills_to_learn=skills_to_learn,
```

**Threshold choice — 0.4, justified.** The extraction rubric in
`SKILL_EXTRACTION_SYSTEM` maps `0.2` to "mentioned or light exposure" and `0.4`
to "coursework or one small project". For a *learning target* we want a signal
that the goal genuinely implies the skill, not an incidental mention. `0.4` is
the first rubric rung that reflects real intent, and it aligns with the existing
`>= 0.5` "shared skill" cut used in `_run_matching` (0.4 is slightly more lenient
because a goal is aspirational rather than demonstrated). The fallback keyword
extractor floors at `0.3` for a single mention, so `0.4` also correctly excludes
a one-off keyword hit while keeping anything mentioned repeatedly.

This is the minimal goal-appropriate change: it reuses the existing extractor and
confidence values rather than introducing a second goal-specific extraction path,
and it only affects `skills_to_learn`. Resume-based `skill_scores` and experience
level are untouched (3.3). Satisfies 2.4; preserves 3.7 for goals that still yield
`>= 0.4` skills.

#### Change 3 — Version the cache key and validate before writing

**File**: `app/services/llm.py`
**Functions**: `_cache_key`, `_write_cache`, call sites in `extract_skills` /
`rerank_and_explain`

Add a version constant and a taxonomy signature, and fold both into the key:

```python
CACHE_VERSION = "v2"

def _taxonomy_signature() -> str:
    from app.services.skills import load_taxonomy
    ids = ",".join(sorted(load_taxonomy().keys()))
    return hashlib.sha256(ids.encode()).hexdigest()[:12]

def _cache_key(system: str, prompt: str) -> str:
    material = f"{CACHE_VERSION}\x00{_taxonomy_signature()}\x00{system}\x00{prompt}"
    return hashlib.sha256(material.encode()).hexdigest()
```

`_write_cache` stays store-only but is now called strictly *after* validation
(it already is, in both public functions — the key fix is to never move the
`_write_cache` call before `SkillScores.model_validate` / `MatchExplanations`
validation). To make the contract explicit and satisfy 2.6, `_write_cache` keeps
its single responsibility and the call sites remain post-validation:

```python
validated = SkillScores.model_validate(_loads_tolerant(raw))  # change 4
_write_cache(db, key, raw)   # only reached when validation succeeded
return validated.skills
```

The null-byte separators prevent `system`/`prompt` boundary collisions. Bumping
`CACHE_VERSION` or changing the taxonomy now changes every key. Satisfies 2.5,
2.6; preserves 3.5 (unchanged prompt + unchanged taxonomy + unchanged version =
same key = cache hit).

#### Change 4 — Tolerant JSON parsing with a clear fallback signal

**File**: `app/services/llm.py`
**Functions**: `extract_skills`, `rerank_and_explain` (plus a shared helper)

Add a fence-stripping helper and use it everywhere a raw LLM string is parsed:

```python
import re

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

def _loads_tolerant(raw: str):
    """json.loads after stripping an optional surrounding markdown code fence."""
    match = _FENCE_RE.match(raw)
    candidate = match.group(1) if match else raw
    return json.loads(candidate)
```

Replace both `json.loads(raw)` call sites with `_loads_tolerant(raw)`. A bare
object has no fence to strip, so `candidate is raw` and parsing is identical to
before (3.4). A fenced-but-valid payload now parses instead of dropping to
fallback (2.7).

For 2.8, upgrade the fallback log from `info` to `warning` and make it explicit
that results came from the weaker path:

```python
logger.warning("extract_skills: LLM extraction unavailable — using keyword fallback")
```

and similarly in `rerank_and_explain`. This distinguishes a successful LLM
extraction (`info` latency log) from a degraded run (`warning` fallback log).
Preserves 3.6 (fallback still runs and returns keyword scores on true
unavailability).

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate each defect on the
*unfixed* code, then verify the fix works and that non-buggy inputs are
unchanged. All tests use `pytest`, matching the existing `tests/` suite
(`test_matching.py`, `test_llm_fallback.py`, `test_skills.py`, `test_flow_api.py`).

### Exploratory Bug Condition Checking

**Goal**: Reproduce each defect before implementing the fix to confirm the root
cause analysis.

**Test Plan**: Drive the two signup handlers and the two `llm.py` functions with
bug-condition inputs and assert the current broken outcome.

**Test Cases**:
1. **Mentor unknown/out-of-range** — POST mentor signup with
   `{"quantum_telepathy": 0.9, "python": 1.7}`; observe the unknown id and `1.7`
   persisted (will fail after fix — now cleaned). (1.1, 1.2)
2. **Mentor non-numeric** — POST with `{"python": "expert"}`; observe a 500 from
   `float()` (will fail after fix — now ignored, 200). (1.3)
3. **Goal over-extraction** — submit a vague goal that yields only `0.2`
   confidences; observe `skills_to_learn` non-empty (will fail after fix — now
   empty). (1.4)
4. **Stale cache** — cache a response, reword the prompt constant, observe the
   same key / stale hit (will fail after fix — key changes). (1.5)
5. **Fenced JSON** — stub the client to return fenced valid JSON; observe
   fallback used (will fail after fix — now parsed). (1.7)

**Expected Counterexamples**: unknown ids and `1.7` in stored scores; `ValueError`
500 on non-numeric; low-confidence skills in `skills_to_learn`; identical cache
key after prompt change; keyword scores where LLM JSON should have been used.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed function
produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT expectedBehavior(result)
END FOR
```

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed function
produces the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation
because it generates many inputs across the domain, catches edge cases unit tests
miss, and gives strong guarantees that non-buggy behavior is unchanged.

**Test Plan**: Capture current behavior for valid mentor scores, high-confidence
goals, bare-JSON responses, unchanged-prompt cache hits, and LLM-off runs on the
*unfixed* code, then assert the fixed code matches.

**Test Cases**:
1. **Valid mentor scores** — posted known ids with in-range values persist the
   same cleaned dict before and after. (3.1)
2. **Resume extraction** — omitting posted scores still runs `extract_skills` and
   persists its scores for mentor and student. (3.2, 3.3)
3. **Bare JSON** — `_loads_tolerant` on an unfenced object equals `json.loads`.
   (3.4)
4. **Cache hit** — identical system+prompt+taxonomy+version returns the cached
   row. (3.5)
5. **LLM off** — `LLM_MODE=off` still returns `fallback_extract` scores. (3.6)

### Unit Tests

- `_validated_scores`: unknown ids dropped, `1.7` → `1.0`, `-0.2` → `0.0`,
  rounding to 2 decimals, `"expert"` skipped without raising. (2.1, 2.2, 2.3)
- Goal threshold filter: a confidence map with mixed values keeps only
  `>= 0.4`; all-low map yields `[]`. (2.4)
- `_cache_key`: changing `CACHE_VERSION`, the prompt, or the taxonomy ids each
  changes the key; identical inputs give identical keys. (2.5, 3.5)
- `_loads_tolerant`: fenced ` ```json ... ``` `, fenced ` ``` ... ``` `, and bare
  object all parse to the same dict; non-JSON still raises. (2.7, 3.4)
- Fallback logging: assert a `warning`-level record is emitted when the fallback
  path runs. (2.8)

### Property-Based Tests

- Generate random `{id: value}` maps (mix of known/unknown ids, in/out-of-range,
  and non-numeric values) and assert `_validated_scores` output keys are all in
  the taxonomy, all values are within `[0.0, 1.0]`, and no exception is raised.
  (Property 1)
- Generate random confidence maps and assert every id in `skills_to_learn` has
  confidence `>= 0.4` and every excluded id is `< 0.4`. (Property 2)
- Generate random valid skill JSON, wrap half in fences, and assert
  `_loads_tolerant` recovers the same object in both forms. (Property 4)

### Integration Tests

- Full mentor signup POST → DB `MentorProfile.skill_scores` contains only
  cleaned, in-range taxonomy ids. (2.1–2.3)
- Full student signup POST with a vague goal → `StudentRequest.skills_to_learn`
  excludes low-confidence skills while `skill_scores` (resume) is unchanged. (2.4,
  3.3)
- Full student signup with a well-supported goal → matches are still produced and
  ranked as before. (3.7)
- Cached-mode extraction with a fenced cached entry → parsed and validated rather
  than fallen back. (2.7)
