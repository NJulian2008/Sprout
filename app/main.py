"""
FastAPI application entry point for Sprout.

Sets up:
- SessionMiddleware (signed cookie holding the demo user_id)
- Static file mount and Jinja2 templates (shared via app.templating)
- Exception handlers for domain errors
- Router registration (demo, api, pages)
- Table creation on startup
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.middleware.sessions import SessionMiddleware

from app.db.models import Base
from app.db.session import engine
from app.services.mentorship import InvalidTransition
from app.settings import settings
from app.templating import templates  # noqa: F401  (ensures templates configured)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sprout")


class NotFound(Exception):
    """Domain-level not-found error (mapped to HTTP 404)."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup if they do not exist yet.
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        mentor_columns = {
            column["name"] for column in inspect(connection).get_columns("mentorprofile")
        }
        if "specialties" not in mentor_columns:
            connection.execute(
                text("ALTER TABLE mentorprofile ADD COLUMN specialties JSON NOT NULL DEFAULT '[]'")
            )

        request_columns = {
            column["name"] for column in inspect(connection).get_columns("studentrequest")
        }
        if "specialty" not in request_columns:
            connection.execute(
                text(
                    "ALTER TABLE studentrequest ADD COLUMN specialty VARCHAR NOT NULL "
                    "DEFAULT 'computer_science'"
                )
            )
    logger.info("Sprout startup complete (LLM_MODE=%s)", settings.llm_mode)
    yield


app = FastAPI(title="Sprout — Mentor Matching", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(InvalidTransition)
async def invalid_transition_handler(request: Request, exc: InvalidTransition):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(NotFound)
async def not_found_handler(request: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


# ── Routers ───────────────────────────────────────────────────────────────────
# Imported here (after app creation) to avoid circular imports.

from app.routers import api, demo, pages  # noqa: E402

app.include_router(demo.router)
app.include_router(api.router)
app.include_router(pages.router)  # pages last (contains catch-all-ish routes)
