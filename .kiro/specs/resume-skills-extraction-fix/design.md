# Resume Skills Extraction Fix Bugfix Design

## Overview

On the student sign-up page the extracted-skills preview never appears after a student selects a
resume file. The feature was shipped missing the client/server wiring that the mentor sign-up flow
uses successfully: there is no `#skill-chips-result` target element on the student page, no HTMX
trigger on the resume input, and no server endpoint that accepts an uploaded file for preview (the
existing `POST /student/skills/extract` reads a `text` form field, not a file).

The fix mirrors the already-working mentor flow onto the student side. On the template, we include
the `partials/skill_chips.html` fragment (giving the page a `#skill-chips-result` element) and add
HTMX attributes to the resume file input so that choosing a file posts the resume as
`multipart/form-data` to a preview endpoint and swaps the returned fragment into place. On the
server, we change `student_skills_extract` to accept the uploaded file, reuse the existing
`_resume_text_from_upload` text extractor and `extract_skills` pipeline, and return the same
`partials/skill_chips.html` fragment the mentor flow renders. Unreadable or empty resumes resolve to
an empty skills map so the section still renders instead of erroring.

The fix is intentionally minimal and confined to the student-side preview path. The final
submission path (`POST /student/signup`), the mentor extract flow, `skill_scores_json` precedence,
and `_resume_text_from_upload`'s format handling are left unchanged.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a student provides a readable resume
  file on the student sign-up form but no skills preview is requested or rendered, because the page
  has no `#skill-chips-result` target, no HTMX trigger, and the only student extract endpoint reads
  a `text` field rather than an uploaded file.
- **Property (P)**: The desired behavior for the bug condition — selecting a resume file issues a
  multipart HTMX request to a preview endpoint that extracts the resume text, runs skill extraction,
  and swaps the `partials/skill_chips.html` fragment (chips, experience badge, and hidden
  `skill_scores_json`) into `#skill-chips-result`.
- **Preservation**: Existing behavior that must remain unchanged — the mentor "Find my skills"
  extract flow, the student final-submission path at `POST /student/signup`, `skill_scores_json`
  precedence at submission, and the PDF/DOCX/TXT and unreadable/empty handling inside
  `_resume_text_from_upload`.
- **student_skills_extract**: The handler for `POST /student/skills/extract` in
  `app/routers/pages.py`. Today it reads a `text: str = Form("")` field; the fix changes it to
  accept an uploaded resume file.
- **_resume_text_from_upload**: The helper in `app/routers/pages.py` that extracts text from a
  supported resume `UploadFile` (TXT/PDF/DOCX) and raises `HTTPException(422)` for empty or
  unreadable files.
- **extract_skills**: The service (`app/services.llm.extract_skills`) that maps resume text to a
  `{skill_id: confidence}` map.
- **skill_chips.html**: The shared partial (`app/templates/partials/skill_chips.html`) that renders
  skill chips, an experience-level badge, and a hidden `skill_scores_json` input. It expects context
  keys `skill_scores`, `experience_level`, `experience_score`, `taxonomy`, and `field_name`.
- **#skill-chips-result**: The DOM element (the partial's root `<div>`) that the HTMX request targets
  and replaces via `hx-swap="outerHTML"`.
- **skill_scores_json**: The hidden form field emitted by the partial. At final submission a
  non-empty value is used in preference to re-extracting skills from the resume text.

## Bug Details

### Bug Condition

The bug manifests when a student selects a readable resume file (PDF, DOCX, or TXT) on the student
sign-up form and expects to see the inferred-skills preview. The student template is missing the
`#skill-chips-result` element and any HTMX trigger, and the only student extract endpoint
(`student_skills_extract`) reads a `text` form field instead of the uploaded file — so no preview
request is issued and, even if one reached the endpoint, the resume contents would be ignored.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type StudentResumeSelection
    (fields: on_student_signup_page, resume_file, resume_is_readable)
  OUTPUT: boolean

  RETURN input.on_student_signup_page
         AND input.resume_file IS NOT NULL
         AND input.resume_is_readable
         AND NOT skillsPreviewRequestIssued(input)      // no HTMX trigger fires
         AND NOT skillChipsResultElementExists(input)    // #skill-chips-result absent
         AND NOT uploadedFileProcessedByExtractEndpoint(input)  // endpoint reads `text`, not file
