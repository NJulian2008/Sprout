# Skill Chips Edit/Remove Bugfix Design

## Overview

The student and mentor sign-up forms promise that AI-extracted skills can be edited ("AI estimate — edit any value below" / "edit freely"), but the chips rendered by `app/templates/partials/skill_chips.html` are static read-only `<span>` elements. There is no control to change a skill's confidence, remove a skill, or add a skill the AI missed. The hidden `skill_scores_json` input is never updated on the client, and the student submit handler (`POST /student/signup`) re-extracts skills server-side and discards `skill_scores_json` entirely. When the AI detects nothing, the partial shows "No skills detected yet" with no way to add a skill at all.

The fix adds client-side edit, remove, and add controls to the chips partial, keeps the hidden `skill_scores_json` input in sync with those edits using vanilla JS, recomputes and re-displays the experience level/score on the client as the user edits, and changes the student submit handler to honor a posted `skill_scores_json` (mirroring the mentor handler) while still re-extracting when none is posted. The add control is a taxonomy-constrained picker (not free text) so every added skill maps to a canonical taxonomy id; adding an id that is already present merges into the existing chip rather than creating a duplicate. The add control renders in both the populated and empty branches of the partial, so a user can build a skill set from scratch even when the AI detected nothing. The server remains the authority: at submit time both handlers recompute `experience_score`/`experience_level` from the submitted (edited) skill set via the existing `app/services/skills.py` helpers.

The approach stays within the existing stack — FastAPI + Jinja2 + HTMX + vanilla JS — and reuses the inline-script pattern already present in both signup templates (the pick-3 priorities / `multiSelect` scripts). The partial is HTMX-swapped (`hx-swap="outerHTML"` into `#skill-chips-result`) by the extract endpoints, so the edit wiring must (re)initialize after every swap, not just on first page load.

## Glossary

- **Bug_Condition (C)**: Either (a) extracted skills are displayed and the user wants to change a confidence value or remove a skill, or (b) the user wants to add a skill the AI did not extract (possible even from the empty "No skills detected yet" state) — but no control exists, and on the student path any posted edits are ignored server-side.
- **Property (P)**: After the fix, edit, remove, and add controls exist, the hidden `skill_scores_json` stays in sync with the user's edited set (including additions), displayed experience level/score reflect the edited set per the skills-service rules, and both submit handlers persist the edited set.
- **Preservation**: Extraction behavior, submission of unedited/un-added data, empty/no-skills handling when the user adds nothing, the `experience_score`/`experience_level` computations, and all other sign-up fields must remain unchanged.
- **skill_chips.html**: The partial in `app/templates/partials/skill_chips.html` that renders chips, the add control, the experience badge/score line, and the hidden `skill_scores_json` input. Rendered both on initial page load (with an empty `skill_scores`) and as the HTMX swap target of the extract endpoints.
- **skill_scores_json**: The hidden form input (`field_name = "skill_scores_json"`) holding a JSON object `{skill_id: confidence}` submitted with the form. Currently populated once via `skill_scores|tojson` and never updated client-side.
- **extract endpoints**: `POST /student/skills/extract` and `POST /mentor/skills/extract` in `app/routers/pages.py`, which run extraction and re-render `skill_chips.html` as an HTMX fragment.
- **taxonomy (picker source)**: The `{skill_id: {id, label, aliases}}` dict returned by `load_taxonomy()` and passed to every `skill_chips.html` render (signup GET routes, both extract endpoints). The add control iterates `taxonomy.values()` to offer each skill's `label` while submitting its canonical `id`, so added skills are always canonical (Requirements 2.3, 3.5).
- **add control**: The taxonomy-constrained picker (`<select>` or `<datalist>`) plus an "Add" button rendered by the partial. On add it inserts a new chip at a default initial confidence, merges the id into the in-memory map (an already-present id updates rather than duplicates — Requirement 2.4), rewrites `skill_scores_json`, and recomputes the badge/score.
- **experience_score(skills, k=5)** / **experience_level(score)**: Pure helpers in `app/services/skills.py`. The score is the mean of the top-k (k=5) confidence values (0.0 for an empty dict); the level maps `< 0.35 → beginner`, `< 0.65 → intermediate`, `≥ 0.65 → advanced`.

