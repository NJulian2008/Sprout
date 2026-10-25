# Bugfix Requirements Document

## Introduction

On the student sign-up page (`GET /student/signup`, `app/templates/student/signup.html`), the
extracted-skills section never appears after a student selects a resume file. The prior feature
`student-signup-skill-inference-pdf` specified that the student should be able to preview and edit
the skills inferred from their uploaded resume before submitting (its Requirement 6), but the
student form was shipped without the pieces that make that preview render.

Concretely, the student sign-up template is missing three things that the mentor sign-up template
(`app/templates/mentor/signup.html`) has and uses correctly:

- An include of the skills preview partial (`partials/skill_chips.html`), so the target element
  `#skill-chips-result` exists nowhere on the student page.
- Any HTMX trigger (`hx-post` / `hx-target` / `hx-swap`) to request the preview when a resume is
  provided.
- A server endpoint that accepts the uploaded resume file as `multipart/form-data`, extracts its
  text, runs skill extraction, and returns the `skill_chips.html` fragment.

The only related student endpoint, `POST /student/skills/extract` (`student_skills_extract` in
`app/routers/pages.py`), reads a `text` form field rather than an uploaded file, so even if a
request reached it the resume contents would never be processed.

Because no HTMX request is wired to fire and no element with id `#skill-chips-result` exists on the
page, the extracted-skills section cannot populate. The underlying services do work: final
submission (`POST /student/signup`) reads the uploaded file via `_resume_text_from_upload` and runs
`extract_skills`, and the mentor flow renders the same partial successfully. The defect is confined
to the student-side preview wiring (template HTMX + a file-accepting preview endpoint).

**Reproduction steps**

1. Open `GET /student/signup`.
2. Fill in the goal and specialty fields.
3. Choose a readable resume file (PDF, DOCX, or TXT) in the "Upload your resume" input.
4. Observe the page: no extracted-skills chips, no experience-level badge, and no error appear.
   Nothing on the page changes in response to selecting the file.

**Impact**

Students cannot see or confirm the skills inferred from their resume before submitting, which was a
core promise of the sign-up flow. The sign-up can still be submitted (skills are extracted at final
submission), but the loss of the preview removes the student's ability to review and correct the
estimate, reducing trust and the quality of the current-skills signal they agree to.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a student selects a readable resume file in the resume upload input on the student sign-up
    form THEN the system does not display the extracted skill chips or experience-level badge,
    because the student sign-up template contains no `#skill-chips-result` element and no HTMX
    trigger to request the skills preview.
1.2 WHEN a student provides a resume on the student sign-up form THEN the system issues no
    client-side HTTP request to render a skills preview, so the extracted-skills section is never
    requested or returned.
1.3 WHEN a resume file is sent to the existing student extract endpoint `POST /student/skills/extract`
    THEN the system reads only a `text` form field and ignores any uploaded file, so the resume
    contents are never extracted or returned as skill chips.

### Expected Behavior (Correct)

2.1 WHEN a student provides a readable resume file on the student sign-up form THEN the system SHALL
    display the extracted skill chips and experience-level badge in a `#skill-chips-result` section
    on the page, rendered from the `partials/skill_chips.html` fragment.
2.2 WHEN a student provides a resume on the student sign-up form THEN the system SHALL issue a
    client-side HTMX request that targets the `#skill-chips-result` section and swaps in the
    returned skills preview fragment.
2.3 WHEN a resume file is submitted to the student skills-preview endpoint as
    `multipart/form-data` THEN the system SHALL extract text from the uploaded file, run it through
    the skill-extraction pipeline, and return the `partials/skill_chips.html` fragment carrying the
    estimated skills in the hidden `skill_scores_json` field.
2.4 WHEN the uploaded resume is unreadable or yields no text THEN the system SHALL return the skills
    preview fragment with an empty skills map rather than failing to render the section.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a mentor uses the "Find my skills" control on the mentor sign-up form THEN the system SHALL
    CONTINUE TO post to `/mentor/skills/extract`, render the `partials/skill_chips.html` fragment
    into `#skill-chips-result`, and show the mentor's extracted skills as before.
3.2 WHEN the student sign-up form is submitted at `POST /student/signup` with a readable resume file
    THEN the system SHALL CONTINUE TO extract the resume text, run skill extraction, persist
    `StudentRequest.skill_scores`, `resume_text`, `experience_score`, and `experience_level`, run
    matching, and redirect to `/student/matches`.
3.3 WHEN the student sign-up form is submitted with a non-empty `skill_scores_json` field THEN the
    system SHALL CONTINUE TO use the posted reviewed scores in preference to re-extracting skills
    from the resume text.
3.4 WHEN a resume file is read on the server THEN the system SHALL CONTINUE TO support the existing
    PDF, DOCX, and TXT formats and the existing unreadable/empty-file handling in
    `_resume_text_from_upload`.
