# Requirements Document

## Introduction

This feature reworks the Sprout student sign-up form and its submission handling. Today the student
form (`app/templates/student/signup.html`) asks students to manually pick the skills they want to
learn from a chip picker, groups the meeting cadence selector with that skill picker, and collects
current-skill evidence through a free-text "Resume or project" paste box that feeds the LLM
skill-extraction pipeline.

Four changes are in scope, all limited to the student sign-up flow:

1. Remove the manual "Skills to learn" chip picker and its hidden `skills_to_learn` field.
2. Move the meeting-cadence selector so it appears directly beneath the availability ("When are you
   free?") section.
3. Infer the skills the student wants to learn (`skills_to_learn`) from the student's stated goal
   text using the existing shared skill-extraction pipeline (`extract_skills` in
   `app/services/llm.py`), instead of from manual selection.
4. Replace the free-text resume paste box with a PDF file upload. The uploaded PDF is read
   server-side and its extracted text is run through the same `extract_skills` pipeline to estimate
   current skills.

The mentor sign-up flow, the matching algorithm, and all downstream mentorship behavior are out of
scope except where they consume fields this feature changes.

## Glossary

- **Student_Signup_Form**: The HTML form served at `GET /student/signup`
  (`app/templates/student/signup.html`) that a student fills in to request matches.
- **Signup_Handler**: The server handler for `POST /student/signup`
  (`student_signup_submit` in `app/routers/pages.py`) that builds the `User` and `StudentRequest`
  records and triggers matching.
- **Goal_Text**: The free-text value of the existing `goal_text` form field ("What do you want to
  achieve?").
- **Skills_To_Learn**: The list of taxonomy skill ids stored on `StudentRequest.skills_to_learn`
  that represents what the student wants to learn and is consumed by the matching algorithm.
- **Skill_Extraction_Pipeline**: The existing shared function `extract_skills(text, db)` in
  `app/services/llm.py`, which calls the LLM skill-extraction prompt (with cache) and falls back to
  keyword extraction (`fallback_extract` in `app/services/skills.py`). Returns
  `{skill_id: confidence}`.
- **PDF_Reader**: The server-side component that extracts plain text from an uploaded PDF file,
  implemented with pypdf (the PDF library already declared in the project's dependency manifests).
- **Resume_PDF**: The PDF file a student uploads in place of the former resume paste box.
- **Resume_Text**: The plain text extracted from the Resume_PDF by the PDF_Reader; stored in the
  existing `StudentRequest.resume_text` column.
- **Skill_Scores**: The `{skill_id: confidence}` map stored on `StudentRequest.skill_scores`
  representing the student's estimated current skills, used to derive experience score and level.
- **Cadence_Selector**: The "How often do you want to meet?" `<select name="cadence">` control.
- **Availability_Section**: The "When are you free?" card that includes the availability grid
  partial (`partials/availability_grid.html`).
- **Skill_Preview_Endpoint**: The server-side HTMX endpoint that accepts an uploaded Resume_PDF as
  `multipart/form-data`, runs it through the PDF_Reader and Skill_Extraction_Pipeline, and returns
  the skill chips preview partial (`partials/skill_chips.html`) for the student to review and edit
  before final submission.
- **Skill_Chips_Preview**: The rendered `partials/skill_chips.html` fragment that displays the
  estimated Skill_Scores as editable chips and carries the reviewed values in the hidden
  `skill_scores_json` field.

## Requirements

### Requirement 1: Remove manual skills-to-learn picker

**User Story:** As a student, I want the sign-up form to not ask me to hand-pick skills to learn, so
that I can describe my goal in my own words without choosing from a predefined list.

#### Acceptance Criteria

1. THE Student_Signup_Form SHALL omit the skills-to-learn chip picker element (the `#skills-to-learn`
   container and its selectable skill chips).
2. THE Student_Signup_Form SHALL omit the hidden `skills_to_learn` input field.
3. THE Student_Signup_Form SHALL omit the client-side script that maintained the manual
   skills-to-learn selection.
4. WHERE the former skills-to-learn picker shared a card with the Cadence_Selector, THE
   Student_Signup_Form SHALL present the remaining sign-up sections without an empty or orphaned
   skills-to-learn section.

### Requirement 2: Place cadence beneath availability

**User Story:** As a student, I want to choose how often I meet right after I set when I'm free, so
that scheduling choices are grouped together in a natural order.

#### Acceptance Criteria

1. THE Student_Signup_Form SHALL render the Cadence_Selector in the document after the
   Availability_Section.
2. THE Cadence_Selector SHALL retain the `name="cadence"` attribute and the existing options
   `weekly` and `every_other_week`.
3. WHEN the Student_Signup_Form is submitted, THE Signup_Handler SHALL receive the selected cadence
   value in the `cadence` field exactly as it does today.

### Requirement 3: Infer skills-to-learn from the goal text

**User Story:** As a student, I want the system to figure out which skills I want to learn from the
goal I describe, so that I do not have to translate my goal into a skill list myself.

#### Acceptance Criteria

1. WHEN the Student_Signup_Form is submitted with a non-empty Goal_Text, THE Signup_Handler SHALL
   derive Skills_To_Learn by running the Goal_Text through the Skill_Extraction_Pipeline.
2. THE Signup_Handler SHALL derive Skills_To_Learn from the Goal_Text only and SHALL exclude the
   Resume_Text from the Skills_To_Learn derivation.
3. THE Signup_Handler SHALL set `StudentRequest.skills_to_learn` to the taxonomy skill ids produced
   by the Skill_Extraction_Pipeline for the Goal_Text.
4. IF the Skill_Extraction_Pipeline returns no skills for the Goal_Text, THEN THE Signup_Handler
   SHALL store an empty Skills_To_Learn list and SHALL complete the sign-up without error.
5. THE Signup_Handler SHALL complete sign-up without requiring any manually selected
   skills-to-learn value.

### Requirement 4: Upload a resume PDF instead of pasting text

**User Story:** As a student, I want to upload my resume or project as a PDF file, so that I don't
have to copy and paste its text into a box.

#### Acceptance Criteria

1. THE Student_Signup_Form SHALL omit the `resume_text` free-text textarea and the "Find my skills"
   HTMX button that posted to `/student/skills/extract`.
2. THE Student_Signup_Form SHALL provide a file input that accepts a single PDF file for the resume
   or project upload.
3. THE Student_Signup_Form SHALL declare `enctype="multipart/form-data"` so the selected file is
   transmitted on submission.
4. WHERE a student uploads a Resume_PDF, THE Signup_Handler SHALL extract text from the Resume_PDF
   using the PDF_Reader.
5. WHEN text has been extracted from the Resume_PDF, THE Signup_Handler SHALL estimate Skill_Scores
   by running the extracted Resume_Text through the Skill_Extraction_Pipeline.
6. WHEN the Student_Signup_Form is submitted with a non-empty `skill_scores_json` field, THE
   Signup_Handler SHALL use the posted `skill_scores_json` value as the Skill_Scores and SHALL NOT
   re-run the Skill_Extraction_Pipeline on the Resume_Text.
7. WHEN the Signup_Handler determines the Skill_Scores, THE Signup_Handler SHALL store the extracted
   Resume_Text in `StudentRequest.resume_text` and the resulting Skill_Scores in
   `StudentRequest.skill_scores`.
8. THE Signup_Handler SHALL compute `experience_score` and `experience_level` from the Skill_Scores
   using the existing `experience_score` and `experience_level` functions.

### Requirement 5: Optional upload and invalid-file handling

**User Story:** As a student, I want sign-up to succeed even if I don't upload a file or my file
can't be read, so that one optional step never blocks me from seeing matches.

#### Acceptance Criteria

1. THE Student_Signup_Form SHALL treat the Resume_PDF upload as optional.
2. WHERE no Resume_PDF is provided, THE Signup_Handler SHALL complete sign-up with an empty
   Resume_Text and an empty Skill_Scores map.
3. IF an uploaded Resume_PDF is encrypted, is not a PDF file type, or is corrupt such that the
   PDF_Reader cannot read it, THEN THE Signup_Handler SHALL treat the file as unreadable, complete
   sign-up with an empty Skill_Scores map, and surface a single shared message indicating the file
   could not be read.
4. IF an uploaded Resume_PDF exceeds 10 megabytes, THEN THE Signup_Handler SHALL reject the file and
   surface a message indicating the 10 megabyte size limit.
5. IF text extraction from the Resume_PDF yields no text, THEN THE Signup_Handler SHALL complete
   sign-up with an empty Skill_Scores map.

### Requirement 6: Preview and edit the estimated current skills before submission

**User Story:** As a student, I want to review and adjust the skills estimated from my uploaded PDF
before I submit, so that my matches reflect a current-skills estimate I agree with.

#### Acceptance Criteria

1. THE Skill_Preview_Endpoint SHALL accept an uploaded Resume_PDF transmitted as
   `multipart/form-data`.
2. WHEN a Resume_PDF is submitted to the Skill_Preview_Endpoint, THE Skill_Preview_Endpoint SHALL
   extract text using the PDF_Reader and estimate Skill_Scores by running the extracted Resume_Text
   through the Skill_Extraction_Pipeline.
3. WHEN the Skill_Preview_Endpoint produces Skill_Scores, THE Skill_Preview_Endpoint SHALL return
   the Skill_Chips_Preview partial (`partials/skill_chips.html`) rendering the Skill_Scores as
   editable chips and carrying the scores in the hidden `skill_scores_json` field.
4. IF the Resume_PDF submitted to the Skill_Preview_Endpoint is unreadable per Requirement 5 or
   yields no text, THEN THE Skill_Preview_Endpoint SHALL return the Skill_Chips_Preview partial with
   an empty Skill_Scores map.
5. WHEN the student edits a value in the Skill_Chips_Preview, THE Skill_Chips_Preview SHALL carry
   the edited Skill_Scores in the hidden `skill_scores_json` field.
6. WHEN the Student_Signup_Form is submitted, THE Signup_Handler SHALL use the reviewed Skill_Scores
   carried in the posted `skill_scores_json` field in preference to re-extracting Skill_Scores from
   the Resume_PDF, consistent with Requirement 4 criterion 6.

### Requirement 7: Preserve downstream matching behavior

**User Story:** As a student, I want my matches to be computed from my inferred skills and estimated
level, so that removing the manual inputs does not degrade match quality wiring.

#### Acceptance Criteria

1. WHEN sign-up completes, THE Signup_Handler SHALL run the matching routine using the inferred
   Skills_To_Learn and the reviewed Skill_Scores as it does today.
2. THE Signup_Handler SHALL persist the `StudentRequest` with the same fields populated as today,
   except that Skills_To_Learn is inferred and Resume_Text originates from the Resume_PDF.
3. WHEN sign-up completes, THE Signup_Handler SHALL redirect the student to `/student/matches` as it
   does today.

### Requirement 8: PDF reader dependency

**User Story:** As a maintainer, I want the PDF reading capability backed by a declared dependency,
so that the application installs and runs with the PDF upload feature.

#### Acceptance Criteria

1. THE project dependency manifests (`requirements.txt` and `pyproject.toml`) SHALL continue to
   declare the existing pypdf package used by the PDF_Reader.
2. WHERE the pypdf package is unavailable at runtime, THE Signup_Handler SHALL treat an uploaded
   file as unreadable per Requirement 5 rather than raising an unhandled error.
