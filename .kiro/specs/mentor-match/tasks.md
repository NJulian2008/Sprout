# Implementation Plan: Mentor–Student Matching Platform

## Overview

Build the full mentor-student matching platform for HackOHI/O 2026 based on the tech stack spec and hackathon spec v5. Stack: FastAPI + SQLAlchemy 2.0 (sync) + SQLite + Pydantic v2 + Jinja2 + HTMX. No build step, one process, runs on a laptop.

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["1"]},
    {"wave": 2, "tasks": ["2", "4", "5"]},
    {"wave": 3, "tasks": ["3"]},
    {"wave": 4, "tasks": ["6", "7"]},
    {"wave": 5, "tasks": ["8", "9", "10"]},
    {"wave": 6, "tasks": ["11"]},
    {"wave": 7, "tasks": ["12"]},
    {"wave": 8, "tasks": ["13"]},
    {"wave": 9, "tasks": ["14", "15", "16", "17", "18"]},
    {"wave": 10, "tasks": ["19"]},
    {"wave": 11, "tasks": ["20", "21", "22", "23"]},
    {"wave": 12, "tasks": ["24", "25", "26", "27", "28"]}
  ],
  "dependencies": {
    "2": ["1"],
    "3": ["2"],
    "4": ["1"],
    "5": ["1"],
    "6": ["4", "5"],
    "7": ["1"],
    "8": ["6", "7"],
    "9": ["1"],
    "10": ["1"],
    "11": ["6", "4"],
    "12": ["3", "6", "8"],
    "13": ["3", "5", "9"],
    "14": ["13"],
    "15": ["8", "11", "13"],
    "16": ["11", "13"],
    "17": ["9", "10", "13"],
    "18": ["4", "13"],
    "19": ["13"],
    "20": ["19"],
    "21": ["19"],
    "22": ["19"],
    "23": ["19"],
    "24": ["8"],
    "25": ["6"],
    "26": ["9"],
    "27": ["11"],
    "28": ["15", "16", "17", "18"]
  }
}
```

## Tasks

- [x] 1. Initialize project structure and dependencies
  - Create `pyproject.toml` with all pinned dependencies: fastapi>=0.115, uvicorn[standard]>=0.30, pydantic>=2.9, pydantic-settings>=2.5, sqlalchemy>=2.0.35, jinja2>=3.1, python-multipart>=0.0.9, itsdangerous>=2.2, httpx>=0.27, python-dotenv>=1.0, pypdf>=4.0, rapidfuzz>=3.9, pytest>=8.0, ruff>=0.6
  - Create the full directory tree: `app/db/`, `app/schemas/`, `app/routers/`, `app/services/`, `app/data/`, `app/templates/student/`, `app/templates/mentor/`, `app/templates/mentorship/`, `app/templates/demo/`, `app/templates/partials/`, `app/static/avatars/`, `tests/`
  - Create `Makefile` with `run`, `seed`, `reset`, `test` targets
  - Create `.env.example` documenting all env vars (`DATABASE_URL`, `SESSION_SECRET`, `LLM_MODE`, `DEMO_MODE`, `COPILOT_TOKEN`)
  - Create `requirements.txt` as pip fallback (same pins)
  - Create skeleton `__init__.py` files in every package
  - Create `README.md` with setup instructions and make targets

- [x] 2. SQLAlchemy ORM models (`app/db/models.py`)
  - Depends on: 1
  - Implement all 10 tables using SQLAlchemy 2.0 `Mapped[...]` / `mapped_column` declarative style: `User`, `MentorProfile`, `StudentRequest`, `Match`, `Mentorship`, `Meeting`, `Deliverable`, `Testimonial`, `Message`, `LLMCache`
  - Use `MutableDict.as_mutable(JSON)` for all JSON dict columns (`skill_scores`, `score_breakdown`) to prevent silent mutation bugs
  - Use `MutableList.as_mutable(JSON)` for JSON list columns (`outcomes`, `availability`, `top3`, `skills_to_learn`, `progress_notes`, `next_deliverable_ids`)
  - All enum-like fields stored as `String` columns (no native enums)
  - Integer autoincrement PKs (`id: Mapped[int] = mapped_column(primary_key=True)`)
  - `created_at` / `started_at` / `completed_at` use `datetime` with UTC default

- [x] 3. Database session and engine (`app/db/session.py`)
  - Depends on: 2
  - Create engine: `create_engine("sqlite:///app.db", connect_args={"check_same_thread": False})`
  - Register `PRAGMA foreign_keys=ON` and `PRAGMA journal_mode=WAL` via `event.listens_for(engine, "connect")`
  - Implement `SessionLocal = sessionmaker(engine, expire_on_commit=False)`
  - Implement `get_session()` FastAPI dependency (yields Session, closes on exit)
  - Implement `reset_db()` = `Base.metadata.drop_all(engine)` + `Base.metadata.create_all(engine)` + `seed()`

- [x] 4. Pydantic schemas (`app/schemas/`)
  - Depends on: 1
  - `user.py`: `UserOut`, `UserCreate` with `role` validation ("student"|"mentor")
  - `mentor.py`: `MentorProfileCreate`, `MentorProfileOut`, `MentorSignupRequest` (full signup form)
  - `student.py`: `StudentRequestCreate`, `StudentRequestOut` with `goal_type` and `cadence` validation
  - `match.py`: `MatchOut`, `MatchCard` (what the UI needs per card)
  - `mentorship.py`: `MentorshipOut`, `DeliverableCreate`, `DeliverableOut`, `DeliverableUpdate`, `MeetingOut`, `MeetingUpdate`, `TestimonialCreate`, `TestimonialOut`, `DecisionRequest`
  - `ai.py`: `SkillScores` (validator: keys must be in taxonomy, values clamped 0.0–1.0, rounded to 2 decimals, unknown keys dropped), `MatchExplanation`, `MatchExplanations` (list of 3, mentor ids validated against provided top-5)
  - All schemas: `model_config = ConfigDict(from_attributes=True)`

- [x] 5. App settings (`app/settings.py`)
  - Depends on: 1
  - `pydantic-settings` `Settings` class reading from `.env`: `database_url: str`, `session_secret: str`, `llm_mode: str = "off"` (live/off/cached), `demo_mode: str = "normal"`, `copilot_token: str = ""`
  - Single module-level `settings = Settings()` instance

- [x] 6. Skills taxonomy and service (`app/data/skills_taxonomy.json` + `app/services/skills.py`)
  - Depends on: 4, 5
  - Create `skills_taxonomy.json` with ~60 skill entries `[{id, label, aliases[]}]` covering: python, javascript, typescript, react, nodejs, sql, postgres, sqlite, git, docker, fastapi, flask, django, machine_learning, deep_learning, pytorch, tensorflow, data_analysis, pandas, numpy, nlp, computer_vision, java, cpp, c, rust, go, kotlin, swift, ios, android, aws, gcp, azure, devops, cicd, linux, bash, html, css, rest_api, graphql, system_design, algorithms, data_structures, statistics, probability, research, technical_writing, project_management, agile, product_management, ux_design, figma, unity, opencv, robotics, embedded, networking, cybersecurity, blockchain, web3
  - Implement `load_taxonomy() -> dict[str, dict]` (cached at module level)
  - Implement `normalize_skill_id(text: str) -> str | None` (exact match first, then alias scan, then rapidfuzz if available)
  - Implement `experience_score(skills: dict[str, float], k: int = 5) -> float` (mean of top-k values)
  - Implement `experience_level(score: float) -> str` (thresholds 0.35 / 0.65 → beginner / intermediate / advanced)
  - Implement `fallback_extract(text: str) -> dict[str, float]` (scan text for taxonomy ids and aliases, confidence = `min(0.7, 0.3 + 0.1 * mention_count)`)

- [x] 7. Config constants (`app/config_constants.py`)
  - Depends on: 1
  - Define all matching weights and thresholds as named constants: `WEIGHT_SKILLS_FIT = 0.45`, `WEIGHT_OUTCOME_FIT = 0.30`, `WEIGHT_AVAIL_FIT = 0.25`, `SKILLS_FIT_COVERAGE_WEIGHT = 0.7`, `SKILLS_FIT_LEVEL_WEIGHT = 0.3`, `COVER_HEADROOM = 0.30`, `LEVEL_FIT_MIN_GAP = 0.15`, `LEVEL_FIT_MAX_GAP = 0.45`, `LEVEL_FIT_LOWER_BOUND = -0.15`, `LEVEL_FIT_UPPER_BOUND = 0.85`, `AVAIL_BLOCKS_FOR_FULL_SCORE = 3`, `LEVEL_BEGINNER_THRESHOLD = 0.35`, `LEVEL_ADVANCED_THRESHOLD = 0.65`, `EXPERIENCE_SCORE_TOP_K = 5`

- [x] 8. Matching service (`app/services/matching.py`)
  - Depends on: 6, 7
  - Define `StudentProfile` and `MentorCandidate` dataclasses (plain Python, no ORM import)
  - Implement `cover(m: float, st: float) -> float` per spec formula
  - Implement `level_fit(gap: float) -> float` per spec piecewise formula
  - Implement `skills_fit(student: StudentProfile, mentor: MentorCandidate) -> tuple[float, dict]`
  - Implement `outcome_fit(student_goal_type: str, mentor_outcomes: list[str]) -> float`
  - Implement `availability_fit(student_avail: list[str], mentor_avail: list[str]) -> float`
  - Implement `compute_score(student, mentor) -> tuple[float, dict]` (weighted sum → 0–100)
  - Implement `apply_hard_filters(student, mentors: list[MentorCandidate]) -> list[MentorCandidate]` (capacity + availability; relax availability if <3 remain, label "schedule_needs_discussion")
  - Implement `rank(student: StudentProfile, mentors: list[MentorCandidate]) -> list[tuple[MentorCandidate, float, dict]]` (sorted desc by score, ties by mentor id)

- [x] 9. Mentorship state machine (`app/services/mentorship.py`)
  - Depends on: 1
  - Define `InvalidTransition(Exception)` domain error
  - Implement `schedule(m, slot: str) -> None` (assert `requested`, set `intro_scheduled`)
  - Implement `hold(m) -> None` (assert `intro_scheduled`, set `intro_held`)
  - Implement `decide(m, side: str, choice: str) -> None` (assert `intro_held`, set decision field, trigger `ended` or `active` per spec logic)
  - Implement `complete(m) -> None` (assert `active`, set `completed`, set `completed_at`)
  - Raise `InvalidTransition` with descriptive message on any illegal call

- [x] 10. Scheduling service (`app/services/scheduling.py`)
  - Depends on: 1
  - Implement `suggest_slots(student_avail: list[str], mentor_avail: list[str], limit: int = 3) -> list[str]`
  - Returns up to `limit` strings from the intersection of both availability lists

- [x] 11. LLM service (`app/services/llm.py` + `app/services/prompts.py`)
  - Depends on: 6, 4
  - Define `LLMClient` Protocol: `complete_json(system: str, prompt: str, timeout_s: float = 6.0) -> str`
  - Implement `CopilotAdapter(LLMClient)` using GitHub Copilot SDK or openai-compatible endpoint; auth from `settings.copilot_token`
  - Implement `OffAdapter(LLMClient)` raises `LLMUnavailable` immediately
  - Implement `CachedAdapter(LLMClient)` reads from `LLMCache` by sha256 key; raises `LLMUnavailable` on miss
  - Implement `get_llm_client(db: Session) -> LLMClient` factory based on `settings.llm_mode`
  - Implement `extract_skills(text: str, db: Session) -> dict[str, float]`: call LLM with skill-extraction prompt, validate with `SkillScores`, fallback to `fallback_extract` on any failure; log latency/cache-hit/fallback
  - Implement `rerank_and_explain(student_json: str, candidates_json: str, db: Session) -> list[dict]`: call LLM with rerank prompt, validate with `MatchExplanations`, fallback to template explanation on any failure
  - Cache LLM results in `LLMCache` table (key = sha256(system+prompt))
  - Keep all prompt strings in `prompts.py` as module-level constants
  - `prompts.py`: define `SKILL_EXTRACTION_SYSTEM`, `SKILL_EXTRACTION_USER_TEMPLATE`, `RERANK_SYSTEM`, `RERANK_USER_TEMPLATE`

- [x] 12. Seed script (`seed.py`)
  - Depends on: 3, 6, 8
  - Create 8 mentor `User` + `MentorProfile` rows: 5 industry, 3 faculty; varied skills, outcomes, availability, top3, resume text; experience levels intermediate–advanced; include one with experience_score ~0.9
  - Create 6 student `User` + `StudentRequest` rows: Maya (beginner, exp_score ~0.3, skills_to_learn=[python, machine_learning]), 1 advanced student (exp_score ~0.75), 4 others
  - Design Maya's `Match` rows (rank 1–3) so: rank-1 mentor wins on skills_fit+outcome_fit, rank-2 on availability_fit, rank-3 on level_fit
  - Create `Mentorship` (active, 2 meetings held, open deliverables) for a non-Maya student
  - Create `Mentorship` (intro_held, both decisions pending) ready for Confirm/Decline demo
  - Create `Mentorship` (completed) with 6–10 `Testimonial` rows
  - Store cached LLM response for Maya's match in `LLMCache`
  - Create avatar SVG files in `app/static/avatars/` for each user
  - `seed()` function must be idempotent-safe (called after drop_all, so no duplicate checks needed)

- [x] 13. FastAPI app entry point (`app/main.py`)
  - Depends on: 3, 5, 9
  - Create `FastAPI` app instance
  - Add `SessionMiddleware` with `session_secret` from settings
  - Register exception handlers: `InvalidTransition` → 400 JSON, `NotFound` → 404 JSON
  - Call `Base.metadata.create_all(engine)` at startup (lifespan or module level)
  - Mount `StaticFiles("/static", directory="app/static")`
  - Configure `Jinja2Templates(directory="app/templates")`
  - Include routers: `demo`, `pages`, `api` (pages router registered last as catch-all)
  - Export `app` for uvicorn

- [x] 14. Demo router (`app/routers/demo.py`)
  - Depends on: 13
  - `GET /demo` — render `demo/panel.html` with list of seed users and current LLM mode
  - `POST /demo/role` — form field `user_id`; set `request.session["user_id"] = user_id`; redirect to `/`
  - `POST /demo/reset` — call `reset_db()`, redirect to `/`
  - `POST /demo/llm_mode` — form field `mode`; update settings llm_mode; redirect to `/demo`

- [x] 15. Pages router — student signup and matches (`app/routers/pages.py` part 1)
  - Depends on: 8, 11, 13
  - `GET /` — render `index.html` with session user context
  - `GET /student/signup` — render `student/signup.html` with taxonomy for chip inputs
  - `POST /student/signup` — parse 5-step form, call `extract_skills` if resume text provided, compute `experience_score`/`experience_level`, create `StudentRequest`, call `rank()`, call `rerank_and_explain()`, create 3 `Match` rows, redirect to `/student/matches`
  - `POST /student/skills/extract` — HTMX: `{text}` → call `extract_skills`, return `partials/skill_chips.html` fragment
  - `GET /student/matches` — load 3 `Match` rows with mentor data, render `student/matches.html`
  - `POST /student/requests` — body: `{match_id, note}`; create `Mentorship(status=requested, note_from_student=note)`; redirect to `/student/dashboard`
  - `GET /student/dashboard` — load student's mentorships, render `student/dashboard.html`

- [x] 16. Pages router — mentor signup and dashboard (`app/routers/pages.py` part 2)
  - Depends on: 11, 13
  - `GET /mentor/signup` — render `mentor/signup.html`
  - `POST /mentor/signup` — parse form, call `extract_skills`, compute experience level, create `User` + `MentorProfile`, redirect to `/mentor/dashboard`
  - `POST /mentor/skills/extract` — HTMX: `{text}` → `extract_skills` → return `partials/skill_chips.html`
  - `GET /mentor/dashboard` — load mentor's mentorships grouped by status, render `mentor/dashboard.html`
  - `GET /mentors/{id}` — load mentor profile + stats + testimonials, render `mentor/profile.html`
  - `GET/POST /availability` — render and handle the Day×4 availability grid for the current user

- [x] 17. Pages router — mentorship workspace (`app/routers/pages.py` part 3)
  - Depends on: 9, 10, 13
  - `GET /mentorship/{id}` — load mentorship + deliverables + meetings, render `mentorship/workspace.html`
  - `POST /mentorships/{id}/intro` — mentor sets slot text, call `schedule()`, save, redirect to workspace
  - `POST /mentorships/{id}/intro/held` — call `hold()`, save, redirect to workspace
  - `POST /mentorships/{id}/decision` — form `{choice: confirm|decline}`, call `decide()`, save; if ended and student, show next-best matches; redirect
  - `POST /mentorships/{id}/deliverables` — student proposes deliverable, create `Deliverable(status=proposed)`
  - `POST /deliverables/{del_id}` — update deliverable text / annotation / status (role-gated: annotation/approve only for mentor)
  - `POST /mentorships/{id}/meetings/{n}` — create or update `Meeting` record; mentor log entry
  - `POST /mentorships/{id}/testimonial` — create `Testimonial`, call `complete()` on mentorship

- [x] 18. JSON API router (`app/routers/api.py`)
  - Depends on: 4, 13
  - `GET /api/skills/taxonomy` → `list[dict]` (id, label, aliases)
  - `POST /api/skills/extract` → `SkillScores` (calls same service as HTML route)
  - `GET /api/matches/{request_id}` → `list[MatchOut]`
  - `GET /api/mentorships/{id}` → `MentorshipOut`
  - `GET /api/mentorships/{id}/deliverables` → `list[DeliverableOut]`
  - `POST /api/mentorships/{id}/decision` → `MentorshipOut` (JSON version of decide)

- [x] 19. Base template and CSS (`app/templates/base.html` + `app/static/styles.css`)
  - Depends on: 13
  - `base.html`: HTML5 boilerplate, nav with app name ("Sprout") + role banner ("Viewing as [Name] ([Role])"), `{% block content %}`, sample-data footer note, `<script src="/static/htmx.min.js">`, CSS link
  - Download and vendor HTMX 2.x into `app/static/htmx.min.js`
  - `styles.css`: implement complete styles for white base + midtone green (#4a7c59) accent, card layout, skill chip badges (with confidence opacity), experience level badges (beginner=yellow, intermediate=blue, advanced=green), availability grid, progress bar, tab nav, Confirm/Decline panel, button variants (primary/secondary/danger), responsive layout (single column on mobile), empty state styles

- [x] 20. Student templates
  - Depends on: 19
  - `templates/student/signup.html` — 5-step form with progress bar; step 1: goal text + goal_type chips; step 2: skills_to_learn chips (from taxonomy) + cadence radio; step 3: availability grid (`partials/availability_grid.html`); step 4: resume textarea + "Use sample resume" button + HTMX "Find my skills" → `partials/skill_chips.html` + experience level badge; step 5: pick-3 priorities
  - `templates/student/matches.html` — 3 match cards each with: headshot, name, type badge, title/org, "Why this match" explanation, skill tags with confidence percentages, experience level badges for both mentor and student, overlap time chips, "Request intro" button + note textarea
  - `templates/student/dashboard.html` — status timeline graphic (5 states), Confirm/Decline panel (`partials/confirm_decline.html`) shown when `intro_held`, next-deliverables banner shown when `active`
  - `templates/partials/skill_chips.html` — HTMX-swappable list of skill chips with confidence level controls (Beginner 0.3 / Working 0.6 / Strong 0.9 select) and experience level badge
  - `templates/partials/availability_grid.html` — 7×4 grid (Mon–Sun × Morning/Afternoon/Evening/Night) with HTMX toggle per cell
  - `templates/partials/confirm_decline.html` — side-by-side panel showing each person's status (Waiting/Confirmed/Declined), active decision buttons only for the current user, status summary line

- [x] 21. Mentor templates
  - Depends on: 19
  - `templates/mentor/signup.html` — resume textarea + "Find my skills" HTMX button → skill chips partial; additional experiences textarea; outcomes checkboxes; availability grid; pick-3 priorities; experience level badge auto-updated
  - `templates/mentor/dashboard.html` — section 1 "New intro requests": per-request card with student name, goal, "why matched" text, suggested slot chips, "Schedule intro" button; section 2 "Awaiting confirmation": confirm/decline panel; section 3 "Your students": per-mentorship card with student name, next meeting date, deliverables list
  - `templates/mentor/profile.html` — stats bar (X students mentored, Y meetings, Z weeks), current students list, past students list, testimonials list with attribution

- [x] 22. Mentorship workspace template (`app/templates/mentorship/workspace.html`)
  - Depends on: 19
  - Tab nav with 4 tabs: Deliverables, Meetings, Confirm, Messages (HTMX `hx-get` tab switching to partial URLs)
  - Deliverables tab: `+ Add deliverable` form (student only), list of deliverables with status badge, annotation textarea (mentor), approve/mark-done buttons (role-gated)
  - Meetings tab: intro meeting card (slot, held button for mentor), later meeting cards locked until active, agreed-time input, mentor log form with deliverable-reference select
  - Confirm tab: embed `partials/confirm_decline.html`
  - Messages tab: simple chronological thread + post form (Could — render if data exists, otherwise empty state)
  - `templates/demo/panel.html` — role switcher dropdown + switch button, Reset to seed button, LLM mode radio group, current session user display

- [x] 23. Availability grid JS (`app/static/grid.js`)
  - Depends on: 19
  - Vanilla JS that enhances the availability grid: on cell click, toggle a CSS class `selected` and update a hidden input value with the current selection as a comma-separated list of "Day-Part" strings
  - Works without HTMX (progressive enhancement); HTMX posts to `/availability` on change if `hx-*` attributes are present

- [x] 24. Unit tests — matching (`tests/test_matching.py`)
  - Depends on: 8
  - Test `cover(m, st)`: m=0.85, st=0.30 → 0.85; m=0.45, st=0.30 → 0.225; m=0.0 → 0.0; m=st → 0.0
  - Test `level_fit(gap)`: gap=0.0 → partial (0.5); gap=0.15 → 1.0; gap=0.30 → 1.0; gap=0.45 → 1.0; gap=0.50 → partial; gap=0.85 → 0.0; gap=-0.15 → 0.0; gap=-0.20 → 0.0
  - Test `rank()` is deterministic: call twice with same inputs, assert identical output
  - Test beginner vs advanced student (same target skills, same mentor pool) produce different top-3
  - Test `outcome_fit`: student goal_type in mentor_outcomes → 1.0; not in → 0.0
  - Test `availability_fit`: 0 overlaps → 0.0; 1 → 1/3; 3 → 1.0; 4 → 1.0
  - Test hard filter: mentor at max_students=2 with 2 active students is excluded
  - Test hard filter relaxation: if only 2 mentors have overlap, all mentors returned with `schedule_needs_discussion` flag

- [x] 25. Unit tests — skills (`tests/test_skills.py`)
  - Depends on: 6
  - Test `experience_score({}) = 0.0`
  - Test `experience_score({"python": 0.8}) = 0.8`
  - Test `experience_score` with 7 skills uses only top 5
  - Test `experience_level(0.0) = "beginner"`, `(0.34) = "beginner"`, `(0.35) = "intermediate"`, `(0.64) = "intermediate"`, `(0.65) = "advanced"`, `(1.0) = "advanced"`
  - Test `normalize_skill_id("py") = "python"`, `normalize_skill_id("python") = "python"`, `normalize_skill_id("zzz") = None`
  - Test `fallback_extract` returns only valid taxonomy ids, values ≤ 0.7

- [x] 26. Unit tests — mentorship state machine (`tests/test_mentorship_flow.py`)
  - Depends on: 9
  - Test `schedule()` transitions `requested → intro_scheduled`
  - Test `hold()` transitions `intro_scheduled → intro_held`
  - Test `decide(side=mentor, choice=confirm)` + `decide(side=student, choice=confirm)` → `active`
  - Test `decide(side=mentor, choice=decline)` → `ended`
  - Test `decide(side=student, choice=decline)` → `ended`
  - Test `complete()` transitions `active → completed`
  - Test calling `schedule()` on an `intro_held` mentorship raises `InvalidTransition`
  - Test calling `decide()` on a `requested` mentorship raises `InvalidTransition`

- [x] 27. Integration tests — LLM fallback (`tests/test_llm_fallback.py`)
  - Depends on: 11
  - Fake `LLMClient` returning valid JSON → `extract_skills` returns correct `SkillScores`
  - Fake returning `{broken json` → fallback `fallback_extract` is called instead
  - Fake raising `TimeoutError` → fallback used, no exception propagated
  - Fake returning skills with unknown taxonomy ids → unknown keys dropped, known keys remain
  - Fake returning skill confidences outside 0–1 → values clamped

- [x] 28. Integration tests — full One Flow (`tests/test_flow_api.py`)
  - Depends on: 15, 16, 17, 18
  - Setup: in-memory SQLite engine, `get_session` dependency override, `LLM_MODE=off`
  - POST `/student/signup` with Maya's data → 302 redirect to `/student/matches`
  - GET `/student/matches` → 200, contains 3 match cards
  - POST `/student/requests` → creates Mentorship(requested), 302 to dashboard
  - POST `/demo/role` as mentor → session switch
  - GET `/mentor/dashboard` → shows intro request
  - POST `/mentorships/{id}/intro` → 302, mentorship is `intro_scheduled`
  - POST `/mentorships/{id}/intro/held` → 302, mentorship is `intro_held`
  - POST `/mentorships/{id}/decision` as mentor `confirm` → still pending (student not decided)
  - POST `/mentorships/{id}/decision` as student `confirm` → mentorship is `active`
  - POST `/mentorships/{id}/deliverables` → creates Deliverable(proposed)
  - POST `/deliverables/{id}` as mentor with `{status: approved}` → Deliverable(approved)
  - POST `/mentorships/{id}/testimonial` → creates Testimonial, mentorship is `completed`

## Notes

- The tech-stack spec supersedes Section 7 (data layer) and Section 11 (stack/routes) of the hackathon spec. Use SQLAlchemy 2.0 + Pydantic v2 as separate layers, not SQLModel.
- All matching math is pure Python in `services/matching.py` with no ORM dependency — unit tests need no database.
- All AI calls go through `services/llm.py`. LLM_MODE=off must work for every flow.
- JSON columns: always reassign the whole value or use `MutableDict`/`MutableList` wrappers to trigger SQLAlchemy change tracking.
- HTMX 2.x must be vendored into `app/static/htmx.min.js` so the demo works offline.
- Seed data drives demo quality. Invest time in making Maya's 3 match cards look genuinely different.
- Record the demo video at hour 19.5 before the feature freeze becomes a problem.
