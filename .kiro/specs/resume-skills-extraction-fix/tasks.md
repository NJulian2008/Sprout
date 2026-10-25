# Implementation Plan

## Overview

This plan fixes the missing student-side resume skills preview using the bug-condition testing
methodology. Tasks are ordered so the exploratory bug-condition test and preservation tests are
written and run against the UNFIXED code first, then the fix is applied to two files
(`app/templates/student/signup.html` and `app/routers/pages.py`), then the same tests are re-run to
confirm the fix (fix-checking) and no regressions (preservation-checking).

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write and run the bug-condition exploration test (fails on unfixed code) and the preservation tests (pass on unfixed code). Independent of each other.",
      "dependsOn": []
    },
    {
      "wave": 2,
      "tasks": ["3.1", "3.2"],
      "description": "Apply the fix: wire the student template preview (3.1) and make the extract endpoint accept the uploaded file (3.2). Independent of each other.",
      "dependsOn": ["1", "2"]
    },
    {
      "wave": 3,
      "tasks": ["3.3", "3.4"],
      "description": "Re-run the task 1 test (fix-checking, now passes) and the task 2 tests (preservation-checking, still pass).",
      "dependsOn": ["3.1", "3.2"]
    },
    {
      "wave": 4,
      "tasks": ["4"],
      "description": "Checkpoint: run the full pytest suite and confirm everything passes.",
      "dependsOn": ["3.3", "3.4"]
    }
  ]
}
```

- Task 1 and Task 2 are independent and can be written in either order (both run before the fix).
- Task 3.1 and Task 3.2 are independent of each other but both must land before 3.3/3.4.
- Task 3.3 depends on Task 1 and the fix; Task 3.4 depends on Task 2 and the fix.
- Task 4 depends on 3.3 and 3.4.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Student resume preview renders extracted skills
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug (`isBugCondition` holds: a student on `/student/signup` selects a readable resume file but no preview is wired or rendered)
  - **Scoped PBT Approach**: For the deterministic page/endpoint assertions, scope the property to the concrete failing cases below; for the resume-text case, parametrize over a small set of readable TXT payloads known to yield taxonomy skills
  - Add a new test module `tests/test_student_skills_preview.py` using pytest + FastAPI `TestClient` with the in-memory SQLite + `get_session` override fixture pattern from `tests/test_flow_api.py` (force `settings.llm_mode = "off"` for determinism)
  - Test case A (no target element): `GET /student/signup` HTML contains `id="skill-chips-result"` (from Bug Condition: `skillChipsResultElementExists` is false on unfixed code)
  - Test case B (no HTMX trigger): the student resume input carries `hx-post="/student/skills/extract"`, `hx-target="#skill-chips-result"`, `hx-encoding="multipart/form-data"`, and `hx-swap="outerHTML"` (from Bug Condition: `skillsPreviewRequestIssued` is false on unfixed code)
  - Test case C (endpoint ignores file): `POST /student/skills/extract` with a readable multipart resume (e.g. `("resume.txt", b"I know some python and git", "text/plain")`) returns 200 and the rendered `partials/skill_chips.html` fragment containing skill chips and a populated hidden `skill_scores_json` (NOT `{}`) — on unfixed code the handler reads `text`, not the file, so the fragment comes back empty (`uploadedFileProcessedByExtractEndpoint` is false)
  - The assertions above match the Expected Behavior Properties from design (Property 1)
  - Run the test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g. "`#skill-chips-result` absent from `/student/signup`", "resume input has no `hx-post`", "multipart resume to `/student/skills/extract` yields an empty `skill_scores_json` fragment")
  - Mark task complete when the test is written, run, and the failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-preview behavior is unchanged
  - **IMPORTANT**: Follow observation-first methodology - run the UNFIXED code for inputs where `isBugCondition` is false, record the actual outputs, then assert those outputs
  - Add preservation tests to `tests/test_student_skills_preview.py` (or alongside the existing suite), reusing the in-memory `TestClient` fixture
  - Observe (mentor extract, Requirement 3.1): `POST /mentor/skills/extract` with `text` renders chips into `#skill-chips-result`; record the fragment contains `id="skill-chips-result"` and chips for a known-skill text
  - Observe (student submission, Requirement 3.2): `POST /student/signup` with a readable resume file (mirror `test_one_flow_end_to_end`) returns 303 to `/student/matches` and persists `StudentRequest.skill_scores`, `resume_text`, `experience_score`, and `experience_level`
  - Observe (`skill_scores_json` precedence, Requirement 3.3): the `partials/skill_chips.html` fragment still emits a hidden input named `skill_scores_json`; record the submission handler's current treatment of a non-empty `skill_scores_json` so the test asserts it is unchanged
  - Observe (resume reader, Requirement 3.4): exercise `_resume_text_from_upload` across readable TXT/PDF/DOCX and the empty/unreadable cases; record that it still returns text for readable inputs and still raises `HTTPException(422)` for empty/unreadable/unsupported inputs
  - Write property-based tests capturing the observed behavior patterns (generate varied readable TXT payloads for mentor extract and submission; generate empty/unreadable payloads for the direct `_resume_text_from_upload` raise-behavior)
  - Property-based testing generates many test cases for stronger guarantees (recommended for preservation)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for missing student-side resume skills preview wiring

  - [x] 3.1 Wire the student sign-up template preview
    - In `app/templates/student/signup.html`, in the "2. Resume" card, add HTMX attributes to the resume file input: `hx-post="/student/skills/extract"`, `hx-trigger="change"`, `hx-encoding="multipart/form-data"`, `hx-target="#skill-chips-result"`, `hx-swap="outerHTML"`, keeping `name="resume_file"`, `required`, and the existing `accept` list
    - Include `partials/skill_chips.html` after the input, seeding empty-state context defaults so it renders on first load: `{% set skill_scores = {} %}{% set experience_level = "intermediate" %}{% set experience_score = 0 %}{% set field_name = "skill_scores_json" %}` then `{% include "partials/skill_chips.html" %}`
    - This introduces the `#skill-chips-result` element and the hidden `skill_scores_json` field, mirroring the mentor template
    - _Bug_Condition: isBugCondition(input) where input.on_student_signup_page AND input.resume_file IS NOT NULL AND input.resume_is_readable AND NOT skillsPreviewRequestIssued AND NOT skillChipsResultElementExists_
    - _Expected_Behavior: expectedBehavior(result) from design Property 1 — a multipart HTMX request targets `#skill-chips-result` and swaps in the `partials/skill_chips.html` fragment_
    - _Preservation: Preservation Requirements from design (3.1 mentor extract, 3.2 student submission, 3.3 skill_scores_json precedence, 3.4 resume reader)_
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Make the student extract endpoint accept and process the uploaded file
    - In `app/routers/pages.py`, change `student_skills_extract` (handler for `POST /student/skills/extract`) to accept `resume_file: UploadFile = File(...)` instead of `text: str = Form("")` (`File`/`UploadFile` already imported)
    - Call `_resume_text_from_upload(resume_file)` inside a `try/except HTTPException`; on `HTTPException` (empty/unreadable/unsupported) fall back to empty resume text so skills resolve to `{}`
    - Run `extract_skills(resume_text, db)` when the text is non-empty, else use `{}`
    - Return the `partials/skill_chips.html` fragment with the same context keys the mentor endpoint uses: `skill_scores`, `experience_level`, `experience_score`, `taxonomy`, and `field_name="skill_scores_json"`
    - Leave `_resume_text_from_upload` itself unchanged so it still raises for direct callers (Requirement 3.4)
    - _Bug_Condition: isBugCondition(input) — endpoint previously read `text` so `uploadedFileProcessedByExtractEndpoint` was false_
    - _Expected_Behavior: expectedBehavior(result) from design Property 1 — extract text via `_resume_text_from_upload`, run `extract_skills`, return the fragment; unreadable/empty renders with `skill_scores == {}` rather than erroring_
    - _Preservation: Preservation Requirements from design (3.4 unreadable/empty handling in `_resume_text_from_upload` unchanged; mentor/submission handlers untouched)_
    - _Requirements: 2.3, 2.4_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Student resume preview renders extracted skills
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior; when it passes it confirms the expected behavior is satisfied
    - Run the bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms the bug is fixed — `#skill-chips-result` present, resume input carries HTMX attributes, and a multipart resume yields a populated `skill_scores_json` fragment)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-preview behavior is unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run the preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in mentor extract, student submission, `skill_scores_json` precedence, or `_resume_text_from_upload`)
    - Confirm all tests still pass after the fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full suite (`pytest`) and confirm the new preview tests plus the existing tests under `tests/` all pass
  - Ensure all tests pass; ask the user if questions arise

## Notes

- Tests use pytest + FastAPI `TestClient` with the in-memory SQLite engine and `get_session`
  override fixture established in `tests/test_flow_api.py`; set `settings.llm_mode = "off"` for
  deterministic skill extraction (`fallback_extract`).
- The fix is confined to `app/templates/student/signup.html` and `student_skills_extract` in
  `app/routers/pages.py`. `_resume_text_from_upload`, `mentor_skills_extract`,
  `student_signup_submit`, and all service-layer code remain unchanged.
- The task 1 exploration test is expected to FAIL on unfixed code (confirming the bug) and must PASS
  unchanged after the fix (fix-checking). Do not edit it between task 1 and task 3.3.
- The task 2 preservation tests must PASS on unfixed code (baseline) and remain passing after the fix
  (preservation-checking). Do not edit them between task 2 and task 3.4.
