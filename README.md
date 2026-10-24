# Sprout — Mentor–Student Matching Platform

Sprout connects students with mentors for HackOHI/O 2026. It runs as a single FastAPI process with no build step, backed by SQLite, and works fully offline (no external services required in `LLM_MODE=off`).

**Stack:** FastAPI · SQLAlchemy 2.0 (sync) · SQLite · Pydantic v2 · Jinja2 · HTMX 2.x

---

## Setup

### Using uv (recommended)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy and edit environment variables
cp .env.example .env
```

### Using pip (fallback)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

---

## Environment variables

Copy `.env.example` to `.env` and adjust as needed:

| Variable        | Default              | Description                                            |
|-----------------|----------------------|--------------------------------------------------------|
| `DATABASE_URL`  | `sqlite:///app.db`   | SQLite database path                                   |
| `SESSION_SECRET`| `change-me-in-production` | Cookie-signing secret — **change before deploying** |
| `LLM_MODE`      | `off`                | `live` / `cached` / `off` — controls AI skill extraction |
| `DEMO_MODE`     | `normal`             | `normal` shows the demo panel; `off` hides it         |
| `COPILOT_TOKEN` | *(empty)*            | Bearer token for the LLM endpoint (only for `LLM_MODE=live`) |

---

## Running the app

```bash
make run
# → http://127.0.0.1:8000
```

---

## Seeding demo data

```bash
make seed
```

Loads 8 mentors, 6 students, pre-computed match rows, and a completed mentorship with testimonials.

---

## Resetting the database

```bash
make reset
```

Drops all tables, recreates the schema, and re-runs the seed script.

---

## Running tests

```bash
make test
```

---

## Project layout

```
app/
  db/          ORM models and session/engine setup
  schemas/     Pydantic v2 schemas
  routers/     FastAPI route handlers (pages, api, demo)
  services/    Business logic (matching, LLM, mentorship FSM, scheduling, skills)
  data/        Static data files (skills taxonomy JSON)
  templates/   Jinja2 HTML templates
  static/      CSS, vendored HTMX, avatar SVGs
tests/         pytest test suite
seed.py        Demo seed script
```
