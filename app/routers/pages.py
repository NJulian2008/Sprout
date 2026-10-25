"""
Page routes (Jinja2 + HTMX) for Sprout.

Covers:
- Landing (/)
- Student signup, matches, requests, dashboard, skills-extract
- Mentor signup, dashboard, profile, skills-extract
- Mentorship workspace + all workspace actions
- Availability grid
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config_constants import CS_ENGINEERING_SPECIALTIES
from app.db.models import (
    Deliverable,
    Match,
    Meeting,
    MentorProfile,
    Mentorship,
    Message,
    StudentRequest,
    Testimonial,
    User,
)
from app.db.session import get_session
from app.services import mentorship as fsm
from app.services import scheduling
from app.services.llm import extract_skills, rerank_and_explain
from app.services.matching import MentorCandidate, StudentProfile, rank
from app.services.skills import experience_level, experience_score, load_taxonomy
from app.templating import current_user, render

router = APIRouter()

# Minimum extraction confidence for a goal-text skill to become a learning
# target. 0.4 is the first SKILL_EXTRACTION rubric rung that reflects real
# intent (coursework / one small project) rather than an incidental mention,
# so ambiguous goals no longer over-produce learning targets (bugfix 2.4).
GOAL_SKILL_THRESHOLD = 0.4


# ── helpers ───────────────────────────────────────────────────────────────────


def _parse_multi(form_value: str | None) -> list[str]:
    """Parse a comma-separated hidden field into a clean list."""
    if not form_value:
        return []
    return [v.strip() for v in form_value.split(",") if v.strip()]


def _validated_scores(posted: dict) -> dict[str, float]:
    """Coerce posted skill scores and run them through ``SkillScores``.

    Non-numeric values are skipped (not raised); unknown ids are dropped and
    valid values clamped to [0.0, 1.0] and rounded to 2 decimals by SkillScores.
    """
    from app.schemas.ai import SkillScores

    numeric: dict[str, float] = {}
    for k, v in posted.items():
        try:
            numeric[k] = float(v)
        except (TypeError, ValueError):
            continue  # malformed entry ignored (2.3)
    return SkillScores(skills=numeric).skills


def _resume_text_from_upload(upload: UploadFile) -> str:
    """Extract text from a supported resume upload."""
    suffix = Path(upload.filename or "").suffix.lower()
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded resume is empty.")

    try:
        if suffix == ".txt":
            text = content.decode("utf-8-sig")
        elif suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            from docx import Document

            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        else:
            raise HTTPException(
                status_code=422,
                detail="Upload your resume as a PDF, DOCX, or TXT file.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="We couldn't read that resume file. Try a text-based PDF or TXT file.",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No readable text was found in the resume file.",
        )
    return text


def _mentor_to_candidate(profile: MentorProfile, active_students: int = 0) -> MentorCandidate:
    return MentorCandidate(
        id=profile.user_id,
        skill_scores=dict(profile.skill_scores),
        experience_score=profile.experience_score,
        outcomes=list(profile.outcomes),
        availability=list(profile.availability),
        active_students=active_students,
        max_students=profile.max_students,
        specialties=list(profile.specialties),
    )


def _active_student_count(db: Session, mentor_id: int) -> int:
    return (
        db.query(Mentorship)
        .filter(Mentorship.mentor_id == mentor_id, Mentorship.status == "active")
        .count()
    )


# ── Landing ─────────────────────────────────────────────────────────────────


@router.get("/")
def landing(request: Request, db: Session = Depends(get_session)):
    return render(
        "index.html",
        {"request": request, "current": current_user(request, db)},
    )


# ── Student signup + matches ──────────────────────────────────────────────────


@router.get("/student/signup")
def student_signup_form(request: Request, db: Session = Depends(get_session)):
    return render(
        "student/signup.html",
        {
            "request": request,
            "current": current_user(request, db),
            "taxonomy": load_taxonomy(),
            "specialties": CS_ENGINEERING_SPECIALTIES,
        },
    )


@router.post("/student/signup")
def student_signup_submit(
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form("Demo Student"),
    goal_text: str = Form(...),
    specialty: str = Form(...),
    cadence: str = Form("weekly"),
    availability: str = Form(""),
    top3: str = Form(""),
    skill_scores_json: str = Form("{}"),
    skill_scores_reviewed: bool = Form(False),
    resume_file: UploadFile = File(...),
):
    resume_text = _resume_text_from_upload(resume_file)
    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="Resume text is required.")
    if not goal_text.strip():
        raise HTTPException(status_code=422, detail="Goal is required.")
    if specialty not in CS_ENGINEERING_SPECIALTIES:
        raise HTTPException(status_code=422, detail="Choose a valid CS or engineering specialty.")

    # Build the student user
    user = User(role="student", name=name, headshot_url="/static/avatars/avatar_9.svg")
    db.add(user)
    db.flush()

    try:
        posted = json.loads(skill_scores_json) if skill_scores_json else {}
    except json.JSONDecodeError:
        posted = {}
    if not isinstance(posted, dict):
        posted = {}
    if skill_scores_reviewed or posted:
        scores = _validated_scores(posted)
    elif resume_text.strip():
        scores = extract_skills(resume_text, db)
    else:
        scores = {}
    goal_skills = extract_skills(goal_text, db, goal_context=True)
    goal_type = _infer_goal_type(goal_text)

    exp_s = experience_score(scores)
    req = StudentRequest(
        student_id=user.id,
        goal_text=goal_text,
        goal_type=goal_type,
        specialty=specialty,
        skills_to_learn=[
            skill_id
            for skill_id, confidence in goal_skills.items()
            if confidence >= GOAL_SKILL_THRESHOLD
        ],
        cadence=cadence,
        availability=_parse_multi(availability),
        top3=_parse_multi(top3),
        resume_text=resume_text,
        skill_scores=scores,
        experience_score=exp_s,
        experience_level=experience_level(exp_s),
    )
    db.add(req)
    db.flush()

    # Run matching
    _run_matching(db, req)

    db.commit()
    request.session["user_id"] = user.id
    request.session["request_id"] = req.id
    return RedirectResponse(url="/student/matches", status_code=303)


def _infer_goal_type(goal_text: str) -> str:
    text = goal_text.lower()
    if any(word in text for word in ("research", "thesis", "publish", "paper")):
        return "research"
    if any(word in text for word in ("career", "job", "internship", "interview", "role")):
        return "career_navigation"
    if any(word in text for word in ("build", "create", "develop", "make", "project", "prototype")):
        return "build_project"
    return "learn_skill"


def _run_matching(db: Session, req: StudentRequest) -> None:
    """Score mentors, pick top 3, write Match rows (with LLM rerank + fallback)."""
    student = StudentProfile(
        id=req.student_id,
        goal_type=req.goal_type,
        skills_to_learn=list(req.skills_to_learn),
        skill_scores=dict(req.skill_scores),
        experience_score=req.experience_score,
        availability=list(req.availability),
        specialty=req.specialty,
    )
    profiles = db.query(MentorProfile).all()
    candidates = [_mentor_to_candidate(p, _active_student_count(db, p.user_id)) for p in profiles]
    ranked = rank(student, candidates)
    top5 = ranked[:5]

    # Build candidate JSON for the LLM
    users_by_id = {u.id: u for u in db.query(User).all()}
    cand_payload = []
    for cand, score, _breakdown in top5:
        u = users_by_id.get(cand.id)
        shared = [s for s in student.skills_to_learn if cand.skill_scores.get(s, 0.0) >= 0.5]
        cand_payload.append(
            {
                "mentor_id": str(cand.id),
                "mentor_name": u.name if u else f"Mentor {cand.id}",
                "experience_level": experience_level(cand.experience_score),
                "student_level": req.experience_level,
                "shared_skills": shared,
                "overlap_summary": ", ".join(
                    sorted(set(student.availability) & set(cand.availability))
                )
                or "by arrangement",
                "score": score,
            }
        )
    student_payload = {
        "goal": req.goal_text,
        "goal_type": req.goal_type,
        "specialty": req.specialty,
        "skills_to_learn": student.skills_to_learn,
        "experience_level": req.experience_level,
        "availability": student.availability,
    }

    explanations = rerank_and_explain(json.dumps(student_payload), json.dumps(cand_payload), db)
    source = "cached" if explanations else "fallback"

    # Map explanations by mentor_id; fall back to top-3 by score
    expl_by_id = {str(e["mentor_id"]): e for e in explanations}

    # Decide final 3: prefer LLM order if valid, else top-3 by score
    if len(expl_by_id) == 3:
        ordered = sorted(explanations, key=lambda e: e["rank"])
        final = []
        score_lookup = {str(c.id): (s, b) for c, s, b in top5}
        for e in ordered:
            mid = str(e["mentor_id"])
            if mid in score_lookup:
                s, b = score_lookup[mid]
                final.append((int(mid), s, b, e["explanation"]))
    else:
        final = []
        for cand, score, breakdown in ranked[:3]:
            expl = expl_by_id.get(str(cand.id), {}).get("explanation", "")
            final.append((cand.id, score, breakdown, expl))
        source = "fallback"

    # Clear any prior matches for this request, then write new ones
    db.query(Match).filter(Match.request_id == req.id).delete()
    for i, (mentor_id, score, breakdown, expl) in enumerate(final, start=1):
        db.add(
            Match(
                request_id=req.id,
                mentor_id=mentor_id,
                rank=i,
                score=round(score, 2),
                score_breakdown=breakdown,
                explanation=expl,
                source=source,
            )
        )


@router.get("/student/matches")
def student_matches(request: Request, db: Session = Depends(get_session)):
    request_id = request.session.get("request_id")
    if request_id is None:
        # Fall back to the most recent request for the session user
        uid = request.session.get("user_id")
        req = (
            db.query(StudentRequest)
            .filter(StudentRequest.student_id == uid)
            .order_by(StudentRequest.id.desc())
            .first()
            if uid
            else None
        )
    else:
        req = db.get(StudentRequest, int(request_id))

    matches_ctx = []
    if req:
        matches = db.query(Match).filter(Match.request_id == req.id).order_by(Match.rank).all()
        for m in matches:
            mentor = db.get(User, m.mentor_id)
            profile = db.get(MentorProfile, m.mentor_id)
            overlap = sorted(set(req.availability) & set(profile.availability)) if profile else []
            matches_ctx.append(
                {
                    "match": m,
                    "mentor": mentor,
                    "profile": profile,
                    "overlap": overlap,
                }
            )

    return render(
        "student/matches.html",
        {
            "request": request,
            "current": current_user(request, db),
            "req": req,
            "matches": matches_ctx,
            "taxonomy": load_taxonomy(),
        },
    )


@router.post("/student/requests")
def student_choose_mentor(
    request: Request,
    db: Session = Depends(get_session),
    match_id: int = Form(...),
    note: str = Form(""),
):
    match = db.get(Match, match_id)
    if match is None:
        return RedirectResponse(url="/student/matches", status_code=303)
    req = db.get(StudentRequest, match.request_id)
    ms = Mentorship(
        mentor_id=match.mentor_id,
        student_id=req.student_id,
        request_id=req.id,
        status="requested",
        note_from_student=note,
        cadence=req.cadence,
    )
    db.add(ms)
    db.commit()
    return RedirectResponse(url="/student/dashboard", status_code=303)


@router.post("/student/skills/extract")
def student_skills_extract(
    request: Request,
    db: Session = Depends(get_session),
    resume_file: UploadFile = File(...),
):
    try:
        resume_text = _resume_text_from_upload(resume_file)
    except HTTPException:
        resume_text = ""
    scores = extract_skills(resume_text, db) if resume_text.strip() else {}
    exp_s = experience_score(scores)
    return render(
        "partials/skill_chips.html",
        {
            "request": request,
            "skill_scores": scores,
            "experience_level": experience_level(exp_s),
            "experience_score": round(exp_s, 2),
            "taxonomy": load_taxonomy(),
            "field_name": "skill_scores_json",
            "scores_reviewed": True,
        },
    )


@router.get("/student/dashboard")
def student_dashboard(request: Request, db: Session = Depends(get_session)):
    user = current_user(request, db)
    mentorships = []
    if user:
        mentorships = (
            db.query(Mentorship)
            .filter(Mentorship.student_id == user.id)
            .order_by(Mentorship.id.desc())
            .all()
        )
    ctx_items = []
    for ms in mentorships:
        mentor = db.get(User, ms.mentor_id)
        deliverables = db.query(Deliverable).filter(Deliverable.mentorship_id == ms.id).all()
        ctx_items.append({"ms": ms, "mentor": mentor, "deliverables": deliverables})
    return render(
        "student/dashboard.html",
        {
            "request": request,
            "current": user,
            "items": ctx_items,
        },
    )


# ── Mentor signup + dashboard + profile ─────────────────────────────────────


@router.get("/mentor/signup")
def mentor_signup_form(request: Request, db: Session = Depends(get_session)):
    return render(
        "mentor/signup.html",
        {
            "request": request,
            "current": current_user(request, db),
            "taxonomy": load_taxonomy(),
            "specialties": CS_ENGINEERING_SPECIALTIES,
        },
    )


@router.post("/mentor/signup")
def mentor_signup_submit(
    request: Request,
    db: Session = Depends(get_session),
    name: str = Form(...),
    bio_short: str = Form(""),
    title: str = Form(""),
    org: str = Form(""),
    mentor_type: str = Form("industry"),
    resume_text: str = Form(""),
    skill_scores_json: str = Form("{}"),
    additional_experiences: str = Form(""),
    outcomes: str = Form(""),
    availability: str = Form(""),
    top3: str = Form(""),
    max_students: int = Form(2),
    specialties: str = Form(""),
    skill_scores_reviewed: bool = Form(False),
    resume_file: UploadFile = File(...),
):
    resume_text = _resume_text_from_upload(resume_file)
    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="Resume text is required.")
    user = User(
        role="mentor",
        name=name,
        bio_short=bio_short,
        title=title,
        org=org,
        mentor_type=mentor_type,
        headshot_url="/static/avatars/avatar_2.svg",
    )
    chosen_specialties = _parse_multi(specialties)
    if not chosen_specialties or any(
        specialty not in CS_ENGINEERING_SPECIALTIES for specialty in chosen_specialties
    ):
        raise HTTPException(
            status_code=422, detail="Choose at least one valid CS or engineering specialty."
        )
    db.add(user)
    db.flush()

    try:
        posted = json.loads(skill_scores_json) if skill_scores_json else {}
    except json.JSONDecodeError:
        posted = {}
    if not isinstance(posted, dict):
        posted = {}
    if skill_scores_reviewed or posted:
        scores = _validated_scores(posted)
    elif resume_text.strip():
        scores = extract_skills(resume_text, db)
    else:
        scores = {}

    exp_s = experience_score(scores)
    profile = MentorProfile(
        user_id=user.id,
        resume_text=resume_text,
        skill_scores=scores,
        experience_score=exp_s,
        experience_level=experience_level(exp_s),
        additional_experiences=additional_experiences,
        specialties=chosen_specialties,
        outcomes=_parse_multi(outcomes),
        availability=_parse_multi(availability),
        top3=_parse_multi(top3),
        max_students=max_students,
    )
    db.add(profile)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/mentor/dashboard", status_code=303)


@router.post("/mentor/skills/extract")
def mentor_skills_extract(
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(""),
):
    scores = extract_skills(text, db) if text.strip() else {}
    exp_s = experience_score(scores)
    return render(
        "partials/skill_chips.html",
        {
            "request": request,
            "skill_scores": scores,
            "experience_level": experience_level(exp_s),
            "experience_score": round(exp_s, 2),
            "taxonomy": load_taxonomy(),
            "field_name": "skill_scores_json",
            "scores_reviewed": True,
        },
    )


@router.get("/mentor/dashboard")
def mentor_dashboard(request: Request, db: Session = Depends(get_session)):
    user = current_user(request, db)
    requests_new, awaiting, active = [], [], []
    if user:
        all_ms = (
            db.query(Mentorship)
            .filter(Mentorship.mentor_id == user.id)
            .order_by(Mentorship.id.desc())
            .all()
        )
        for ms in all_ms:
            student = db.get(User, ms.student_id)
            req = db.get(StudentRequest, ms.request_id)
            profile = db.get(MentorProfile, user.id)
            slots = []
            if req and profile:
                slots = scheduling.suggest_slots(list(req.availability), list(profile.availability))
            match = (
                db.query(Match)
                .filter(Match.request_id == ms.request_id, Match.mentor_id == user.id)
                .first()
            )
            item = {
                "ms": ms,
                "student": student,
                "req": req,
                "slots": slots,
                "match": match,
            }
            if ms.status == "requested":
                requests_new.append(item)
            elif ms.status == "intro_scheduled" or ms.status == "intro_held":
                awaiting.append(item)
            elif ms.status in ("active", "completed"):
                deliverables = (
                    db.query(Deliverable).filter(Deliverable.mentorship_id == ms.id).all()
                )
                item["deliverables"] = deliverables
                active.append(item)
    return render(
        "mentor/dashboard.html",
        {
            "request": request,
            "current": user,
            "requests_new": requests_new,
            "awaiting": awaiting,
            "active": active,
        },
    )


@router.get("/mentors/{mentor_id}")
def mentor_profile(mentor_id: int, request: Request, db: Session = Depends(get_session)):
    mentor = db.get(User, mentor_id)
    profile = db.get(MentorProfile, mentor_id)
    all_ms = db.query(Mentorship).filter(Mentorship.mentor_id == mentor_id).all()
    current_students, past_students = [], []
    meetings_held = 0
    for ms in all_ms:
        student = db.get(User, ms.student_id)
        meetings_held += (
            db.query(Meeting)
            .filter(Meeting.mentorship_id == ms.id, Meeting.status == "held")
            .count()
        )
        if ms.status == "active":
            current_students.append(student)
        elif ms.status == "completed":
            past_students.append(student)
    testimonials = []
    for t in db.query(Testimonial).filter(Testimonial.mentor_id == mentor_id).all():
        author = db.get(User, t.student_id)
        testimonials.append({"t": t, "author": author})
    return render(
        "mentor/profile.html",
        {
            "request": request,
            "current": current_user(request, db),
            "mentor": mentor,
            "profile": profile,
            "current_students": current_students,
            "past_students": past_students,
            "meetings_held": meetings_held,
            "total_mentored": len(current_students) + len(past_students),
            "testimonials": testimonials,
            "taxonomy": load_taxonomy(),
        },
    )


# ── Availability ───────────────────────────────────────────────────────────────


@router.get("/availability")
def availability_page(request: Request, db: Session = Depends(get_session)):
    user = current_user(request, db)
    current_avail = []
    if user and user.role == "mentor":
        p = db.get(MentorProfile, user.id)
        current_avail = list(p.availability) if p else []
    elif user and user.role == "student":
        req = (
            db.query(StudentRequest)
            .filter(StudentRequest.student_id == user.id)
            .order_by(StudentRequest.id.desc())
            .first()
        )
        current_avail = list(req.availability) if req else []
    return render(
        "availability.html",
        {"request": request, "current": user, "current_avail": current_avail},
    )


@router.post("/availability")
def availability_save(
    request: Request,
    db: Session = Depends(get_session),
    availability: str = Form(""),
):
    user = current_user(request, db)
    avail = _parse_multi(availability)
    if user and user.role == "mentor":
        p = db.get(MentorProfile, user.id)
        if p:
            p.availability = avail
    elif user and user.role == "student":
        req = (
            db.query(StudentRequest)
            .filter(StudentRequest.student_id == user.id)
            .order_by(StudentRequest.id.desc())
            .first()
        )
        if req:
            req.availability = avail
    db.commit()
    return RedirectResponse(url="/availability", status_code=303)


# ── Mentorship workspace ──────────────────────────────────────────────────────


def _load_workspace(db: Session, mentorship_id: int):
    ms = db.get(Mentorship, mentorship_id)
    if ms is None:
        return None
    mentor = db.get(User, ms.mentor_id)
    student = db.get(User, ms.student_id)
    deliverables = (
        db.query(Deliverable)
        .filter(Deliverable.mentorship_id == ms.id)
        .order_by(Deliverable.id)
        .all()
    )
    meetings = (
        db.query(Meeting).filter(Meeting.mentorship_id == ms.id).order_by(Meeting.number).all()
    )
    testimonials = db.query(Testimonial).filter(Testimonial.mentorship_id == ms.id).all()
    message_rows = (
        db.query(Message)
        .filter(Message.mentorship_id == ms.id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    messages = [{"msg": m, "sender": db.get(User, m.sender_id)} for m in message_rows]
    return {
        "ms": ms,
        "mentor": mentor,
        "student": student,
        "deliverables": deliverables,
        "meetings": meetings,
        "testimonials": testimonials,
        "messages": messages,
    }


@router.get("/mentorship/{mentorship_id}")
def mentorship_workspace(mentorship_id: int, request: Request, db: Session = Depends(get_session)):
    ctx = _load_workspace(db, mentorship_id)
    if ctx is None:
        return RedirectResponse(url="/", status_code=303)
    ctx["request"] = request
    ctx["current"] = current_user(request, db)
    return render("mentorship/workspace.html", ctx)


@router.post("/mentorships/{mentorship_id}/intro")
def schedule_intro(
    mentorship_id: int,
    request: Request,
    db: Session = Depends(get_session),
    slot: str = Form(...),
):
    ms = db.get(Mentorship, mentorship_id)
    fsm.schedule(ms, slot)
    # Create the intro meeting record
    db.add(
        Meeting(
            mentorship_id=ms.id,
            number=0,
            agreed_time_text=slot,
            status="scheduled",
        )
    )
    db.commit()
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/mentorships/{mentorship_id}/intro/held")
def mark_intro_held(mentorship_id: int, request: Request, db: Session = Depends(get_session)):
    ms = db.get(Mentorship, mentorship_id)
    fsm.hold(ms)
    intro = db.query(Meeting).filter(Meeting.mentorship_id == ms.id, Meeting.number == 0).first()
    if intro:
        intro.status = "held"
    db.commit()
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/mentorships/{mentorship_id}/decision")
def record_decision(
    mentorship_id: int,
    request: Request,
    db: Session = Depends(get_session),
    choice: str = Form(...),
):
    ms = db.get(Mentorship, mentorship_id)
    user = current_user(request, db)
    side = "mentor" if user and user.id == ms.mentor_id else "student"
    fsm.decide(ms, side, choice)
    db.commit()
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/mentorships/{mentorship_id}/deliverables")
def propose_deliverable(
    mentorship_id: int,
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(...),
    due_meeting: int | None = Form(None),
):
    db.add(
        Deliverable(
            mentorship_id=mentorship_id,
            text=text,
            status="proposed",
            due_meeting=due_meeting,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/deliverables/{deliverable_id}")
def update_deliverable(
    deliverable_id: int,
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(None),
    mentor_annotation: str = Form(None),
    status: str = Form(None),
):
    d = db.get(Deliverable, deliverable_id)
    if d:
        user = current_user(request, db)
        ms = db.get(Mentorship, d.mentorship_id)
        is_mentor = user and ms and user.id == ms.mentor_id
        if text is not None:
            d.text = text
        # Only the mentor may annotate/approve
        if is_mentor and mentor_annotation is not None:
            d.mentor_annotation = mentor_annotation
        if status is not None:
            if status in ("approved",) and not is_mentor:
                pass  # students cannot approve
            else:
                d.status = status
        db.commit()
        mentorship_id = d.mentorship_id
    else:
        mentorship_id = 0
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/mentorships/{mentorship_id}/meetings/{number}")
def update_meeting(
    mentorship_id: int,
    number: int,
    request: Request,
    db: Session = Depends(get_session),
    agreed_time_text: str = Form(None),
    summary: str = Form(None),
    note: str = Form(None),
):
    meeting = (
        db.query(Meeting)
        .filter(Meeting.mentorship_id == mentorship_id, Meeting.number == number)
        .first()
    )
    if meeting is None:
        meeting = Meeting(mentorship_id=mentorship_id, number=number)
        db.add(meeting)
    if agreed_time_text is not None:
        meeting.agreed_time_text = agreed_time_text
    if summary is not None:
        meeting.summary = summary
    if note:
        notes = list(meeting.progress_notes)
        notes.append(note)
        meeting.progress_notes = notes
    db.commit()
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/mentorships/{mentorship_id}/testimonial")
def leave_testimonial(
    mentorship_id: int,
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(...),
):
    ms = db.get(Mentorship, mentorship_id)
    if ms:
        db.add(
            Testimonial(
                mentorship_id=ms.id,
                student_id=ms.student_id,
                mentor_id=ms.mentor_id,
                text=text,
            )
        )
        if ms.status == "active":
            fsm.complete(ms)
        db.commit()
    return RedirectResponse(url=f"/mentorship/{mentorship_id}", status_code=303)


@router.post("/mentorships/{mentorship_id}/messages")
def send_message(
    mentorship_id: int,
    request: Request,
    db: Session = Depends(get_session),
    text: str = Form(...),
):
    """Append a chat message to the mentorship thread.

    Both participants may post in any state. Empty messages and posts from a
    non-participant are silently ignored (no write), then we redirect back so
    the thread re-renders on reload.
    """
    ms = db.get(Mentorship, mentorship_id)
    user = current_user(request, db)
    if ms and user and user.id in (ms.mentor_id, ms.student_id) and text.strip():
        db.add(Message(mentorship_id=ms.id, sender_id=user.id, text=text.strip()))
        db.commit()
    # Redirect back to the Messages tab (hash) so the full reload stays in chat.
    # NOTE: the "#messages" fragment pairs with the hash-based tab JS in
    # workspace.html; revisit if the overhaul moves tabs to partial swaps.
    return RedirectResponse(url=f"/mentorship/{mentorship_id}#messages", status_code=303)