## Bug Details

### Bug Condition

The bug manifests whenever the user wants to curate the skill set before submitting — adjust a skill's confidence, remove a skill, or add a skill the AI missed. The chips partial renders values as static spans with no interactive control and offers no add control, the client never writes back to `skill_scores_json`, and the student submit handler ignores `skill_scores_json` and re-extracts from the resume, so even a hypothetically edited or added value is discarded on that path. The add case is not gated on there being extracted skills: the user may want to add a skill even from the empty "No skills detected yet" state.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SignupInteraction
  OUTPUT: boolean

  RETURN (
           (input.hasExtractedSkills
            AND (input.userWantsToEditValue OR input.userWantsToRemoveSkill))
           OR input.userWantsToAddSkill
         )
         AND (NOT editControlExists(input.renderedChips)
              OR NOT addControlExists(input.renderedChips)
              OR NOT hiddenJsonReflects(input.renderedChips, input.userEditedSet)
              OR submittedEditsIgnored(input.path, input.userEditedSet))
END FUNCTION
```

### Examples

- AI extracts `{python: 0.9, java: 0.8}`. The user wants to lower `python` to `0.5` — expected: slider/input lets them set `0.5` and the submitted set has `python: 0.5`; actual: the confidence is a read-only `<span>`, nothing changes.
- AI extracts `{python: 0.9, java: 0.8}`. The user wants to remove `java` — expected: a remove control deletes the chip and the submitted set is `{python: 0.9}`; actual: no remove control exists, `java` is submitted verbatim.
- AI extracts `{python: 0.9}` but the user also knows `sql`. The user wants to add `sql` — expected: a taxonomy picker inserts a `sql` chip at a default confidence the user can adjust, and the submitted set is `{python: 0.9, sql: <default>}`; actual: no add control exists, so `sql` can never be included.
- Add merge case: AI extracts `{python: 0.9}` and the user picks `Python` again from the add control — expected: the existing `python` chip is updated (no second chip, no duplicate key); actual: no add control exists at all.
- Mentor path: user edits down to `{python: 0.5}` but no control exists, so `skill_scores_json` still holds the original extracted set and the stale set is persisted.
- Student path (worst case): even if `skill_scores_json` were correctly edited or added to, `POST /student/signup` calls `extract_skills(resume_text, db)` and ignores the posted JSON, so the edit/addition is discarded and skills are re-extracted from the resume.
- Empty-state add case: AI extracts nothing (`{}`), so "No skills detected yet" shows. The user wants to add `sql` manually — expected: the add control is present in the empty branch too, so adding `sql` yields a chip and a submitted set `{sql: <default>}`; actual: the empty branch has no add control, so the user can only ever submit `{}` on that path.
- Edge case (unchanged): AI extracts nothing and the user adds nothing. Expected: "No skills detected yet" message and an empty set `{}` submitted — this must stay unchanged.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Skill extraction continues to work via `POST /student/skills/extract` and `POST /mentor/skills/extract`, rendering chips as before (Requirement 3.1).
- When the user does not edit, remove, or add anything, the AI-extracted set is submitted and persisted exactly as extracted (Requirement 3.2).
- When no skills are detected and the user adds none, the "No skills detected yet" message shows and an empty set `{}` is submitted (Requirement 3.3).
- `experience_score` and `experience_level` produce identical results for any given skill set — the helpers are not modified (Requirement 3.4).
- Only canonical taxonomy ids are persisted; the add control is constrained to the taxonomy so no unknown or free-text keys enter `skill_scores_json`, consistent with existing normalization (Requirement 3.5).
- All other sign-up fields (goal, specialty, availability, top3, outcomes, resume text, specialties, mentor fields) are processed exactly as before (Requirement 3.6).
- When `skill_scores_json` is absent, empty, or malformed, handling falls back gracefully without crashing (Requirement 3.7).

**Scope:**
All inputs that do NOT involve editing, removing, or adding a skill should be completely unaffected by this fix. This includes:
- Unedited extraction results on both paths.
- The empty / no-skills result when the user adds nothing.
- Every non-skill form field and the HTMX extraction round-trip itself.

**Note:** The expected correct behavior for buggy inputs is defined in the Correctness Properties section (Property 1).

## Hypothesized Root Cause

Based on the bug description and code, the defect has two distinct roots — one in the template/client layer and one in the student submit handler.

1. **No interactive controls in the chips partial**: `skill_chips.html` renders each skill as `<span class="chip">…<span class="conf">N%</span></span>` with no input or remove button, and offers no control to add a skill the AI missed (in either the populated or the empty branch). There is nothing for the user to interact with, so Requirements 2.1, 2.2, 2.3, and 2.10 cannot be met.

2. **Hidden field never updated client-side**: `skill_scores_json` is set once from `skill_scores|tojson` at render time and no script writes back to it. Even if controls existed, edits and additions would not reach the server (Requirement 2.5).

3. **No client-side recompute of experience level/score**: The badge and score are rendered once from the server-provided values and there is no JS to recompute them as the user edits or adds (Requirement 2.7). The computation must mirror `experience_score` (mean of top-k=5) and `experience_level` (0.35 / 0.65 thresholds).

4. **Student submit handler ignores `skill_scores_json`**: `POST /student/signup` does not accept a `skill_scores_json` form field at all; it calls `extract_skills(resume_text, db)` and uses that result unconditionally, discarding any client edits or additions (Requirement 2.8). The mentor handler already honors a posted set (`posted = json.loads(skill_scores_json)` → `scores = {k: float(v) for k, v in posted.items()}`), so the student handler should follow the same honor-if-present-else-extract pattern. Added canonical ids survive that `float(v)` coercion unchanged, and because the picker only emits canonical ids, no non-canonical keys reach the persisted set (Requirement 3.5) — so no extra server change is needed beyond adopting the mentor pattern.

5. **Re-initialization after HTMX swap**: The chips partial is swapped via `hx-swap="outerHTML"`. Any edit/add-wiring script must run both on initial load and after each swap (e.g. via an `htmx:afterSwap` listener or an inline initializer inside the partial), otherwise controls only work before the first extraction or not at all. The initializer must also handle the empty → non-empty transition so that adding the first skill from the "No skills detected yet" state produces a chip, updates the hidden field, and recomputes the badge (Requirement 2.10).

6. **Taxonomy not guaranteed to the picker**: The add control needs the taxonomy to populate its options. `load_taxonomy()` is already passed to `skill_chips.html` on every render path — the signup GET routes (`student_signup_form`, `mentor_signup_form`), both extract endpoints (`student_skills_extract`, `mentor_skills_extract`), so `taxonomy` is in scope wherever the partial renders. The partial can iterate `taxonomy.values()` for `{id, label}` directly, so no new context variable is strictly required; if a leaner payload is preferred, each render call may pass an explicit `taxonomy_options` list of `{id, label}` instead. No currently-missing render path was found.

## Correctness Properties

Property 1: Bug Condition - Editable, addable, synced, recomputed, and persisted skill chips

_For any_ input where the bug condition holds (isBugCondition returns true) — extracted skills are shown and the user changes a confidence value or removes a skill, or the user adds a skill the AI missed (including from the empty "No skills detected yet" state) — the fixed sign-up flow SHALL provide a control to change each skill's confidence, a control to remove each skill, and a taxonomy-constrained add control that is present in both the populated and empty branches. When the user adds a skill it SHALL insert a chip at a default user-editable initial confidence under the chosen canonical taxonomy id, and adding an id already present SHALL merge into (update) the existing chip rather than create a duplicate chip or duplicate key. The flow SHALL keep the hidden `skill_scores_json` field in sync with the user's current edited set (including additions) at submission time, display an experience level and score computed from that set consistently with `experience_level(experience_score(editedSet))`, constrain every confidence (including an added skill's initial confidence) to the inclusive range 0–1 (clamping or ignoring out-of-range input), and persist the edited skill set — using only canonical taxonomy ids — on both the student and mentor submit paths rather than re-extracting and discarding the changes.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10**

Property 2: Preservation - Unedited and unrelated behavior

_For any_ input where the bug condition does NOT hold (isBugCondition returns false) — the user triggers extraction but does not edit, remove, or add any skill, no skills are detected and none are added, or any non-skill field is submitted — the fixed code SHALL produce the same result as the original code: extraction still renders chips, an unedited extracted set is submitted and persisted verbatim, an empty result with no additions still shows "No skills detected yet" and submits `{}`, `experience_score`/`experience_level` are unchanged, only canonical taxonomy ids are persisted, all other fields are processed as before, and absent/empty/malformed `skill_scores_json` falls back without crashing.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming the root cause analysis is correct, three files change: the chips partial (edit/remove/add controls + sync/recompute script), the student submit handler (honor posted JSON), and the stylesheet (minor styling for the new controls). The skills service is NOT modified, and no new server context is required because `taxonomy` already reaches every render path.

**File**: `app/templates/partials/skill_chips.html`

1. **Render editable confidence control per chip**: Replace the read-only `<span class="conf">` with an editable control bound to the skill id — a numeric input (`type="number"`, `min="0"`, `max="100"`, `step="1"`, representing percent) and/or a `range` slider, carrying a `data-skill` attribute equal to the taxonomy `sid`. Keep displaying the skill label (`taxonomy[sid].label if sid in taxonomy else sid`).

2. **Render a remove control per chip**: Add a small button (`type="button"`, `class="chip-remove"`, `data-skill="{{ sid }}"`, `aria-label="Remove {{ label }}"`) inside each chip so the user can delete that skill.

3. **Render a taxonomy-constrained add control in BOTH branches**: Add an "add skill" control so the user can include a skill the AI missed (Requirement 2.3). Because an added skill must map to a canonical taxonomy id (Requirements 2.3, 3.5), the control is a picker over the taxonomy rather than a free-text field — a `<select class="chip-add-select">` (or an `<input list=...>` bound to a `<datalist>`) populated from the taxonomy, showing each entry's `label` and carrying its canonical `id` as the option `value`:
   ```jinja
   <select class="chip-add-select" aria-label="Add a skill">
     <option value="" selected disabled>Add a skill…</option>
     {% for sid, entry in taxonomy.items() %}
       <option value="{{ sid }}">{{ entry.label }}</option>
     {% endfor %}
   </select>
   <button type="button" class="chip-add" aria-label="Add selected skill">Add</button>
   ```
   This add control MUST render in both the populated (`{% if skill_scores %}`) branch and the empty (`{% else %}`) branch, so a user can add a skill even from the "No skills detected yet" state (Requirement 2.10). (Iterating `taxonomy.items()` keeps every id canonical; if a leaner payload is preferred, iterate a passed-in `taxonomy_options` list of `{id, label}` instead — but no server change is required since `taxonomy` is already in context.)

4. **Keep the hidden field and seed it from the server set**: Keep `<input type="hidden" name="{{ field_name }}" value='{{ skill_scores|tojson }}'>` as the initial/authoritative-at-render value and the sync target in both branches. Preserve the empty branch's `value="{}"` and the "No skills detected yet" message (now accompanied by the add control) for Requirements 3.3 and 3.7.

5. **Update the editing note**: Change the note to one consistent with the controls, e.g. "AI estimate — adjust any value, remove a skill, or add one below." (Requirement 2.6). The mentor template's "edit freely" heading already matches; no change required there.

6. **Add a self-initializing script in the partial (edit + remove + add + merge)**: Because the partial is HTMX-swapped, include a `<script>` at the end of the partial that builds the in-memory map from the current hidden-input JSON and wires up the controls for the just-rendered fragment. Behaviors:
   - **On confidence change**: clamp the percent to `[0,100]`, convert to a `0–1` float, update the map, rewrite the hidden input's `value` as JSON, recompute the badge/score (Requirements 2.5, 2.7, 2.9).
   - **On remove**: delete the chip's entry from the map, remove the chip element, rewrite the hidden input, recompute (Requirements 2.2, 2.5, 2.7).
   - **On add**: read the selected canonical id from the picker; if the id is already in the map, update/keep its existing chip (merge, do NOT append a second chip or key — Requirement 2.4); otherwise insert a new chip for that id (label from the picker's option text) at a default initial confidence (e.g. 0.5), clamped to `[0,1]` and user-editable like any other chip. Then merge into the map, rewrite the hidden input, and recompute (Requirements 2.3, 2.4, 2.5, 2.7, 2.9). The add handler MUST also handle the empty → non-empty transition: when adding from the "No skills detected yet" state, replace/convert the empty placeholder into a chips container so the first added chip, the updated hidden field, and the recomputed badge all appear (Requirement 2.10).
   This self-initializing-partial approach guarantees the wiring runs after every swap without a separate global `htmx:afterSwap` handler; if a global handler is preferred, it must be idempotent and target `#skill-chips-result`.

