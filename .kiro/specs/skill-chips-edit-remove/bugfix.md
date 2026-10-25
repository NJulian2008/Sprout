# Bugfix Requirements Document

## Introduction

On the student and mentor sign-up forms, AI-extracted skills are shown as "skill chips" rendered by the partial `app/templates/partials/skill_chips.html`. The partial's note tells the user "AI estimate — edit any value below," and the mentor form's heading promises users can "edit freely," implying each skill's confidence can be changed, unwanted skills can be removed, and skills the AI missed can be added before submission.

In reality the chips are static, read-only `<span>` elements with no interactive controls. There is no way to delete a skill, change its confidence, or add a skill the extractor did not detect. The only persisted value is a hidden JSON input (`name="skill_scores_json"`) that is populated from the server-rendered `skill_scores` dict and never updated on the client, so whatever the AI extracts is submitted verbatim. Compounding this, the student submit handler (`/student/signup`) re-extracts skills from the resume server-side and ignores `skill_scores_json` entirely, so even a correctly edited value would be discarded on the student path.

This bug makes the advertised "edit any value" / "edit freely" affordance non-functional and causes inaccurate skill profiles to be saved, which in turn feeds the experience score, experience level, and mentor matching. In particular, when the AI misses a skill the user actually has (or detects none at all), there is no way to add it, so the saved profile understates the user's real skill set.

## Bug Analysis

### Current Behavior (Defect)

The UI claims skills are editable, but no edit, removal, or add controls exist, and edits (if they were possible) would not be persisted on the student path.

1.1 WHEN extracted skill chips are displayed on the student or mentor sign-up form THEN the system renders each skill as a static read-only `<span>` with no control to change its confidence value
1.2 WHEN extracted skill chips are displayed on the student or mentor sign-up form THEN the system renders each skill with no control to remove or delete that skill
1.3 WHEN the user wants to add a skill the AI did not extract THEN the system provides no control to add one, so a skill the user actually has cannot be included in the submitted set
1.4 WHEN the user attempts to adjust, remove, or add a skill before submitting THEN the system leaves the hidden `skill_scores_json` field unchanged, so the AI-extracted set is submitted verbatim
1.5 WHEN skills are shown THEN the system displays the note "AI estimate — edit any value below" (and the mentor form promises "edit freely") even though no editing or adding is possible
1.6 WHEN the displayed experience level and score are shown THEN the system does not recompute them in response to any user change, because no user change can occur
1.7 WHEN the student sign-up form is submitted THEN the system re-extracts skills from the resume server-side and ignores the submitted `skill_scores_json`, discarding any client-side edits or additions
1.8 WHEN no skills are detected THEN the system shows "No skills detected yet" and offers no way to add a skill manually, so the user can only ever submit an empty skill set on that path

### Expected Behavior (Correct)

Users can change a skill's confidence, remove skills, and add a skill the AI missed (chosen from the taxonomy); those changes stay in sync with the submitted data, the derived experience values reflect them, and both submit handlers persist the resulting set.

2.1 WHEN extracted skill chips are displayed on the student or mentor sign-up form THEN the system SHALL provide a control that lets the user change each skill's confidence value
2.2 WHEN extracted skill chips are displayed on the student or mentor sign-up form THEN the system SHALL provide a control that lets the user remove each individual skill
2.3 WHEN the user wants to include a skill the AI did not extract THEN the system SHALL provide a control to add a skill, constrained to the skills taxonomy so the added skill maps to a canonical taxonomy id (consistent with `normalize_skill_id` and the taxonomy in `app/services/skills.py`), and SHALL assign it an initial confidence the user can then edit like any other chip
2.4 WHEN the user adds a skill that is already present in the current set THEN the system SHALL update/merge that skill's confidence rather than creating a duplicate chip or duplicate key
2.5 WHEN the user changes a skill's confidence value, removes a skill, or adds a skill THEN the system SHALL update the hidden `skill_scores_json` field so it reflects the current edited set (including additions) at submission time
2.6 WHEN the user has edited the skill set THEN the system SHALL present a note consistent with the actual available controls (changing values, removing skills, and adding skills)
2.7 WHEN the user changes a confidence value, removes a skill, or adds a skill THEN the system SHALL recompute and display the experience level and experience score consistently with the skills service rules (mean of the top-k confidences, mapped to beginner/intermediate/advanced), accounting for added skills
2.8 WHEN a sign-up form is submitted with an edited `skill_scores_json` THEN the system SHALL persist the edited skill set (including additions, removals, and value changes) for both the student and mentor paths, rather than re-extracting and discarding the edits
2.9 WHEN a confidence value is edited (including the initial confidence of an added skill) THEN the system SHALL constrain it to the valid confidence range (0 through 1 inclusive, i.e. 0%–100%) and ignore or clamp out-of-range input
2.10 WHEN no skills were detected ("No skills detected yet") THEN the system SHALL STILL allow the user to add a skill from the taxonomy, after which the chip, hidden `skill_scores_json`, and experience values reflect the added skill

