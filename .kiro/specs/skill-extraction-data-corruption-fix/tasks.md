# Implementation Plan

## Overview

This plan fixes four confirmed defects in Sprout's AI skill-extraction and match-rerank
pipeline using the exploratory bugfix methodology: reproduce each defect on the unfixed
code first, apply each minimal fix with its unit/property/integration tests, then confirm
non-buggy behavior is preserved. The four fixes are: (1) validate posted mentor/student
scores through `SkillScores` in `app/routers/pages.py`; (2) threshold goal skills at `0.4`
before they become learning targets; (3) version the LLM cache key with `CACHE_VERSION` +
taxonomy signature and keep writes strictly post-validation in `app/services/llm.py`; and
(4) tolerant fenced-JSON parsing with a clear fallback warning in `app/services/llm.py`.

## Task Dependency Graph

- Task 1 (bug reproduction tests) and Task 2 (preservation baseline tests) are
  independent and come first; both run against the UNFIXED code.
- Tasks 3, 4, 5, 6 (the four fixes) each depend on Tasks 1 and 2 being in place, but are
  independent of one another and may be implemented in any order.
- Task 7 (verify bug tests pass) depends on Tasks 1, 3, 4, 5, 6.
- Task 8 (verify preservation tests pass) depends on Tasks 2, 3, 4, 5, 6.
- Task 9 (full suite + build) depends on all prior tasks (7 and 8 complete).

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "dependsOn": [] },
    { "wave": 2, "tasks": ["3", "4", "5", "6"], "dependsOn": ["1", "2"] },
    { "wave": 3, "tasks": ["7", "8"], "dependsOn": ["3", "4", "5", "6"] },
    { "wave": 4, "tasks": ["9"], "dependsOn": ["7", "8"] }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration tests (BEFORE implementing any fix)
  - **Property 1: Bug Condition** - Corrupted/Hallucinated Data Reproduction
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected post-fix behavior - they will validate the fix when they pass after implementation
  - **GOAL**: Surface the counterexamples from the design's "Exploratory Bug Condition Checking" section
  - **Scoped PBT Approach**: For these deterministic defects, scope each property to the concrete failing case(s) for reproducibility
  - Add tests to `tests/test_flow_api.py` (signup handlers) and `tests/test_llm_fallback.py` (llm.py parsing/cache)
  - Mentor unknown/out-of-range (1.1, 1.2): POST mentor signup with `skill_scores_json` = `{"quantum_telepathy": 0.9, "python": 1.7}`; assert the unknown id and `1.7` are persisted verbatim on `MentorProfile.skill_scores` (confirms no `SkillScores` cleaning)
  - Mentor non-numeric (1.3): POST mentor signup with `{"python": "expert"}`; assert the request 500s from the unhandled `float("expert")` `ValueError`
  - Goal over-extraction (1.4): submit a vague student goal ("I want to maybe explore some coding stuff") that yields only `~0.2` confidences; assert `StudentRequest.skills_to_learn` is non-empty (confidence discarded via `list(goal_skills)`)
  - Stale cache (1.5): cache a response via `_cache_key(system, prompt)`, then reword the prompt constant and assert the key is unchanged / the stale entry is still hit
  - Fenced JSON (1.7): stub the client to return valid skill JSON wrapped in ```` ```json ... ``` ````; assert `extract_skills` falls through to `fallback_extract` because strict `json.loads(raw)` raises
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bugs exist)
  - Document the counterexamples found: unknown id + `1.7` in stored scores; `ValueError` 500 on non-numeric; low-confidence skills in `skills_to_learn`; identical cache key after prompt reword; keyword scores where fenced LLM JSON should have been used
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Buggy Inputs Unchanged
  - **IMPORTANT**: Follow observation-first methodology - record behavior on UNFIXED code, then assert it
  - Add tests to `tests/test_flow_api.py`, `tests/test_matching.py`, and `tests/test_llm_fallback.py`
  - Valid mentor scores (3.1): observe that posting known taxonomy ids with in-range confidences persists a specific cleaned dict on `MentorProfile.skill_scores`; capture that exact dict as the baseline to preserve
  - Resume extraction (3.2, 3.3): observe that omitting posted scores still runs `extract_skills` on resume text and persists its `skill_scores` + experience level for both mentor and student; capture the baseline values
  - Bare JSON (3.4): observe that a bare `{"skills": {"python": 0.8}}` (no fences) parses and validates; capture the parsed/validated result
  - Cache hit (3.5): observe that identical `system + prompt` (unchanged taxonomy) returns the cached row as a hit; capture the hit behavior
  - LLM off (3.6): observe that `LLM_MODE=off` returns `fallback_extract` keyword scores; capture the returned scores
  - Well-supported goal (3.7): observe that a goal yielding `>= 0.4` skills still ranks mentors and produces matches; capture the match output
  - Property-based: generate random valid `{known_id: in_range_value}` maps and assert current behavior persists them cleaned (baseline for Property 5)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix 1 - Validate posted mentor/student scores through `SkillScores`

  - [x] 3.1 Add `_validated_scores` helper and use it in both signup handlers
    - In `app/routers/pages.py` add `_validated_scores(posted: dict) -> dict[str, float]` that coerces each value with `float()` inside a `try/except (TypeError, ValueError)` (skipping malformed entries) and returns `SkillScores(skills=numeric).skills`
    - Replace the raw `scores = {k: float(v) for k, v in posted.items()}` comprehension with `scores = _validated_scores(posted)` in the posted-scores branch of BOTH `mentor_signup_submit` and `student_signup_submit`
    - Unknown ids drop, values clamp to `[0.0, 1.0]` and round to 2 decimals via `SkillScores`; non-numeric entries are skipped without raising
    - _Design: Fix Implementation Change 1_
    - _Bug_Condition: isBugCondition_mentorScores(posted) — unknown id, out-of-range, or non-numeric value_
    - _Expected_Behavior: stored scores all in taxonomy, all in [0.0, 1.0], no unhandled error (Property 1)_
    - _Preservation: valid posted ids produce the same cleaned values (3.1); resume path unaffected (3.2)_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.2 Unit + property tests for `_validated_scores`
    - Unit: unknown ids dropped; `1.7` → `1.0`; `-0.2` → `0.0`; rounding to 2 decimals; `"expert"` skipped without raising (add to `tests/test_skills.py` or `tests/test_flow_api.py`)
    - Property-based: generate random `{id: value}` maps mixing known/unknown ids, in/out-of-range, and non-numeric values; assert output keys are all in the taxonomy, all values within `[0.0, 1.0]`, and no exception raised
    - Integration: full mentor signup POST → `MentorProfile.skill_scores` contains only cleaned, in-range taxonomy ids
    - _Design: Correctness Property 1; Unit Tests; Property-Based Tests; Integration Tests_
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 4. Fix 2 - Threshold goal skills before they become learning targets

  - [x] 4.1 Add `GOAL_SKILL_THRESHOLD = 0.4` and filter goal extraction
    - In `app/routers/pages.py` (`student_signup_submit`) add module-level `GOAL_SKILL_THRESHOLD = 0.4`
    - Replace `skills_to_learn = list(goal_skills)` with a comprehension keeping only `skill_id` where `confidence >= GOAL_SKILL_THRESHOLD` from `goal_skills = extract_skills(goal_text, db)`
    - Only `skills_to_learn` changes; resume-based `skill_scores` and experience level are untouched
    - _Design: Fix Implementation Change 2 (threshold 0.4 justified)_
    - _Bug_Condition: isBugCondition_goalSkills(goal_text) — extraction yields skill with confidence < 0.4_
    - _Expected_Behavior: every id in skills_to_learn has confidence >= 0.4 (Property 2)_
    - _Preservation: resume skill_scores/experience unchanged (3.3); well-supported goals still match (3.7)_
    - _Requirements: 2.4_

  - [x] 4.2 Unit + property + integration tests for the goal threshold
    - Unit: a mixed confidence map keeps only `>= 0.4`; an all-low map yields `[]`
    - Property-based: generate random confidence maps; assert every id in `skills_to_learn` has confidence `>= 0.4` and every excluded id is `< 0.4`
    - Integration: full student signup POST with a vague goal → `StudentRequest.skills_to_learn` excludes low-confidence skills while resume `skill_scores` is unchanged
    - _Design: Correctness Property 2; Unit Tests; Property-Based Tests; Integration Tests_
    - _Requirements: 2.4, 3.3_