7. **Client-side experience recompute (display only)**: Implement a JS mirror of the skills-service rules for live display: `score = mean(top 5 confidences descending)`, `0` when empty; `level = beginner (<0.35) | intermediate (<0.65) | advanced (≥0.65)`. Round the displayed score to 2 decimals to match the server-rendered `round(exp_s, 2)`. Update the `.badge badge-<level>` class and label and the `(score …)` text, accounting for added skills. This is display-only; the server recomputes authoritatively at submit.

**File**: `app/routers/pages.py` — `student_signup_submit` (`POST /student/signup`)

8. **Accept and honor `skill_scores_json` (mirror the mentor handler)**: Add a `skill_scores_json: str = Form("{}")` parameter. Replace the unconditional `scores = extract_skills(resume_text, db)` with the same honor-if-present-else-extract logic the mentor handler uses:
   ```python
   try:
       posted = json.loads(skill_scores_json) if skill_scores_json else {}
   except json.JSONDecodeError:
       posted = {}
   if posted:
       scores = {k: float(v) for k, v in posted.items()}
   elif resume_text.strip():
       scores = extract_skills(resume_text, db)
   else:
       scores = {}
   ```
   Then compute `exp_s = experience_score(scores)` and `experience_level(exp_s)` from `scores` as today, so the server stays authoritative and matching uses the edited set (Requirements 2.5, 2.8). `goal_skills`/`goal_type` extraction from `goal_text` is unchanged.

   Added skills require no extra server handling: the add control emits the same `{skill_id: confidence}` shape under canonical taxonomy ids, so an added entry is just another key in `posted`. The `{k: float(v) for k, v in posted.items()}` coercion preserves the id keys verbatim (only values are coerced to float), and because the picker only produces canonical ids, no unknown/free-text key can be persisted (Requirement 3.5). The merge-not-duplicate guarantee is enforced client-side (a JSON object cannot hold duplicate keys anyway, so a re-added id overwrites its prior value — Requirement 2.4).

