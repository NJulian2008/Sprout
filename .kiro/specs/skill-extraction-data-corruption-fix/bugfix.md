# Bugfix Requirements Document

## Introduction

Sprout's AI skill-extraction and match-rerank pipeline is writing corrupted and hallucinated data into student requests and mentor profiles, which in turn drives spurious matches and untrustworthy explanations. Four confirmed root causes were found by reading the code:

1. The mentor signup handler stores posted `skill_scores_json` directly on `MentorProfile.skill_scores` without passing it through the `SkillScores` schema, so hallucinated/unknown skill ids and out-of-range confidences are persisted verbatim instead of being dropped or clamped like every other path.
2. The student signup handler runs the resume-oriented extractor on short goal text and turns every extracted key into a learning target regardless of confidence, so ambiguous goals over-produce skills and inflate the match candidate pool.
3. The LLM cache key is `sha256(system + prompt)` with no prompt/taxonomy/model version component, and the cache stores the raw unvalidated LLM string, so changing the prompt or taxonomy silently serves stale (and possibly invalid) cached responses.
4. The extraction path parses the LLM response with a strict `json.loads` and swallows any parse error into the weaker keyword fallback, so a model that wraps JSON in markdown fences silently degrades extraction quality with no clear signal.

This spec scopes the fix to these four confirmed root causes. The corrupting writes happen in `app/routers/pages.py` (`mentor_signup_submit`, `student_signup_submit`) and `app/services/llm.py` (`_cache_key`, `_write_cache`, `extract_skills`, `CopilotAdapter`), with supporting validation in `app/schemas/ai.py` and the extraction prompt in `app/services/prompts.py`. Secondary issues (fallback double-counting, silent `SkillScores` drops/clamps, un-fact-checked rerank explanations) are noted as lower priority and are out of primary scope.

## Bug Analysis

### Current Behavior (Defect)

What currently happens when the bugs are triggered:

1.1 WHEN a mentor signup submits `skill_scores_json` containing a skill id that is not in the taxonomy THEN the system parses it with `{k: float(v) for k, v in posted.items()}` and persists the unknown id on `MentorProfile.skill_scores` without dropping it

1.2 WHEN a mentor signup submits `skill_scores_json` containing a confidence outside the 0.0–1.0 range THEN the system persists the out-of-range value on `MentorProfile.skill_scores` without clamping or rounding it

1.3 WHEN a mentor signup submits malformed numeric values in `skill_scores_json` (non-numeric confidences) THEN the system raises an unhandled error from `float(v)` instead of rejecting the entry cleanly

1.4 WHEN a student submits short or ambiguous goal text THEN the system runs `extract_skills` (the resume-oriented extractor with the `SKILL_EXTRACTION` prompt) on it and sets `skills_to_learn` to every extracted key via `list(goal_skills)`, discarding confidence, so weakly-supported and spurious skills become learning targets

1.5 WHEN the skill-extraction prompt or the skills taxonomy changes after a response has been cached THEN the system continues to return the stale cached response because `_cache_key` is `sha256(system + prompt)` with no version/taxonomy component

1.6 WHEN an invalid or unvalidated LLM string is produced THEN the system writes that raw string into the cache via `_write_cache`, so later reads can return content that fails validation

1.7 WHEN the LLM returns valid skill JSON wrapped in markdown code fences (e.g. ```json ... ```) THEN the strict `json.loads(raw)` in `extract_skills` raises, the error is swallowed, and the system silently falls through to the weaker `fallback_extract`

1.8 WHEN the system falls back from LLM extraction to keyword extraction THEN the degradation is recorded only as a generic info log, giving no clear signal that results came from the weaker path

### Expected Behavior (Correct)

What should happen instead:

2.1 WHEN a mentor signup submits `skill_scores_json` containing a skill id that is not in the taxonomy THEN the system SHALL route the posted scores through `SkillScores` validation so the unknown id is dropped before persistence

2.2 WHEN a mentor signup submits `skill_scores_json` containing a confidence outside the 0.0–1.0 range THEN the system SHALL clamp the value to [0.0, 1.0] and round to 2 decimal places via `SkillScores` before persistence

2.3 WHEN a mentor signup submits malformed numeric values in `skill_scores_json` THEN the system SHALL reject or ignore the malformed entries without raising an unhandled error, consistent with the other skill-ingestion paths

2.4 WHEN a student submits goal text THEN the system SHALL set `skills_to_learn` to only the meaningfully-supported skills (e.g. extracted keys whose confidence meets a defined threshold and/or produced by a goal-appropriate extraction), so ambiguous goals no longer over-produce learning targets

2.5 WHEN the skill-extraction prompt or the skills taxonomy changes THEN the system SHALL compute a cache key that includes a version/taxonomy component so stale cached entries are no longer returned for the changed inputs

2.6 WHEN a response is about to be cached THEN the system SHALL validate it against its schema first and SHALL only store validated content

2.7 WHEN the LLM returns valid skill JSON wrapped in markdown code fences THEN the system SHALL tolerantly extract the JSON (stripping code fences) before parsing so a well-formed response is used instead of falling back