END FUNCTION
```

### Examples

- A student fills in goal and specialty, then chooses a readable `resume.pdf`. Expected: skill chips
  and an experience-level badge appear in a `#skill-chips-result` section. Actual: nothing on the
  page changes — no chips, no badge, no error.
- A student chooses a readable `resume.docx`. Expected: a multipart HTMX request renders the skills
  preview. Actual: no client-side request is issued at all.
- A hypothetical request sends a resume file to `POST /student/skills/extract`. Expected: the file
  text is extracted and returned as chips. Actual: the endpoint reads only the `text` form field and
  ignores the file, returning an empty preview.
- Edge case: a student chooses an unreadable or empty resume file. Expected (post-fix): the preview
  section renders with an empty skills map (the "no skills detected yet" state) rather than failing
  to render.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The mentor "Find my skills" control must continue to post to `/mentor/skills/extract`, render
  `partials/skill_chips.html` into `#skill-chips-result`, and show the mentor's extracted skills as
  before. (Requirement 3.1)
- Student final submission at `POST /student/signup` with a readable resume file must continue to
  extract resume text, run skill extraction, persist `StudentRequest.skill_scores`, `resume_text`,
  `experience_score`, and `experience_level`, run matching, and redirect to `/student/matches`.
  (Requirement 3.2)
- Student final submission with a non-empty `skill_scores_json` field must continue to use the posted
  reviewed scores in preference to re-extracting skills from the resume text. (Requirement 3.3)

  Note: the current `student_signup_submit` handler does not yet read `skill_scores_json`; it always
  re-extracts. This design does not change that handler. Requirement 3.3 is treated as a preservation
  constraint — the preview endpoint and template changes must not remove or interfere with the
  `skill_scores_json` field the partial emits, so that submission-side consumption keeps working
  wherever it is (or becomes) wired.
- Server-side resume reading must continue to support PDF, DOCX, and TXT formats and keep the
  existing unreadable/empty-file handling in `_resume_text_from_upload`. (Requirement 3.4)

**Scope:**
All inputs that do NOT involve selecting a resume file for preview on the student sign-up form should
be completely unaffected by this fix. This includes:
- Mentor-side skill extraction and the mentor sign-up flow in general.
- Student final form submission (`POST /student/signup`) and its persistence/matching/redirect path.
- All other resume-reading callers of `_resume_text_from_upload`.

Note: The actual expected correct behavior for the bug condition is defined in the Correctness
Properties section (Property 1). This section focuses on what must NOT change.

## Hypothesized Root Cause

The requirements phase already localized the defect; the root cause is the absence of the
student-side preview wiring that the mentor flow has. Concretely:

1. **Missing target element**: The student template never includes `partials/skill_chips.html`, so
   no `#skill-chips-result` element exists on the page for an HTMX response to swap into.

2. **Missing client-side trigger**: The resume file input has no `hx-post`/`hx-target`/`hx-swap`
   attributes, so selecting a file issues no request and the preview is never fetched.

3. **Endpoint reads the wrong input**: `student_skills_extract` is declared with `text: str =
   Form("")` and calls `extract_skills(text, db)`. It does not declare an `UploadFile`, so an
   uploaded resume is never read — the resume bytes are ignored even if a request reaches it.

4. **No graceful empty/unreadable handling for preview**: `_resume_text_from_upload` raises
   `HTTPException(422)` for empty/unreadable files. A preview endpoint that called it directly would
   return an error instead of an empty-skills fragment, so the section would fail to render for the
   edge case in Requirement 2.4.

## Correctness Properties

Property 1: Bug Condition - Student resume preview renders extracted skills

_For any_ input where the bug condition holds (isBugCondition returns true) — a student on the
sign-up page selects a readable resume file — the fixed system SHALL issue a `multipart/form-data`
HTMX request to the student skills-preview endpoint, extract the resume text via
`_resume_text_from_upload`, run it through `extract_skills`, and return the
`partials/skill_chips.html` fragment (carrying the estimated skills in the hidden `skill_scores_json`
field, plus the experience-level badge) swapped into `#skill-chips-result`. When the resume is
unreadable or yields no text, the fragment SHALL render with an empty skills map rather than failing.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Non-preview behavior is unchanged