9. **Preserve empty/malformed fallback**: The `try/except` + `elif resume_text.strip()` structure keeps Requirement 3.7 (absent/empty/malformed JSON) and Requirement 3.2 (unedited: client posts the extracted set verbatim, so `posted` equals the extraction and nothing changes) intact. When extraction found nothing and the user added nothing, the client posts `{}`, `posted` is falsy, and the resume is re-extracted — matching prior student-path behavior for the no-skills case. When the user added a skill from the empty state, `posted` is non-empty and is honored, so the manually added skill is persisted.

**File**: `app/static/styles.css`

10. **Style the new controls**: Add minimal rules for the per-chip numeric/slider input, the `.chip-remove` button, and the add control (`.chip-add-select` / `.chip-add`) so they sit within the existing `.chips` layout and `.chip` pill (reuse `.chips`/`.chip`/`.badge-*` classes already defined). No change to existing chip/badge rules.

### Why both display-side and server-side recompute

The client recompute (change 6) gives immediate feedback and satisfies Requirement 2.5 at the UI level. The server recompute (change 7, unchanged mentor logic) is the source of truth for persisted `experience_score`/`experience_level` and for matching. Keeping both in agreement depends only on the JS mirroring the documented skills-service rules; the Python helpers are untouched, preserving Requirement 3.4.

