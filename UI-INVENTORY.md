# Sprout UI inventory

## Screens and templates

| Template | Screen | Main data and interactions |
|---|---|---|
| `base.html` | Shared shell | Signed-in header with left-aligned wordmark, Dashboard, Calendar, Messages and role-specific Profile; signup keeps only the Demo panel link |
| `index.html` | Landing | Student and mentor entry points |
| `student/signup.html` | Student onboarding | Goal, specialty, resume upload, availability and three priorities; posts to `/student/signup` for skill review, then posts edited skills to create the request |
| `student/matches.html` | Student matches | Up to three mentor cards; `POST /student/requests` with `match_id` and an optional note |
| `student/dashboard.html` | Student dashboard fallback | Redirects students with a mentorship to its dashboard; otherwise offers the matches flow |
| `student/profile.html` | Student profile | Edit name, major, year and short bio |
| `mentor/signup.html` | Mentor onboarding | Name and profile, specialties, resume upload, editable confidence scores, outcomes, availability and priorities |
| `mentor/dashboard.html` | Mentor dashboard | Awaiting and active students in one clickable roster with next-meeting details; new requests appear below with accept, decline and scheduling actions |
| `mentor/profile.html` | Mentor profile | Three impact counts, skill list, current and past students, testimonials, and an owner-only preference to accept one additional student |
| `mentorship/workspace.html` | Mentorship dashboard | Student progress checklist, next-meeting deliverables, meetings, mutual confirmation, and a low-key end-connection control on one page |
| `messages.html` | Messages | Conversation placeholder for the current or latest mentorship |
| `availability.html` | Availability | Day/time toggles and saved confirmation |
| `demo/panel.html` | Demo panel | Switch between student and professional views, choose an account, reset confirmation and existing LLM modes |
| `partials/skill_chips.html` | Shared skill editor | Confidence control, removal/undo, suggestions and hidden `skill_scores_json` value |
| `partials/skill_chip_item.html` | One skill | Accessible inline confidence editor |
| `partials/availability_grid.html` | Shared availability grid | Accessible toggle buttons and the hidden `availability` field |
| `partials/confirm_decline.html` | Shared decision panel | `choice=confirm` or `choice=decline` to `/mentorships/{id}/decision` |

## Route and data notes

- Student signup uses an optional `stage` field to pause after resume parsing, collect confidence edits, and continue through the same endpoint.
- `skill_scores_json` remains a skill-ID to confidence mapping. The overall experience estimate used in matching is derived from those scores; there is no per-skill level control in the UI.
- `/student/dashboard` redirects to the student's latest mentorship dashboard when one exists. Choosing a mentor opens that dashboard directly.
- `/student/profile` updates the student's name, major, year and short bio.
- The student resume parser accepts the formats already supported by the backend: PDF, DOCX and TXT.
- Mentor onboarding uses the same PDF, DOCX and TXT upload and skill-confidence review flow as student onboarding. New mentor profiles default to one student; mentors can opt into one additional student from their profile.
- Students can propose a deliverable for the next scheduled meeting. Mentors can edit and approve it; either participant can mark an approved deliverable complete.
- Either mentorship participant can end a pending or active connection. If the student includes an optional testimonial, it is saved with the mentor's profile testimonials.
- A mentor can decline a new request through the existing decision route. The handler now records that transition from `requested` to `ended`; decisions after the intro keep the existing state-machine behavior.
- Availability saving and testimonial completion keep their existing routes and add query flags only for success messages.

## Static files

- `app/static/styles.css` — shared green-and-white design system and responsive layouts.
- `app/static/ui.js` — onboarding steps, confidence editing, drop-zone feedback, demo account filtering and request slot disclosure.
- `app/static/grid.js` — keyboard-accessible availability toggles.
- `app/static/htmx.min.js` — vendored HTMX 2.x.
- `app/static/images/Sprout_Text.svg` and `Sprout_Main.svg` — copied unchanged from the supplied files.
- `app/static/avatars/avatar_{id}.svg` — existing demo profile imagery.
