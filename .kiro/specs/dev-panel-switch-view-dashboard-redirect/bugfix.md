# Bugfix Requirements Document

## Introduction

The demo operator panel includes a role switcher that sets the active user for the session. When the operator selects a profile and clicks "Switch", a confirmation appears in the top-right indicating the active profile changed, but the app then lands on the home/landing page (`index.html`). That landing page only offers "Continue as a Student" and "Continue as a Mentor" buttons, both of which route to the profile-creation (signup) flows — not to the selected profile's existing dashboard.

This makes the switch feel broken: the operator has impersonated a real seeded user but is pushed back toward creating a brand-new profile. The expected outcome is to land on the switched profile's dashboard (student or mentor) so the operator immediately sees that user's view.

The defect lives in the `POST /demo/role` handler (`app/routers/demo.py`), which unconditionally redirects to `/` after setting `session["user_id"]`.

## Bug Analysis

### Current Behavior (Defect)

After the role switcher sets the session's active user, the app redirects to the landing page regardless of the switched user's role.

1.1 WHEN the operator switches to a student profile via the demo role switcher THEN the system redirects to the landing page (`/`) that shows the "Continue as a Student / Continue as a Mentor" buttons
1.2 WHEN the operator switches to a mentor profile via the demo role switcher THEN the system redirects to the landing page (`/`) that shows the "Continue as a Student / Continue as a Mentor" buttons
1.3 WHEN the operator follows a button on the landing page reached after switching THEN the system routes to the signup/create-profile flow instead of the switched profile's dashboard

### Expected Behavior (Correct)

After the role switcher sets the session's active user, the app should navigate directly to that user's dashboard based on their role.

2.1 WHEN the operator switches to a student profile via the demo role switcher THEN the system SHALL redirect to the student dashboard (`/student/dashboard`) for the switched profile
2.2 WHEN the operator switches to a mentor profile via the demo role switcher THEN the system SHALL redirect to the mentor dashboard (`/mentor/dashboard`) for the switched profile
2.3 WHEN the operator switches to a profile THEN the system SHALL set the session's active user to the selected profile before redirecting so the dashboard renders that profile's view

### Unchanged Behavior (Regression Prevention)

The fix must only change where the role switcher redirects; all other demo-panel and routing behavior must stay the same.

3.1 WHEN the operator uses the "Reset to seed data" action THEN the system SHALL CONTINUE TO reseed the database, clear the session, and redirect to the landing page (`/`)
3.2 WHEN the operator toggles the LLM mode THEN the system SHALL CONTINUE TO update the mode and redirect back to the demo panel (`/demo`)
3.3 WHEN a visitor with no active session opens the landing page (`/`) THEN the system SHALL CONTINUE TO show the "Continue as a Student / Continue as a Mentor" options
3.4 WHEN the student or mentor dashboard is requested for the switched profile THEN the system SHALL CONTINUE TO render that profile's existing mentorships, requests, and related data unchanged