## Testing Strategy

### Validation Approach

The strategy is two-phase: first surface counterexamples that demonstrate the bug on the current code, then verify the fix works and preserves existing behavior. Server-side logic (`student_signup_submit`, `mentor_signup_submit`, and the skills helpers) is covered by Python tests using the existing TestClient setup under `tests/`. Client-side edit/add/sync/recompute behavior — including the merge-not-duplicate rule and the empty → non-empty add transition — is described for manual/DOM verification since the project has no JS test harness; the server-side persistence of a posted `skill_scores_json` (including added canonical ids) is the authoritative, automatable guarantee.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix, and confirm the root-cause split (template has no controls — edit, remove, or add; student handler ignores posted JSON). If refuted, re-hypothesize.

**Test Plan**: Write tests against the current code. For the server, post to `/student/signup` with a `skill_scores_json` that differs from what the resume would extract (including an added skill the resume lacks), then assert the persisted `StudentRequest.skill_scores` ignores the posted set (demonstrating the discard). For the template, assert the rendered chips fragment contains no editable input, no remove control, and no add control — in both the populated and empty branches.

**Test Cases**:
1. **Student discard test**: `POST /student/signup` with a resume plus `skill_scores_json={"python": 0.5}`; assert the saved `skill_scores` came from re-extraction, not the posted `{"python": 0.5}` (will fail to honor edits on unfixed code).
2. **Student added-skill discard test**: `POST /student/signup` with a resume plus `skill_scores_json` containing a skill the resume does not mention (e.g. `{"sql": 0.6}` for a Python-only resume); assert `sql` is absent from the persisted set because the handler re-extracts (will fail on unfixed code).
3. **No controls test**: Render `partials/skill_chips.html` (or hit an extract endpoint) with a non-empty `skill_scores`; assert the HTML has no `input`/`chip-remove`/`data-skill` control inside chips and no add control (`chip-add`/`chip-add-select`) (passes on unfixed code, documenting the defect).
4. **No add control in empty state test**: Render the partial with an empty `skill_scores`; assert the empty branch shows "No skills detected yet" and has no add control (passes on unfixed code, documenting Requirement 2.10's defect).
5. **Mentor stale-set observation**: `POST /mentor/signup` with `skill_scores_json` equal to the extracted set (no client edit possible); confirm it persists verbatim — baseline for preservation.
6. **Edge case**: Extract endpoint with text yielding no skills; assert "No skills detected yet" and hidden `value="{}"` (baseline; must stay true after fix when the user adds nothing).

**Expected Counterexamples**:
- Student handler persists re-extracted skills regardless of posted `skill_scores_json`, dropping both edits and added skills.
- Chips fragment exposes no control to edit a value, remove a skill, or add a skill — in either branch.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed flow produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := handleSignup_fixed(input)
  ASSERT editControlsExist(result)                       // value-edit + remove controls
    AND  addControlExists(result)                        // taxonomy picker, both branches
    AND  (NOT input.userWantsToAddSkill
          OR isCanonicalTaxonomyId(addedSkillId(input))) // added skill is canonical
    AND  hiddenJson(result) = userEditedSkillSet(input)  // reflects edits/removals/additions
    AND  noDuplicateKeys(hiddenJson(result))             // re-add merges, not duplicates
    AND  displayedLevel(result) = experience_level(experience_score(userEditedSkillSet(input)))
    AND  persistedSkills(result) = userEditedSkillSet(input)
END FOR
```

where `userEditedSkillSet(input)` is the extracted set with value changes and removals applied, plus any added skills merged in under their canonical taxonomy id.

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed flow produces the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT handleSignup_original(input) = handleSignup_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because it generates many skill sets across the input domain, catches edge cases manual tests miss, and gives strong guarantees that unedited/unrelated behavior is unchanged. Capture current behavior on unedited inputs, then assert the fixed code matches.

**Test Plan**: Observe current behavior for unedited submissions and the no-skills case, then write tests that post the extracted set verbatim as `skill_scores_json` and assert the persisted result is identical to extraction.

**Test Cases**:
1. **Unedited student submission**: `POST /student/signup` posting `skill_scores_json` equal to what the resume extracts; assert persisted `skill_scores` equals the extracted set (Requirement 3.2).
2. **Unedited mentor submission**: `POST /mentor/signup` unchanged behavior holds (Requirement 3.2).
3. **No-skills, no-add case**: Empty extraction and no additions → `{}` submitted and persisted; "No skills detected yet" shown (Requirement 3.3).
4. **Malformed/absent JSON**: `POST /student/signup` with `skill_scores_json` missing or `"not json"`; assert graceful fallback to re-extraction, no crash (Requirement 3.7).
5. **Canonical-ids only**: Post a `skill_scores_json` whose keys are canonical taxonomy ids (as the picker always emits); assert the persisted keys are exactly those canonical ids, unchanged by the `float(v)` coercion (Requirement 3.5).
6. **Other fields unchanged**: Assert goal, specialty, availability, top3, outcomes, specialties persist exactly as before (Requirement 3.6).

### Unit Tests

- `experience_score` / `experience_level` still return documented values for representative sets, including empty (Requirement 3.4) — guards against accidental helper changes.
- Student handler: posted non-empty `skill_scores_json` (including a key the resume would not extract, i.e. an added skill) is honored and used for `experience_score`; empty/malformed falls back to extraction.
- Student handler: `float(v)` coercion of posted confidences preserves the id keys and coerces only values; out-of-range values are handled (clamped client-side; server trusts the already-clamped submitted set).
- Template render (populated): non-empty `skill_scores` produces per-chip editable input, a remove control with `data-skill`, and an add control (`chip-add-select` populated from `taxonomy` with canonical ids as option values + `chip-add` button).
- Template render (empty): empty `skill_scores` produces the "No skills detected yet" branch with `value="{}"` AND an add control, so a skill can be added from scratch (Requirement 2.10).

### Property-Based Tests

- Generate random skill sets `{skill_id: confidence in [0,1]}` over canonical taxonomy ids; post them as `skill_scores_json` to `/student/signup` and `/mentor/signup`; assert persisted `skill_scores` equals the posted set and `experience_score`/`experience_level` equal the helper outputs for that set (fix checking + Requirement 3.4 consistency).
- Generate sets and remove a random subset client-side-style (drop keys) posted as `skill_scores_json`; assert removed skills are absent from the persisted set.
- Generate an extracted set plus a random added canonical id not already present; post the merged set and assert the added skill is persisted and that re-including an already-present id does not produce a duplicate key (merge-not-duplicate, Requirement 2.4).
- Generate an add-from-empty case: post a single added canonical skill with an empty resume extraction; assert the persisted set is exactly that added skill (Requirement 2.10).
- Generate the unedited/un-added case (post the extracted set unchanged) and assert the persisted result is identical to extraction for both paths (preservation).

### Integration Tests

- Full student flow: extract via `/student/skills/extract`, submit `/student/signup` with an edited `skill_scores_json` that includes an added skill, then load `/student/matches` and confirm the edited-and-added skill set drives `experience_level` and matching.
- Full mentor flow: extract via `/mentor/skills/extract`, submit `/mentor/signup` with an edited-and-added set, confirm the persisted `MentorProfile.skill_scores` reflects edits/removals/additions.
- Add-from-empty flow: with an extraction that yields no skills, add a skill via the picker and submit; confirm the persisted set contains exactly the added canonical skill (Requirement 2.10).
- HTMX re-init: after an extract swap replaces `#skill-chips-result`, editing a value, removing a chip, and adding a skill from the picker each update the hidden `skill_scores_json`; re-adding an existing skill updates its chip rather than duplicating it (DOM/manual verification, since no JS test harness exists).
