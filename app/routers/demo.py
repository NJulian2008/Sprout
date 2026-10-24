"""
Demo operator router: role switching, DB reset, and LLM mode toggle.

No real authentication — the session cookie just holds a user_id.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_session
from app.settings import settings
from app.templating import current_user, render

router = APIRouter()


@router.get("/demo")
def demo_panel(request: Request, db: Session = Depends(get_session)):
    """Operator panel: role switcher, reset button, LLM toggle."""
    users = db.query(User).order_by(User.role.desc(), User.id).all()
    return render(
        "demo/panel.html",
        {
            "request": request,
            "users": users,
            "current": current_user(request, db),
            "llm_mode": settings.llm_mode,
            "demo_mode": settings.demo_mode,
        },
    )


@router.post("/demo/role")
def set_role(request: Request, user_id: int = Form(...)):
    """Set the session's active user (role switcher)."""
    request.session["user_id"] = user_id
    return RedirectResponse(url="/", status_code=303)


@router.post("/demo/reset")
def reset(request: Request):
    """Reseed the database to the demo baseline."""
    from app.db.session import reset_db
    reset_db()
    # Clear the session so the operator starts fresh.
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.post("/demo/llm_mode")
def set_llm_mode(request: Request, mode: str = Form(...)):
    """Toggle the LLM mode at runtime (on=live / off / cached)."""
    if mode in ("live", "off", "cached"):
        settings.llm_mode = mode
    return RedirectResponse(url="/demo", status_code=303)
