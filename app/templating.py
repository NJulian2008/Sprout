"""
Shared Jinja2 template configuration and common template helpers.

All routers import `templates` / `render` from here so there is a single
Jinja2Templates instance with shared globals.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from app.db.models import User
from app.settings import settings

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["settings"] = settings


def render(name: str, context: dict) -> HTMLResponse:
    """Render a template using the modern Starlette signature.

    Context MUST contain a "request" key. This wrapper lets routers keep the
    familiar ``render("x.html", {"request": request, ...})`` call style while
    using the request-first API required by Starlette >= 0.29.
    """
    request = context["request"]
    return templates.TemplateResponse(request, name, context)


def current_user(request: Request, db) -> User | None:
    """Return the User for the session's user_id, or None if not set."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return db.get(User, int(user_id))
