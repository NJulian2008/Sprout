# Implementation Plan

## Overview

This plan fixes the demo role switcher (`POST /demo/role` in `app/routers/demo.py`) so that
switching to a seeded profile lands on that profile's dashboard instead of the landing page.
It follows the exploratory bugfix workflow: write a failing bug-condition test and passing
preservation tests before the fix, apply the targeted fix, then re-run both to confirm the bug
is resolved with no regressions. Tests use FastAPI's `TestClient` against an in-memory SQLite DB,
mirroring the fixture pattern in `tests/test_flow_api.py`.

## Task Dependency Graph

- Task 1 (bug condition exploration test) and Task 2 (preservation tests) are independent and
  both run against the UNFIXED code first.
- Task 3 (the fix) depends on Tasks 1 and 2 being written and run.
  - Task 3.1 (implement) must precede 3.2 and 3.3.
  - Task 3.2 re-runs the Task 1 test; Task 3.3 re-runs the Task 2 tests.
- Task 4 (checkpoint) depends on Task 3 being complete.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "dependsOn": [] },
    { "wave": 2, "tasks": ["3.1"], "dependsOn": ["1", "2"] },
    { "wave": 3, "tasks": ["3.2", "3.3"], "dependsOn": ["3.1"] },
    { "wave": 4, "tasks": ["4"], "dependsOn": ["3.2", "3.3"] }
  ]
}
```

## Tasks

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Role Switcher Redirects to the Matching Dashboard
  - **IMPORTANT**: Write this property-based test BEFORE implementing the fix in `app/routers/demo.py`
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails** - a failing run here is the goal
  - **NOTE**: This test encodes the Expected Behavior; it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the role switcher lands on `/` instead of the role-specific dashboard
  - Add the test to a new module `tests/test_demo_role_redirect.py`, reusing the in-memory SQLite + `get_session` override + `_seed_all` fixture pattern from `tests/test_flow_api.py`, with `TestClient(app)` calls using `follow_redirects=False` so the 303 `Location` header can be asserted
  - **Scoped PBT Approach**: The seeded user set is small and deterministic, so drive the property across all seeded user ids by querying the test DB for every `User` and asserting per-role outcomes (this keeps the property reproducible rather than generating random ids)
  - For every seeded user: `POST /demo/role` with `{"user_id": user.id}` and assert `Location == "/student/dashboard"` when `user.role == "student"` and `Location == "/mentor/dashboard"` when `user.role == "mentor"` (from the Bug Condition / `isBugCondition` in design)
  - Assert the session is set: after the POST, a follow-up `GET` to the dashboard renders as the switched user (the operator should actually reach that profile's view)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - every switch currently redirects to `/`, proving the bug exists)
  - Document counterexamples found (e.g., "POST /demo/role with a seeded student id returns Location `/` instead of `/student/dashboard`"; same for a seeded mentor id) to confirm the root cause is the single unconditional `RedirectResponse(url="/", ...)` in `set_role`
  - Mark task complete when the test is written, run, and the failure is documented
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Switch Behavior and Fallback Unchanged
  - **IMPORTANT**: Follow observation-first methodology - observe behavior on UNFIXED code, then encode it
  - Add these tests to `tests/test_demo_role_redirect.py` using the same in-memory DB fixture
  - Observe: `POST /demo/reset` on unfixed code reseeds, clears the session, and redirects (303) to `/`; write a test asserting `Location == "/"` and that the session no longer carries the prior `user_id`
  - Observe: `POST /demo/llm_mode` with a valid mode (e.g. `off`) on unfixed code updates the mode and redirects (303) to `/demo`; write a test asserting `Location == "/demo"`
  - Observe: `GET /` with no active session on unfixed code renders the landing page with the "Continue as a Student" and "Continue as a Mentor" CTAs; write a test asserting both CTA strings are present
  - Observe: the student and mentor dashboards (reached directly) render the switched profile's mentorships/requests on unfixed code; write a test asserting that content renders
  - **Fallback (property-based over the non-bug domain)**: for `user_id` values that do NOT resolve to a seeded `User` (ids outside the seeded set, e.g. `max_seeded_id + 1` and a large id), assert `POST /demo/role` redirects (303) to `/` - this pins the graceful fallback where `isBugCondition` is false (from Preservation Requirements in design)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior that the fix must preserve)
  - Mark task complete when the tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3. Fix the role switcher redirect in `set_role` (POST /demo/role)

  - [ ] 3.1 Implement the fix
    - In `app/routers/demo.py`, change the `set_role` signature to request a DB session: `def set_role(request: Request, user_id: int = Form(...), db: Session = Depends(get_session)):` (`Session`, `Depends`, and `get_session` are already imported)
    - Keep `request.session["user_id"] = user_id` as the first action so the session is active before any dashboard renders (requirement 2.3)
    - Look up the switched user with `user = db.get(User, user_id)` (`User` is already imported)
    - Redirect by role: `student` → `RedirectResponse(url="/student/dashboard", status_code=303)`, `mentor` → `RedirectResponse(url="/mentor/dashboard", status_code=303)`
    - Fall back to `RedirectResponse(url="/", status_code=303)` when `user` is `None` or the role is neither `student` nor `mentor`, keeping the handler total
    - Do not modify `reset`, `set_llm_mode`, the landing route, or the dashboard routes
    - _Bug_Condition: isBugCondition(input) — input.user_id resolves to an existing student or mentor whose redirect target != dashboardFor(user.role)_
    - _Expected_Behavior: expectedBehavior(result) — set session then redirect 303 to /student/dashboard for students and /mentor/dashboard for mentors (from design)_
    - _Preservation: Preservation Requirements from design — reset→/, llm_mode→/demo, sessionless landing CTAs, dashboard data rendering, and unknown user_id fallback→/_
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Role Switcher Redirects to the Matching Dashboard
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior; when it passes it confirms the expected behavior is satisfied
    - Run the bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms the bug is fixed - students land on `/student/dashboard`, mentors on `/mentor/dashboard`, session is set)
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Switch Behavior and Fallback Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run the preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions - reset→/, llm_mode→/demo, sessionless landing CTAs, dashboard data rendering, and unknown-user fallback→/ all unchanged)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 4. Checkpoint - Ensure all tests pass
  - Run the full suite (`tests/`) with the project's test runner so both the new `tests/test_demo_role_redirect.py` and the existing integration tests (including `tests/test_flow_api.py`, which exercises `POST /demo/role`) pass
  - Confirm the fix introduced no regressions across the suite
  - Ensure all tests pass; ask the user if questions arise

## Notes

- The fix is confined to `set_role` in `app/routers/demo.py`; `reset`, `set_llm_mode`, the landing
  route, and both dashboard routes are intentionally left untouched.
- Property 1 (Bug Condition / Expected Behavior) validates requirements 2.1, 2.2, 2.3; Property 2
  (Preservation) validates requirements 3.1, 3.2, 3.3, 3.4.
- The existing `tests/test_flow_api.py` already calls `POST /demo/role` and relies on the session
  being set; the fix keeps that behavior, so that suite should continue to pass unchanged.
- Run `POST` requests in tests with `follow_redirects=False` to assert the 303 `Location` header
  directly.
