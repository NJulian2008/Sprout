# Demo Role Switcher Dashboard Redirect Bugfix Design

## Overview

The demo operator panel's role switcher (`POST /demo/role`) lets an operator impersonate a seeded user by writing their id into the session cookie. The handler correctly sets `session["user_id"]` but then unconditionally redirects to the landing page (`/`). The landing page (`index.html`) only offers "Continue as a Student" and "Continue as a Mentor" buttons, both of which lead to the profile-creation (signup) flows. The net effect: switching to a real seeded profile dumps the operator back at a page that pushes them to create a brand-new profile, which makes the switch feel broken.

The fix is targeted and minimal: after setting the session's active user, look up that user's role and redirect to the role-appropriate dashboard — `/student/dashboard` for a student and `/mentor/dashboard` for a mentor — instead of `/`. To look up the role, the handler needs a database session, which it currently does not request. No other demo-panel behavior (reset, LLM toggle) and no landing-page behavior changes.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a `POST /demo/role` request that sets the session to a valid, existing user (student or mentor) and is then redirected to `/` instead of that user's dashboard.
- **Property (P)**: The desired behavior for the bug condition — after setting the session, the response redirects (HTTP 303) to the dashboard matching the switched user's role (`/student/dashboard` or `/mentor/dashboard`).
- **Preservation**: Existing behavior that must stay unchanged — the reset action (`POST /demo/reset`), the LLM-mode toggle (`POST /demo/llm_mode`), the landing page (`GET /`) for sessionless visitors, and the dashboards' own rendering of a profile's data.
- **set_role**: The handler for `POST /demo/role` in `app/routers/demo.py` that writes `user_id` into the session and returns a `RedirectResponse`.
- **current_user**: The helper in `app/templating.py` that returns the `User` for `session["user_id"]`, or `None` if unset/missing. Both dashboards use it to decide whose data to render.
- **role**: The `User.role` string column (`"student"` or `"mentor"`) that determines which dashboard is appropriate for a switched profile.

## Bug Details

### Bug Condition

The bug manifests when the operator submits the role switcher form for any existing seeded user. The `set_role` handler sets `session["user_id"]` to the selected user's id but then returns `RedirectResponse(url="/", ...)` regardless of that user's role. Because the destination does not depend on the role, both students and mentors are sent to the landing page rather than their dashboards.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DemoRoleRequest   # { user_id: int }
  OUTPUT: boolean

  LET user = lookupUser(input.user_id)

  RETURN user IS NOT NULL
         AND user.role IN ['student', 'mentor']
         AND redirectTargetOf(set_role(input)) != dashboardFor(user.role)
END FUNCTION