2.8 WHEN the system falls back from LLM extraction to keyword extraction THEN the system SHALL clearly log and signal that the fallback path was used, distinguishing it from a successful LLM extraction

### Unchanged Behavior (Regression Prevention)

Existing behavior that must be preserved:

3.1 WHEN a mentor signup submits `skill_scores_json` containing only valid taxonomy ids with in-range confidences THEN the system SHALL CONTINUE TO persist those scores on `MentorProfile.skill_scores` (now via `SkillScores`, producing the same cleaned values)

3.2 WHEN a mentor or student signup omits posted scores and relies on resume-based extraction THEN the system SHALL CONTINUE TO call `extract_skills` on the resume text and persist the resulting scores

3.3 WHEN a resume is submitted for skill extraction THEN the system SHALL CONTINUE TO produce the same resume-based `skill_scores` and experience level as before (the goal-text change applies only to `skills_to_learn`)

3.4 WHEN the LLM returns a bare JSON object with no markdown fences THEN the system SHALL CONTINUE TO parse and validate it exactly as before

3.5 WHEN a cached response exists for an unchanged prompt and unchanged taxonomy version THEN the system SHALL CONTINUE TO serve it as a cache hit

3.6 WHEN the LLM is unavailable (LLM_MODE=off, timeout, or cache miss) THEN the system SHALL CONTINUE TO fall back to `fallback_extract` and return keyword-based scores

3.7 WHEN matching runs for a student whose goal yields well-supported skills THEN the system SHALL CONTINUE TO rank mentors and produce matches as before

## Bug Condition Analysis

### Bug Condition Functions

```pascal
// 1 — Mentor signup validation bypass
FUNCTION isBugCondition_mentorScores(posted)
  INPUT: posted of type map<string, any>   // parsed skill_scores_json
  OUTPUT: boolean
  RETURN EXISTS k IN posted WHERE (k NOT IN taxonomy)
      OR EXISTS v IN posted.values WHERE (v < 0.0 OR v > 1.0 OR NOT isNumeric(v))
END FUNCTION

// 2 — Goal-text over-extraction
FUNCTION isBugCondition_goalSkills(goal_text)
  INPUT: goal_text of type string
  OUTPUT: boolean
  // short/ambiguous goal text that yields weakly-supported extracted skills
  RETURN EXISTS s IN extract_skills(goal_text) WHERE confidence(s) < THRESHOLD
END FUNCTION

// 3 — Stale cache
FUNCTION isBugCondition_cache(system, prompt, taxonomy_version)
  INPUT: system, prompt of type string; taxonomy_version of type string
  OUTPUT: boolean
  // key does not change when prompt/taxonomy version changes
  RETURN cache_key_ignores(taxonomy_version)
END FUNCTION

// 4 — Fenced JSON forced into fallback
FUNCTION isBugCondition_fencedJson(raw)
  INPUT: raw of type string   // LLM response
  OUTPUT: boolean
  RETURN isValidSkillJson(strip_code_fences(raw)) AND NOT isValidSkillJson(raw)
END FUNCTION
```

### Properties (Fix Checking)

```pascal
// Property 1: mentor scores are validated before persistence
FOR ALL posted WHERE isBugCondition_mentorScores(posted) DO
  stored ← mentor_signup_submit'(posted).skill_scores
  ASSERT (FOR ALL k IN stored: k IN taxonomy)
     AND (FOR ALL v IN stored.values: 0.0 <= v <= 1.0)
     AND no_unhandled_error(mentor_signup_submit'(posted))
END FOR

// Property 2: only meaningfully-supported goal skills become learning targets
FOR ALL goal_text WHERE isBugCondition_goalSkills(goal_text) DO
  learn ← student_signup_submit'(goal_text).skills_to_learn
  ASSERT FOR ALL s IN learn: confidence(s) >= THRESHOLD
END FOR

// Property 3: cache invalidates when prompt/taxonomy version changes
FOR ALL (system, prompt, taxonomy_version) WHERE isBugCondition_cache(...) DO
  ASSERT _cache_key'(system, prompt) depends on taxonomy_version
  ASSERT _write_cache' stores only validated content
END FOR

// Property 4: fenced-but-valid JSON is used, not dropped to fallback
FOR ALL raw WHERE isBugCondition_fencedJson(raw) DO
  ASSERT extract_skills' parses strip_code_fences(raw) successfully
     AND does NOT use fallback_extract for this input
END FOR
```

### Preservation (Preservation Checking)

```pascal
FOR ALL X WHERE NOT (isBugCondition_mentorScores(X)
                 OR isBugCondition_goalSkills(X)
                 OR isBugCondition_cache(X)
                 OR isBugCondition_fencedJson(X)) DO
  ASSERT F(X) = F'(X)
END FOR
```

**Key definitions:** `F` is the current (unfixed) pipeline; `F'` is the pipeline after the fix. `THRESHOLD` is the goal-skill confidence cutoff to be finalized in design.