_For any_ input where the bug condition does NOT hold (isBugCondition returns false) — the mentor
extract flow, student final submission at `POST /student/signup`, submission-time `skill_scores_json`
precedence, and all other callers of `_resume_text_from_upload` — the fixed code SHALL produce the
same result as the original code, preserving the mentor preview, the student persistence/matching/
redirect path, the reviewed-scores precedence, and the existing PDF/DOCX/TXT and unreadable/empty
handling.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

Assuming our root cause analysis is correct, two files change: the student sign-up template and the
student preview endpoint. No service-layer code changes.

### Changes Required

**File**: `app/templates/student/signup.html`

**Section**: the "2. Resume" card.

**Specific Changes**:
1. **Add HTMX attributes to the resume file input** so selecting a file posts it as multipart to the
   preview endpoint and swaps the response into the target:
   - `hx-post="/student/skills/extract"`
   - `hx-trigger="change"` (fire when a file is chosen)
   - `hx-encoding="multipart/form-data"` (send the file, not just form-encoded values)
   - `hx-target="#skill-chips-result"`
   - `hx-swap="outerHTML"`
   The input keeps `name="resume_file"` so the same field name reaches the endpoint; `required` and
   the `accept` list are preserved.

2. **Include the skill-chips partial** inside the Resume card (after the input), mirroring the mentor
   template, seeding the context defaults so the partial renders its empty state on first load:
   ```jinja
   {% set skill_scores = {} %}{% set experience_level = "intermediate" %}{% set experience_score = 0 %}{% set field_name = "skill_scores_json" %}
   {% include "partials/skill_chips.html" %}
   ```
   This introduces the `#skill-chips-result` element and the hidden `skill_scores_json` field into
   the student form, both of which the fragment response will replace/populate.

**File**: `app/routers/pages.py`

**Function**: `student_skills_extract` (handler for `POST /student/skills/extract`)

**Specific Changes**:
3. **Accept the uploaded file instead of a `text` field.** Change the signature from
   `text: str = Form("")` to `resume_file: UploadFile = File(...)` (import `File`/`UploadFile` are
   already present in the module).

4. **Extract text safely and degrade to empty skills on unreadable/empty input.** Call
   `_resume_text_from_upload(resume_file)` inside a `try/except HTTPException`. On success, run
   `extract_skills(resume_text, db)`; on `HTTPException` (empty/unreadable/unsupported), use an empty
   scores map `{}`. This satisfies Requirement 2.4 (render the fragment rather than error) while
   keeping `_resume_text_from_upload` itself unchanged (Requirement 3.4).

5. **Return the shared fragment unchanged.** Keep rendering `partials/skill_chips.html` with the same
   context keys the mentor endpoint uses: `skill_scores`, `experience_level`, `experience_score`,
   `taxonomy`, and `field_name="skill_scores_json"`. The hidden `skill_scores_json` field is thus
   populated with the estimate, preserving submission-side precedence (Requirement 3.3).

Illustrative post-fix handler (pseudocode-level, final form determined in implementation):
```python
@router.post("/student/skills/extract")
def student_skills_extract(
    request: Request,
    db: Session = Depends(get_session),
    resume_file: UploadFile = File(...),
):
    try:
        resume_text = _resume_text_from_upload(resume_file)
    except HTTPException:
        resume_text = ""
    scores = extract_skills(resume_text, db) if resume_text.strip() else {}
    exp_s = experience_score(scores)
    return render(
        "partials/skill_chips.html",
        {
            "request": request,
            "skill_scores": scores,
            "experience_level": experience_level(exp_s),
            "experience_score": round(exp_s, 2),
            "taxonomy": load_taxonomy(),
            "field_name": "skill_scores_json",
        },
    )
```

**Explicitly unchanged**: `student_signup_submit`, `mentor_skills_extract`, `mentor_signup_submit`,
`_resume_text_from_upload`, and all service-layer code.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate
the bug on unfixed code, then verify the fix works correctly and preserves existing behavior. Tests
live under `tests/` (pytest + FastAPI `TestClient`, consistent with the existing suite such as
`tests/test_flow_api.py` and `tests/test_skills.py`).

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or
refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Request `GET /student/signup` and assert the preview wiring is absent on unfixed code,
and post a resume file to `POST /student/skills/extract` and assert the file is ignored. Run these on
the UNFIXED code to observe the failures predicted by the root-cause analysis.

**Test Cases**:
1. **No target element**: `GET /student/signup` HTML does not contain `id="skill-chips-result"` (will
   fail-to-find on unfixed code).