- [x] 5. Fix 3 - Version the cache key and validate before writing

  - [x] 5.1 Add `CACHE_VERSION` + `_taxonomy_signature()` and fold both into `_cache_key`
    - In `app/services/llm.py` add `CACHE_VERSION = "v2"` and `_taxonomy_signature()` returning a short `sha256` of the sorted taxonomy ids from `load_taxonomy()`
    - Rewrite `_cache_key(system, prompt)` to hash `f"{CACHE_VERSION}\x00{_taxonomy_signature()}\x00{system}\x00{prompt}"` (null-byte separators prevent boundary collisions)
    - Keep `_write_cache` store-only and ensure both call sites in `extract_skills` and `rerank_and_explain` call `_write_cache` strictly AFTER schema validation (`SkillScores.model_validate` / `MatchExplanations.model_validate`)
    - _Design: Fix Implementation Change 3_
    - _Bug_Condition: isBugCondition_cache(system, prompt, taxonomy_version) — key ignores version/taxonomy_
    - _Expected_Behavior: _cache_key depends on version + taxonomy; _write_cache stores only validated content (Property 3)_
    - _Preservation: unchanged prompt + taxonomy + version = same key = cache hit (3.5)_
    - _Requirements: 2.5, 2.6_

  - [x] 5.2 Unit tests for versioned cache key
    - Changing `CACHE_VERSION`, the prompt, or the taxonomy ids each changes the key; identical inputs give identical keys
    - Assert `_write_cache` is only reached after validation succeeds (no raw pre-validation write)
    - _Design: Correctness Property 3; Unit Tests_
    - _Requirements: 2.5, 2.6, 3.5_