# dashboardFor('student') = '/student/dashboard'
# dashboardFor('mentor')  = '/mentor/dashboard'
```

### Examples

- **Switch to a student** — Operator selects a seeded student and clicks "Switch". Expected: session set to that student and redirect to `/student/dashboard` showing their mentorships. Actual: redirect to `/`, which offers only "Continue as a Student / Continue as a Mentor".
- **Switch to a mentor** — Operator selects a seeded mentor and clicks "Switch". Expected: session set to that mentor and redirect to `/mentor/dashboard` showing their incoming requests and active mentorships. Actual: redirect to `/`.
- **Follow-through from landing** — After the broken redirect lands on `/`, clicking either CTA routes into the signup/create-profile flow rather than the switched profile's dashboard.
- **Edge case — unknown user_id** — A submitted `user_id` with no matching `User` row has no role to key off. Expected correct behavior: fall back to the landing page (`/`) rather than error, since there is no dashboard to show.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `POST /demo/reset` must continue to reseed the database, clear the session, and redirect to `/`.
- `POST /demo/llm_mode` must continue to update the mode (when valid) and redirect to `/demo`.
- `GET /` for a visitor with no active session must continue to render the landing page with the "Continue as a Student / Continue as a Mentor" options.
- `GET /student/dashboard` and `GET /mentor/dashboard` must continue to render the switched profile's existing mentorships, requests, deliverables, and related data exactly as before — the fix changes only how the operator arrives at these routes, not what they render.
- Setting `session["user_id"]` to the selected profile must still happen before redirecting (requirement 2.3), so the dashboard renders that profile's view.

**Scope:**
All behavior that does NOT involve the `set_role` redirect target must be completely unaffected by this fix. This includes:
- The demo reset and LLM-mode toggle handlers.
- The landing page and signup flows.
- The dashboard page handlers and their data queries.
- Session read/write semantics everywhere other than the `set_role` redirect.

## Hypothesized Root Cause

Based on the bug description and code inspection, the cause is confirmed to be a single unconditional redirect:

1. **Redirect target independent of role (primary cause)**: `set_role` returns `RedirectResponse(url="/", status_code=303)` with no reference to the switched user. The landing page is never a useful destination for an already-identified user, so every switch — student or mentor — lands on the create-profile page.

2. **Handler lacks a DB session to resolve the role**: `set_role` currently takes only `request` and the `user_id` form field; it has no `Session` dependency, so it cannot look up `User.role` to choose a destination. The fix must add a `Session = Depends(get_session)` parameter (consistent with every other handler in the file).

3. **No fallback for a missing/invalid user (secondary consideration)**: Because the current code never looks the user up, it never has to handle a `user_id` with no matching row. Once the lookup is added, an absent user must degrade gracefully to `/`.

## Correctness Properties

Property 1: Bug Condition - Role Switcher Redirects to the Matching Dashboard

_For any_ `POST /demo/role` request where the bug condition holds (isBugCondition returns true — the selected `user_id` resolves to an existing student or mentor), the fixed `set_role` function SHALL set `session["user_id"]` to that id and return an HTTP 303 redirect to `/student/dashboard` when the user's role is `student` and to `/mentor/dashboard` when the user's role is `mentor`.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Switch Behavior and Fallback Unchanged

_For any_ input where the bug condition does NOT hold (isBugCondition returns false) — including the demo reset action, the LLM-mode toggle, a sessionless landing-page visit, the dashboard page renders, and a `set_role` call whose `user_id` does not resolve to an existing user — the fixed code SHALL produce the same result as the original code, preserving reset→`/`, llm_mode→`/demo`, landing-page content for sessionless visitors, dashboard data rendering, and a graceful fallback to `/` when no user is found.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `app/routers/demo.py`

**Function**: `set_role` (`POST /demo/role`)

**Specific Changes**:

1. **Add a database session dependency**: Change the signature to request a session the same way the other handlers do:
   - `def set_role(request: Request, user_id: int = Form(...), db: Session = Depends(get_session)):`
   - `Session`, `Depends`, and `get_session` are already imported in this module, so no new imports are needed.

2. **Set the session before redirecting**: Keep `request.session["user_id"] = user_id` as the first action, preserving requirement 2.3 (session is active before the dashboard renders).

3. **Resolve the switched user's role**: Look up the user with `db.get(User, user_id)` (`User` is already imported). Read `user.role` to decide the destination.

4. **Choose the redirect target by role**:
   - `student` → `RedirectResponse(url="/student/dashboard", status_code=303)`
   - `mentor` → `RedirectResponse(url="/mentor/dashboard", status_code=303)`

5. **Fall back gracefully**: If `db.get(...)` returns `None` (no such user) or the role is neither `student` nor `mentor`, redirect to `/` as before. This keeps the handler total and avoids introducing a new error path.

Illustrative shape of the fixed handler (final code produced during implementation):
```python
@router.post("/demo/role")
def set_role(
    request: Request,
    user_id: int = Form(...),
    db: Session = Depends(get_session),
):
    """Set the session's active user and land on that user's dashboard."""
    request.session["user_id"] = user_id
    user = db.get(User, user_id)
    if user and user.role == "student":
        return RedirectResponse(url="/student/dashboard", status_code=303)
    if user and user.role == "mentor":
        return RedirectResponse(url="/mentor/dashboard", status_code=303)
    return RedirectResponse(url="/", status_code=303)
