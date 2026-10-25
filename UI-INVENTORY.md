# Sprout UI inventory

## Screens and templates

| Template | Screen | Main data and interactions |
|---|---|---|
| `base.html` | Shared shell | Preserved SVG wordmark, role label, desktop links and mobile bottom navigation |
| `index.html` | Landing | Student and mentor entry points |
| `student/signup.html` | Student onboarding | Goal, specialty, resume upload, availability and three priorities; posts to `/student/signup` for skill review, then posts edited skills to create the request |
| `student/matches.html` | Student matches | Up to three mentor cards; `POST /student/requests` with `match_id` and an optional note |
| `student/dashboard.html` | Student dashboard | Mentorship status, milestones, due work and pending decision actions |
| `mentor/signup.html` | Mentor onboarding | Profile, specialties, pasted resume, editable skills, outcomes, availability and priorities; HTMX extraction uses `/mentor/skills/extract` |
| `mentor/dashboard.html` | Mentor dashboard | Expandable New requests, Awaiting and Active sections; accept and decline, slot selection and workspace links |
| `mentor/profile.html` | Mentor profile | Three impact counts, skill list, current and past students, testimonials |
| `mentorship/workspace.html` | Mentorship workspace | Deliverables, meetings, mutual confirmation, testimonial completion and the planned messaging empty state |
| `availability.html` | Availability | Day/time toggles and saved confirmation |
| `demo/panel.html` | Demo tools | Role selection, reset confirmation and existing LLM modes |
| `partials/skill_chips.html` | Shared skill editor | Confidence and level controls, removal/undo, suggestions, and hidden `skill_scores_json` / `skill_levels_json` values |
| `partials/skill_chip_item.html` | One skill | Accessible inline editor for confidence and experience level |
| `partials/availability_grid.html` | Shared availability grid | Accessible toggle buttons and the hidden `availability` field |
| `partials/confirm_decline.html` | Shared decision panel | `choice=confirm` or `choice=decline` to `/mentorships/{id}/decision` |

## Route and data notes

- Existing route paths and form names are kept. Student signup now uses an optional `stage` field to pause after resume parsing, collect skill edits, and continue through the same endpoint.
- `skill_scores_json` remains a skill-ID to confidence mapping. New optional `skill_levels_json` values are stored separately on student requests and mentor profiles. Existing submissions without either field keep their parse-on-submit behavior.
- The student resume parser accepts the formats already supported by the backend: PDF, DOCX and TXT.
- A mentor can decline a new request through the existing decision route. The handler now records that transition from `requested` to `ended`; decisions after the intro keep the existing state-machine behavior.
- Availability saving and testimonial completion keep their existing routes and add query flags only for success messages.

## Static files

- `app/static/styles.css` — shared green-and-white design system and responsive layouts.
- `app/static/ui.js` — onboarding steps, editable skills, drop-zone feedback, tabs and request slot disclosure.
- `app/static/grid.js` — keyboard-accessible availability toggles.
- `app/static/htmx.min.js` — vendored HTMX 2.x.
- `app/static/images/Sprout_Text.svg` and `Sprout_Main.svg` — copied unchanged from the supplied files.
- `app/static/avatars/avatar_{id}.svg` — existing demo profile imagery.
