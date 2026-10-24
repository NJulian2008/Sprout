"""
JSON API router (/api/*).

Returns Pydantic response models for the core resources. These endpoints
share the same service functions as the HTML pages and double as the
integration test surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.models import Deliverable, Match, Mentorship
from app.db.session import get_session
from app.schemas.ai import SkillScores
from app.schemas.match import MatchOut
from app.schemas.mentorship import DeliverableOut, MentorshipOut
from app.services import mentorship as fsm
from app.services.llm import extract_skills
from app.services.skills import load_taxonomy
from app.templating import current_user

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/skills/taxonomy")
def api_taxonomy() -> list[dict]:
    """Return the full skills taxonomy as a list of entries."""
    return list(load_taxonomy().values())


@router.post("/skills/extract")
def api_extract(text: str = "", db: Session = Depends(get_session)) -> SkillScores:
    """Extract skill confidences from text and return validated SkillScores."""
    scores = extract_skills(text, db) if text.strip() else {}
    return SkillScores(skills=scores)


@router.get("/matches/{request_id}")
def api_matches(request_id: int, db: Session = Depends(get_session)) -> list[MatchOut]:
    matches = (
        db.query(Match)
        .filter(Match.request_id == request_id)
        .order_by(Match.rank)
        .all()
    )
    return [MatchOut.model_validate(m) for m in matches]


@router.get("/mentorships/{mentorship_id}")
def api_mentorship(mentorship_id: int, db: Session = Depends(get_session)) -> MentorshipOut:
    ms = db.get(Mentorship, mentorship_id)
    if ms is None:
        raise HTTPException(status_code=404, detail="Mentorship not found")
    return MentorshipOut.model_validate(ms)


@router.get("/mentorships/{mentorship_id}/deliverables")
def api_deliverables(
    mentorship_id: int, db: Session = Depends(get_session)
) -> list[DeliverableOut]:
    rows = (
        db.query(Deliverable)
        .filter(Deliverable.mentorship_id == mentorship_id)
        .order_by(Deliverable.id)
        .all()
    )
    return [DeliverableOut.model_validate(d) for d in rows]


@router.post("/mentorships/{mentorship_id}/decision")
def api_decision(
    mentorship_id: int,
    request: Request,
    choice: str,
    db: Session = Depends(get_session),
) -> MentorshipOut:
    ms = db.get(Mentorship, mentorship_id)
    if ms is None:
        raise HTTPException(status_code=404, detail="Mentorship not found")
    user = current_user(request, db)
    side = "mentor" if user and user.id == ms.mentor_id else "student"
    fsm.decide(ms, side, choice)
    db.commit()
    db.refresh(ms)
    return MentorshipOut.model_validate(ms)