2. **No HTMX trigger**: the student resume input has no `hx-post`/`hx-target` attributes (absent on
   unfixed code).
3. **Endpoint ignores file**: posting a readable resume file (multipart) to
   `POST /student/skills/extract` returns the empty-skills fragment because the handler reads `text`,
   not the file (will fail on unfixed code — no chips rendered for a real resume).
4. **Edge case**: posting an empty/unreadable file to the endpoint — observe current behavior (on
   unfixed code the file is ignored and an empty fragment returns; post-fix the handler must also
   return the empty fragment, not a 422).

**Expected Counterexamples**:
- `#skill-chips-result` is absent from the student page and no HTMX attributes are present.
- A multipart resume posted to the extract endpoint yields no skills, confirming the handler reads
  the wrong input.
- Possible causes (all confirmed by the requirements phase): missing partial include, missing HTMX
  trigger, endpoint reading a `text` field instead of an `UploadFile`.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the
expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := student_skills_extract_fixed(input.resume_file)
  ASSERT result renders partials/skill_chips.html
  ASSERT result targets/produces #skill-chips-result
  IF input.resume_is_readable AND resume yields text THEN
    ASSERT result.skill_scores == extract_skills(text_of(input.resume_file))
    ASSERT result contains hidden field skill_scores_json
  ELSE
    ASSERT result.skill_scores == {}   // empty, still rendered
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function
produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT mentor_skills_extract_original(input)   == mentor_skills_extract_fixed(input)
  ASSERT student_signup_submit_original(input)   == student_signup_submit_fixed(input)
  ASSERT resume_text_from_upload_original(input) == resume_text_from_upload_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain.
- It catches edge cases that manual unit tests might miss.
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs.

**Test Plan**: Observe behavior on UNFIXED code first for the mentor extract flow, student final
submission, and direct `_resume_text_from_upload` calls across PDF/DOCX/TXT and empty/unreadable
inputs, then write tests capturing that behavior and assert it is unchanged after the fix.

**Test Cases**:
1. **Mentor extract preservation**: Observe that posting text to `/mentor/skills/extract` renders
   chips into `#skill-chips-result` on unfixed code, then verify this is unchanged after the fix.
2. **Student submission preservation**: Observe that `POST /student/signup` with a readable resume
   persists `skill_scores`/`resume_text`/`experience_score`/`experience_level`, runs matching, and
   redirects to `/student/matches`; verify unchanged after the fix.
3. **skill_scores_json precedence preservation**: Verify the submission-side handling of a non-empty
   `skill_scores_json` is unchanged and that the partial still emits the field.
4. **Resume-reader preservation**: Verify `_resume_text_from_upload` still handles PDF, DOCX, TXT,
   and the empty/unreadable cases exactly as before (the helper itself is not modified).

### Unit Tests

- Test `POST /student/skills/extract` with a readable TXT/PDF/DOCX file returns a fragment containing
  skill chips and a populated hidden `skill_scores_json`.
- Test `POST /student/skills/extract` with an empty/unreadable file returns the empty-skills fragment
  (status 200, no 422) with `skill_scores_json` set to `{}`.
- Test `GET /student/signup` includes `#skill-chips-result` and the resume input carries the HTMX
  attributes (`hx-post`, `hx-target`, `hx-encoding`, `hx-swap`).
- Test the mentor extract endpoint and student submission endpoints still behave as before.

### Property-Based Tests

- Generate varied resume texts and verify the student preview endpoint's `skill_scores` matches
  `extract_skills` output for readable inputs and is `{}` for empty inputs.
- Generate inputs that do NOT trigger the bug condition (mentor extract, student submission, direct
  resume reads) and verify behavior is identical to the pre-fix code.
- Generate random unreadable/empty file payloads and verify the preview endpoint always renders the
  fragment (never raises) while `_resume_text_from_upload` still raises when called directly.

### Integration Tests

- Full student flow: load `GET /student/signup`, post a resume file to the preview endpoint, confirm
  the returned fragment carries chips and the hidden field, then submit `POST /student/signup` and
  confirm the redirect to `/student/matches` and persisted request.
- Cross-flow isolation: exercise the mentor extract/signup flow in the same session to confirm the
  student changes do not affect it.
- Visual-feedback check: confirm that selecting a file on the student page produces a response that
  replaces `#skill-chips-result` (experience badge and chips visible for a readable resume).