- [x] 6. Fix 4 - Tolerant JSON parsing with a clear fallback signal

  - [x] 6.1 Add `_loads_tolerant` helper and upgrade the fallback log
    - In `app/services/llm.py` add `_FENCE_RE` and `_loads_tolerant(raw)` that strips an optional surrounding markdown code fence (```` ```json ... ``` ```` or ```` ``` ... ``` ````) then calls `json.loads` on the inner content (bare objects pass through unchanged)
    - Replace both `json.loads(raw)` call sites (in `extract_skills` and `rerank_and_explain`) with `_loads_tolerant(raw)`
    - Upgrade the fallback log from `logger.info` to `logger.warning` in both functions, making it explicit that results came from the weaker keyword path
    - _Design: Fix Implementation Change 4_
    - _Bug_Condition: isBugCondition_fencedJson(raw) — valid skill JSON wrapped in fences_
    - _Expected_Behavior: fences stripped and JSON parsed instead of dropping to fallback; fallback clearly signaled (Property 4)_
    - _Preservation: bare JSON parses exactly as before (3.4); fallback still runs on true unavailability (3.6)_
    - _Requirements: 2.7, 2.8_

  - [x] 6.2 Unit + property tests for tolerant parsing and fallback signal
    - Unit: fenced ```` ```json ... ``` ````, fenced ```` ``` ... ``` ````, and a bare object all parse to the same dict; non-JSON still raises
    - Unit: assert a `warning`-level record is emitted when the fallback path runs (not `info`)
    - Property-based: generate random valid skill JSON, wrap half in fences, and assert `_loads_tolerant` recovers the same object in both forms
    - Integration: cached-mode extraction with a fenced cached entry → parsed and validated rather than fallen back
    - _Design: Correctness Property 4; Unit Tests; Property-Based Tests; Integration Tests_
    - _Requirements: 2.7, 2.8, 3.4_

- [x] 7. Verify bug condition exploration tests now pass
  - **Property 1: Expected Behavior** - Corrupted/Hallucinated Data Eliminated
  - **IMPORTANT**: Re-run the SAME tests from task 1 - do NOT write new tests
  - The tests from task 1 encode the expected behavior across all four defects
  - Run the bug condition exploration tests from task 1 against the fixed code
  - **EXPECTED OUTCOME**: Tests PASS (mentor scores cleaned; non-numeric ignored with 200; low-confidence goal skills excluded; cache key changes on prompt/taxonomy change; fenced JSON parsed instead of fallback)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 8. Verify preservation tests still pass
  - **Property 2: Preservation** - Non-Buggy Inputs Unchanged
  - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
  - Run the preservation property tests from task 2 against the fixed code
  - **EXPECTED OUTCOME**: Tests PASS (valid mentor scores, resume extraction, bare JSON, unchanged-prompt cache hit, LLM-off fallback, and well-supported-goal matching all unchanged)
  - Confirm no regressions were introduced by any of the four fixes
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 9. Checkpoint - Run the full test suite and build verification
  - Run the complete `pytest` suite (existing `tests/` plus all new tests) and confirm everything passes
  - Confirm the application imports/builds cleanly (e.g. `python -c "import app.main"` and any Makefile/pyproject build or lint target)
  - Ensure all tests pass; if questions or unexpected failures arise, ask the user before proceeding
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

## Notes

- Tasks 1 and 2 must be run against the UNFIXED code: Task 1 tests MUST FAIL (proving the
  bugs exist) and Task 2 tests MUST PASS (capturing the baseline to preserve). Do not
  "fix" a failing Task 1 test early — its failure is the expected signal.
- Tests follow the existing `pytest` layout in `tests/`: signup-handler flows in
  `test_flow_api.py`, LLM parsing/cache in `test_llm_fallback.py`, pure skill logic in
  `test_skills.py`, and matching in `test_matching.py`.
- Property-based testing is recommended for the fix-checking and preservation properties
  because it exercises many inputs across the domain and surfaces edge cases unit tests miss.
- The threshold value `0.4` (`GOAL_SKILL_THRESHOLD`) and cache version `"v2"`
  (`CACHE_VERSION`) are fixed by the design; do not change them without updating the design.
- The scope is strictly the four confirmed root causes. Secondary issues noted in the
  requirements (fallback double-counting, silent `SkillScores` drops, un-fact-checked
  rerank explanations) are out of scope for this spec.
