# Requirements Document

## Introduction

This feature improves the account and session user experience of the Sprout mentor-matching demo app across four related capabilities: (1) letting students enter their own name during signup instead of being assigned a hardcoded default, (2) guaranteeing the app presents a signed-out starting state so a fresh visitor is never treated as an existing user, (3) making the Sprout brand logo route a signed-in user to their role-appropriate dashboard rather than the landing/signup page, and (4) adding an explicit sign-out action — available on both the normal website and the demo operator panel — that clears the session and returns to the landing page without reseeding the database.

Sprout is a FastAPI + Jinja2 + HTMX demo. There is no password authentication: "signed in" means the server-side session cookie holds a `user_id` (resolved to a `User` by `current_user`), and "signed out" means the session has no `user_id`. These requirements operate entirely at the session level and MUST NOT introduce password-based authentication.

## Glossary

- **Sprout_App**: The FastAPI web application serving the Sprout mentor-matching demo, including its page routes, templates, and session handling.
- **Session**: The signed cookie managed by the application's session middleware, holding at most a `user_id` (and, for students, a `request_id`).
- **Signed_In**: The state in which the current Session contains a `user_id` that resolves to an existing User.
- **Signed_Out**: The state in which the current Session contains no `user_id`, so `current_user` resolves to no User.
- **User**: A person record in the `user` table, having a `role` of either `student` or `mentor` and a `name`.
- **Student_Signup_Form**: The HTML form rendered at `GET /student/signup` for creating a student User and StudentRequest.
- **Student_Signup_Handler**: The route handling `POST /student/signup` that creates the student User and signs the visitor in.
- **Brand_Logo**: The "🌱 Sprout" link in the top bar defined in the base template.
- **Landing_Page**: The page served at `GET /` presenting the student and mentor signup calls to action.
- **Student_Dashboard**: The page served at `GET /student/dashboard`.
- **Mentor_Dashboard**: The page served at `GET /mentor/dashboard`.
- **Sign_Out_Control**: A user-facing control on the normal website that triggers sign-out.
- **Demo_Panel**: The operator page served at `GET /demo` for switching roles, resetting data, and toggling LLM mode.
- **Demo_Sign_Out_Control**: A control on the Demo_Panel that triggers sign-out.
- **Sign_Out_Action**: The server operation that clears the Session and returns the visitor to the Landing_Page.
- **Reset_Action**: The existing `POST /demo/reset` operation that reseeds the database and clears the Session.

## Requirements

### Requirement 1: Student enters their own name

**User Story:** As a student signing up, I want to enter my own name, so that my profile and matches show who I actually am instead of a placeholder.

#### Acceptance Criteria

1. THE Student_Signup_Form SHALL display a text input for the student name.
2. THE Student_Signup_Form SHALL mark the name input as required so the browser blocks submission when the name input is empty.
3. WHEN a student submits the Student_Signup_Form with a non-empty name value, THE Student_Signup_Handler SHALL create the student User with `name` set to the submitted name value.
4. IF the Student_Signup_Handler receives a request whose name value is missing or contains only whitespace, THEN THE Student_Signup_Handler SHALL create the student User with `name` set to "Demo Student".
5. THE Student_Signup_Form SHALL place the name input so that it is visible before the form's submit control without horizontal scrolling at a viewport width of 375 pixels.

### Requirement 2: Signed-out starting state

**User Story:** As a first-time visitor, I want the app to start signed out, so that I am not mistaken for an existing user before I choose a role.

#### Acceptance Criteria

1. WHEN a visitor loads any page with a Session that contains no `user_id`, THE Sprout_App SHALL render that page in the Signed_Out state.
2. WHILE the Session is in the Signed_Out state, THE Sprout_App SHALL display an indication that no user is signed in.
3. THE Sprout_App SHALL establish a `user_id` in the Session only in response to a student signup submission, a mentor signup submission, or a Demo_Panel role selection.
4. WHEN the Sign_Out_Action completes, THE Sprout_App SHALL place the Session in the Signed_Out state.

### Requirement 3: Brand logo routes by sign-in state

**User Story:** As a signed-in user, I want the Sprout logo to take me to my dashboard, so that I return to my workspace instead of the signup landing page.

#### Acceptance Criteria

1. WHILE the Session is in the Signed_Out state, THE Brand_Logo SHALL link to the Landing_Page.
2. WHILE the Session is Signed_In as a User whose role is `student`, THE Brand_Logo SHALL link to the Student_Dashboard.
3. WHILE the Session is Signed_In as a User whose role is `mentor`, THE Brand_Logo SHALL link to the Mentor_Dashboard.

### Requirement 4: Sign out from the normal website

**User Story:** As a signed-in user on the website, I want a way to sign out, so that I can return to the signup page and start over as a different role.

#### Acceptance Criteria

1. WHILE the Session is Signed_In, THE Sprout_App SHALL display the Sign_Out_Control on the normal website.
2. WHILE the Session is in the Signed_Out state, THE Sprout_App SHALL hide the Sign_Out_Control.
3. WHEN a user activates the Sign_Out_Control, THE Sprout_App SHALL clear the Session.
4. WHEN a user activates the Sign_Out_Control, THE Sprout_App SHALL redirect the browser to the Landing_Page.
5. WHEN a user activates the Sign_Out_Control, THE Sprout_App SHALL preserve all existing database records.

### Requirement 5: Sign out from the demo panel

**User Story:** As a demo operator, I want to sign out from the demo panel, so that I can get back to the signed-out landing page without reseeding the database.

#### Acceptance Criteria

1. THE Demo_Panel SHALL display the Demo_Sign_Out_Control.
2. WHEN an operator activates the Demo_Sign_Out_Control, THE Sprout_App SHALL clear the Session.
3. WHEN an operator activates the Demo_Sign_Out_Control, THE Sprout_App SHALL redirect the browser to the Landing_Page.
4. WHEN an operator activates the Demo_Sign_Out_Control, THE Sprout_App SHALL preserve all existing database records.
5. THE Demo_Panel SHALL present the Demo_Sign_Out_Control as a control distinct from the Reset_Action control.