```

No other function, template, or route is modified. `reset`, `set_llm_mode`, the landing route, and both dashboard routes are untouched.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on the unfixed code, then verify the fix redirects correctly by role and preserves all other behavior. Tests use FastAPI's `TestClient` (as the existing suite in `tests/` does) with redirects disabled so the `Location` header of the 303 response can be asserted directly.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute it, we re-hypothesize.

**Test Plan**: Seed the database, issue `POST /demo/role` with a known student id and a known mentor id, and assert the redirect `Location`. Run these against the UNFIXED code to observe that both land on `/`.

**Test Cases**:
1. **Switch-to-student redirect**: POST a seeded student's id; assert `Location == "/student/dashboard"` (will fail on unfixed code — currently `/`).
2. **Switch-to-mentor redirect**: POST a seeded mentor's id; assert `Location == "/mentor/dashboard"` (will fail on unfixed code — currently `/`).
3. **Session is set**: After the POST, assert a follow-up GET to the dashboard renders as the switched user (will fail on unfixed code because the operator never reaches the dashboard).
4. **Unknown user_id fallback**: POST an id with no matching `User`; assert `Location == "/"` (passes on unfixed code; pins the fallback so the fix does not regress it).

**Expected Counterexamples**:
- For a seeded student and a seeded mentor, the redirect `Location` is `/` rather than the role-specific dashboard.
- Root cause confirmed if both counterexamples trace to the single unconditional `RedirectResponse(url="/", ...)` in `set_role`.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := set_role_fixed(input)
  ASSERT sessionUserId(result) == input.user_id
  ASSERT redirectTargetOf(result) == dashboardFor(lookupUser(input.user_id).role)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT behavior_original(input) == behavior_fixed(input)
END FOR
# Covers: POST /demo/reset, POST /demo/llm_mode, GET / (sessionless),
# GET /student/dashboard, GET /mentor/dashboard, and set_role with an unknown user_id.
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many `user_id` values (valid students, valid mentors, and non-existent ids) across the input domain.
- It catches edge cases that hand-written unit tests might miss, such as ids at the boundary of the seeded set.
- It provides strong guarantees that non-switch endpoints and the fallback path are unchanged.

**Test Plan**: Observe behavior on the UNFIXED code first for reset, LLM toggle, the sessionless landing page, and dashboard rendering, then write tests capturing that behavior so the fix must keep it identical.

**Test Cases**:
1. **Reset preservation**: Observe `POST /demo/reset` reseeds, clears the session, and redirects to `/` on unfixed code; assert the same after the fix.
2. **LLM toggle preservation**: Observe `POST /demo/llm_mode` with a valid mode updates it and redirects to `/demo` on unfixed code; assert the same after the fix.
3. **Sessionless landing preservation**: Observe `GET /` with no session renders the "Continue as a Student / Continue as a Mentor" CTAs on unfixed code; assert the same after the fix.
4. **Dashboard data preservation**: Observe the student and mentor dashboards render the switched profile's mentorships/requests on unfixed code (reached directly); assert the same content after the fix.

### Unit Tests

- `POST /demo/role` with a seeded student id redirects (303) to `/student/dashboard`.
- `POST /demo/role` with a seeded mentor id redirects (303) to `/mentor/dashboard`.
- `POST /demo/role` with a non-existent id redirects (303) to `/` (graceful fallback).
- Session's `user_id` equals the submitted id after the switch, regardless of destination.
- `POST /demo/reset` and `POST /demo/llm_mode` redirect to `/` and `/demo` respectively (unchanged).

### Property-Based Tests

- Generate ids drawn from the seeded users and assert the redirect target matches `dashboardFor(user.role)` for every generated id.
- Generate ids outside the seeded set and assert the redirect target is always `/`.
- Across all generated valid ids, assert `session["user_id"]` is always set to the submitted id before the redirect.

### Integration Tests

- Full operator flow: open `/demo`, switch to a seeded student, follow the redirect, and confirm the student dashboard renders that student's mentorships.
- Full operator flow: switch to a seeded mentor, follow the redirect, and confirm the mentor dashboard renders that mentor's incoming requests and active mentorships.
- Switch student → switch mentor in sequence and confirm each lands on the correct dashboard, verifying no cross-contamination between switches.