### Unchanged Behavior (Regression Prevention)

The fix must not alter extraction, submission of unedited data, or any unrelated signup behavior.

3.1 WHEN the user uploads a resume or pastes text and triggers skill extraction THEN the system SHALL CONTINUE TO extract skills via the existing `/student/skills/extract` and `/mentor/skills/extract` endpoints and render them as chips
3.2 WHEN the user does not edit, remove, or add any skill before submitting THEN the system SHALL CONTINUE TO submit and persist the AI-extracted skill set exactly as extracted
3.3 WHEN no skills are detected and the user adds none THEN the system SHALL CONTINUE TO show the "No skills detected yet" message and submit an empty skill set (`{}`)
3.4 WHEN the experience level and score are computed from a given skill set THEN the system SHALL CONTINUE TO produce the same results as the existing `experience_score` and `experience_level` helpers for that set
3.5 WHEN a skill (added or extracted) is mapped to a taxonomy id THEN the system SHALL CONTINUE TO use only canonical taxonomy ids, consistent with existing normalization, and SHALL NOT persist unknown or free-text skill keys
3.6 WHEN the form is submitted THEN the system SHALL CONTINUE TO process all other fields (goal, specialty, availability, top3, outcomes, resume text, specialties) exactly as before
3.7 WHEN `skill_scores_json` is absent, empty, or malformed THEN the system SHALL CONTINUE TO fall back to its existing handling without crashing

## Bug Condition

**Bug Condition Function** — identifies the inputs that trigger the bug:

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type SignupInteraction
  OUTPUT: boolean

  // The bug is triggered whenever the user wants to curate the skill set
  // before submitting — change a value, remove a skill, or add a skill the AI
  // missed — because no control exists, and on the student path the submitted
  // edits are ignored server-side. Adding is possible even when the AI
  // extracted nothing, so it is not gated on hasExtractedSkills.
  RETURN (X.hasExtractedSkills
          AND (X.userWantsToEditValue OR X.userWantsToRemoveSkill))
     OR  X.userWantsToAddSkill
END FUNCTION
```

**Property Specification (Fix Checking)** — correct behavior for buggy inputs:

```pascal
// Property: Fix Checking — editable, addable, synced, and persisted skill chips
FOR ALL X WHERE isBugCondition(X) DO
  result ← handleSignup'(X)
  ASSERT editControlsExist(result)                         // values editable, skills removable
    AND  addControlExists(result)                          // skill can be added from the taxonomy
    AND  (NOT X.userWantsToAddSkill
          OR isCanonicalTaxonomyId(addedSkillId(X)))       // added skill maps to a taxonomy id
    AND  hiddenJson(result) = userEditedSkillSet(X)        // skill_scores_json reflects adds/edits/removals
    AND  noDuplicateKeys(hiddenJson(result))               // adding an existing skill merges, not duplicates
    AND  displayedLevel(result) = experience_level(experience_score(userEditedSkillSet(X)))
    AND  persistedSkills(result) = userEditedSkillSet(X)   // student + mentor paths both persist the set
END FOR
```

where `userEditedSkillSet(X)` is the AI-extracted set with the user's value changes and removals applied, plus any added skills merged in under their canonical taxonomy id (a duplicate add updating the existing confidence rather than creating a second entry).

**Preservation Goal (Preservation Checking)** — inputs the user does not curate behave identically:

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT handleSignup(X) = handleSignup'(X)
END FOR
```

**Key Definitions:**
- **F** (`handleSignup`): the signup/extract flow before the fix — static chips, no add control, verbatim submission, student-path re-extraction.
- **F'** (`handleSignup'`): the signup/extract flow after the fix — editable/removable chips plus an add-from-taxonomy control, all kept in sync with `skill_scores_json`, recomputed experience values, and both handlers persisting the resulting set.
- **Counterexample**: AI extracts `{python: 0.9, java: 0.8}`; the user lowers `python` to `0.5`, removes `java`, and adds `sql` (which the AI missed) at `0.6`, but the saved profile is still `{python: 0.9, java: 0.8}` — the add/edit/remove are all dropped (mentor path keeps the stale set; student path re-extracts and ignores the edits), and with the AI detecting nothing there is likewise no way to add `sql` to an otherwise empty set.
