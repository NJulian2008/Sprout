"""
seed.py — Sprout demo seed data.

Creates all mentor/student users, profiles, matches, mentorships, meetings,
deliverables, testimonials, the LLM cache entry for Maya's rerank, and
initials-based SVG avatars for every user.

Usage:
    python seed.py                 # run directly
    python -m pytest seed.py       # no-op (no tests here)

The module is also imported by app.db.session.reset_db() via a deferred import
to avoid circular-import issues.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.models import (
    Deliverable,
    LLMCache,
    Match,
    Meeting,
    MentorProfile,
    Mentorship,
    StudentRequest,
    Testimonial,
    User,
)
from app.db.session import SessionLocal
from app.services.prompts import RERANK_SYSTEM, RERANK_USER_TEMPLATE
from app.services.skills import experience_level

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _ago(days: int = 0, hours: int = 0) -> datetime:
    return _now() - timedelta(days=days, hours=hours)


def _cache_key(system: str, prompt: str) -> str:
    return hashlib.sha256((system + prompt).encode()).hexdigest()


def _make_svg(initials: str, color: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
        f'<circle cx="40" cy="40" r="40" fill="{color}"/>'
        f'<text x="40" y="48" font-family="system-ui" font-size="24" '
        f'font-weight="bold" fill="white" text-anchor="middle">{initials}</text>'
        "</svg>"
    )


def _write_avatars(users: list[dict]) -> None:
    """Write SVG avatar files to app/static/avatars/."""
    avatar_dir = Path(__file__).parent / "app" / "static" / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    for u in users:
        svg = _make_svg(u["initials"], u["color"])
        (avatar_dir / f"avatar_{u['id']}.svg").write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------------------
# Color constants
# ---------------------------------------------------------------------------

FACULTY_COLOR = "#4a7c59"
INDUSTRY_COLOR = "#2563eb"
STUDENT_COLOR = "#7c3aed"


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------


def seed() -> None:  # noqa: PLR0915
    """Populate the database with demo data and generate SVG avatars."""

    db = SessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()


def _seed_all(db) -> None:  # noqa: PLR0912, PLR0915
    # ------------------------------------------------------------------ #
    # 1. MENTOR USERS + MentorProfiles                                     #
    # ------------------------------------------------------------------ #

    mentors_data = [
        # (id, name, role, title, org, mentor_type, bio_short,
        #  skill_scores, outcomes, availability, top3, max_students)
        {
            "id": 1,
            "name": "Dr. Sarah Chen",
            "title": "Associate Professor of Computer Science",
            "org": "Ohio State University",
            "mentor_type": "faculty",
            "bio_short": "ML researcher and educator. I love helping students publish their first paper.",
            "skill_scores": {
                "python": 0.9,
                "machine_learning": 1.0,
                "deep_learning": 0.9,
                "nlp": 0.85,
                "data_analysis": 0.8,
                "statistics": 0.85,
                "research": 0.9,
                "pytorch": 0.8,
                "tensorflow": 0.7,
            },
            "outcomes": ["learn_skill", "research"],
            "availability": [
                "Mon-Morning",
                "Mon-Evening",
                "Wed-Morning",
                "Wed-Evening",
                "Fri-Morning",
            ],
            "top3": ["technical_depth", "clear_feedback", "big_picture"],
            "max_students": 2,
        },
        {
            "id": 2,
            "name": "Marcus Johnson",
            "title": "Senior Software Engineer",
            "org": "Honda Research Institute",
            "mentor_type": "industry",
            "bio_short": "10 years building production systems. I help students ship real software.",
            "skill_scores": {
                "python": 0.9,
                "javascript": 0.7,
                "react": 0.6,
                "nodejs": 0.6,
                "sql": 0.8,
                "docker": 0.8,
                "aws": 0.75,
                "system_design": 0.85,
                "rest_api": 0.8,
                "git": 0.9,
                "cicd": 0.7,
            },
            "outcomes": ["build_project", "career_navigation"],
            "availability": ["Tue-Evening", "Thu-Evening", "Sat-Morning", "Sat-Afternoon"],
            "top3": ["hands_on_building", "accountability", "technical_depth"],
            "max_students": 2,
        },
        {
            "id": 3,
            "name": "Priya Patel",
            "title": "Machine Learning Engineer",
            "org": "Google",
            "mentor_type": "industry",
            "bio_short": "Building production ML systems at scale. Love mentoring the next generation.",
            "skill_scores": {
                "python": 0.9,
                "machine_learning": 0.9,
                "deep_learning": 0.8,
                "tensorflow": 0.85,
                "data_analysis": 0.75,
                "statistics": 0.7,
                "computer_vision": 0.8,
                "numpy": 0.8,
                "pandas": 0.75,
            },
            "outcomes": ["learn_skill", "build_project"],
            "availability": ["Mon-Evening", "Tue-Evening", "Wed-Evening", "Thu-Evening"],
            "top3": ["technical_depth", "hands_on_building", "clear_feedback"],
            "max_students": 2,
        },
        {
            "id": 4,
            "name": "James Rodriguez",
            "title": "Senior Product Manager",
            "org": "TechBridge Startup",
            "mentor_type": "industry",
            "bio_short": "Bridging tech and business. I help engineers transition into PM roles.",
            "skill_scores": {
                "product_management": 0.85,
                "agile": 0.8,
                "project_management": 0.75,
                "system_design": 0.6,
                "sql": 0.5,
                "python": 0.4,
                "ux_design": 0.65,
                "technical_writing": 0.7,
            },
            "outcomes": ["career_navigation", "build_project"],
            "availability": [
                "Mon-Morning",
                "Tue-Morning",
                "Wed-Morning",
                "Thu-Morning",
                "Fri-Morning",
            ],
            "top3": ["big_picture", "career_guidance", "clear_feedback"],
            "max_students": 2,
        },
        {
            "id": 5,
            "name": "Dr. Emily Watson",
            "title": "Assistant Professor of Data Science",
            "org": "Ohio State University",
            "mentor_type": "faculty",
            "bio_short": "Data science educator. I make statistics and ML accessible to everyone.",
            "skill_scores": {
                "python": 0.8,
                "data_analysis": 0.9,
                "statistics": 0.9,
                "machine_learning": 0.75,
                "pandas": 0.85,
                "numpy": 0.8,
                "sql": 0.7,
                "research": 0.8,
                "probability": 0.85,
            },
            "outcomes": ["learn_skill", "research"],
            "availability": ["Tue-Morning", "Thu-Morning", "Tue-Evening", "Thu-Evening"],
            "top3": ["clear_feedback", "technical_depth", "accountability"],
            "max_students": 3,
        },
        {
            "id": 6,
            "name": "Kevin Park",
            "title": "Staff DevOps Engineer",
            "org": "CloudWave Inc.",
            "mentor_type": "industry",
            "bio_short": "Automating everything. I help students understand modern cloud infrastructure.",
            "skill_scores": {
                "docker": 0.9,
                "aws": 0.85,
                "cicd": 0.9,
                "linux": 0.85,
                "python": 0.65,
                "bash": 0.8,
                "kubernetes": 0.8,
                "networking": 0.7,
                "git": 0.8,
            },
            "outcomes": ["build_project", "learn_skill"],
            "availability": ["Mon-Evening", "Wed-Evening", "Fri-Evening", "Sat-Morning"],
            "top3": ["hands_on_building", "technical_depth", "flexible_schedule"],
            "max_students": 2,
        },
        {
            "id": 7,
            "name": "Dr. Aisha Williams",
            "title": "Associate Professor of Human-Computer Interaction",
            "org": "Ohio State University",
            "mentor_type": "faculty",
            "bio_short": "HCI researcher focused on accessibility and inclusive design.",
            "skill_scores": {
                "ux_design": 0.9,
                "figma": 0.85,
                "research": 0.8,
                "technical_writing": 0.75,
                "html": 0.6,
                "css": 0.65,
                "javascript": 0.5,
                "product_management": 0.6,
            },
            "outcomes": ["learn_skill", "build_project"],
            "availability": ["Mon-Morning", "Wed-Morning", "Mon-Evening", "Wed-Evening"],
            "top3": ["clear_feedback", "big_picture", "casual_friendly"],
            "max_students": 2,
        },
        {
            "id": 8,
            "name": "David Kim",
            "title": "Full-Stack Developer",
            "org": "Freelance / OSU Alum",
            "mentor_type": "industry",
            "bio_short": "OSU alum who went indie. I help students build their first portfolio projects.",
            "skill_scores": {
                "python": 0.6,
                "javascript": 0.7,
                "react": 0.65,
                "nodejs": 0.6,
                "html": 0.75,
                "css": 0.7,
                "sql": 0.55,
                "git": 0.7,
                "rest_api": 0.6,
            },
            "outcomes": ["build_project", "learn_skill"],
            "availability": ["Tue-Evening", "Thu-Evening", "Fri-Evening", "Sat-Evening"],
            "top3": ["hands_on_building", "flexible_schedule", "casual_friendly"],
            "max_students": 3,
        },
    ]

    # experience_score values specified in the task (pre-validated)
    mentor_exp_scores = {
        1: 0.9,
        2: 0.82,
        3: 0.78,
        4: 0.62,
        5: 0.74,
        6: 0.70,
        7: 0.68,
        8: 0.55,
    }

    specialties_by_mentor = {
        1: ["computer_science", "artificial_intelligence"],
        2: ["automotive", "computer_science"],
        3: ["artificial_intelligence", "computer_science"],
        4: ["computer_science", "industrial"],
        5: ["artificial_intelligence", "computer_science"],
        6: ["computer_science", "industrial"],
        7: ["computer_science"],
        8: ["computer_science"],
    }
    for m in mentors_data:
        user = User(
            id=m["id"],
            role="mentor",
            name=m["name"],
            headshot_url=f"/static/avatars/avatar_{m['id']}.svg",
            bio_short=m["bio_short"],
            title=m["title"],
            org=m["org"],
            mentor_type=m["mentor_type"],
        )
        db.add(user)

    # Flush so User rows exist before MentorProfile FK references them.
    # (User and MentorProfile have no ORM relationship, so SQLAlchemy cannot
    # infer insert ordering on its own.)
    db.flush()

    for m in mentors_data:
        exp_s = mentor_exp_scores[m["id"]]
        profile = MentorProfile(
            user_id=m["id"],
            skill_scores=m["skill_scores"],
            experience_score=exp_s,
            experience_level=experience_level(exp_s),
            specialties=specialties_by_mentor[m["id"]],
            outcomes=m["outcomes"],
            availability=m["availability"],
            top3=m["top3"],
            max_students=m["max_students"],
        )
        db.add(profile)

    # ------------------------------------------------------------------ #
    # 2. STUDENT USERS + StudentRequests                                   #
    # ------------------------------------------------------------------ #

    students_data = [
        {
            "id": 9,
            "name": "Maya Okonkwo",
            "major": "Computer Science",
            "year": "2nd year",
            "bio_short": "2nd-year CS student eager to build my first ML project.",
            "goal_text": "I want to build my first real machine learning project",
            "goal_type": "build_project",
            "skills_to_learn": ["python", "machine_learning", "data_analysis"],
            "skill_scores": {"python": 0.3, "html": 0.2, "css": 0.2, "git": 0.3},
            "experience_score": 0.275,
            "experience_level": "beginner",
            "cadence": "weekly",
            "availability": ["Mon-Evening", "Tue-Evening", "Wed-Evening", "Thu-Evening"],
            "top3": ["hands_on_building", "technical_depth", "accountability"],
        },
        {
            "id": 10,
            "name": "Alex Torres",
            "major": "Electrical Engineering",
            "year": "3rd year",
            "bio_short": "EE student interested in embedded systems and IoT.",
            "goal_text": "Learn embedded systems and IoT development",
            "goal_type": "learn_skill",
            "skills_to_learn": ["embedded", "python", "networking"],
            "skill_scores": {"c": 0.5, "cpp": 0.55, "python": 0.4, "algorithms": 0.6, "linux": 0.5},
            "experience_score": 0.52,
            "experience_level": "intermediate",
            "cadence": "every_other_week",
            "availability": ["Sat-Morning", "Sat-Afternoon", "Sun-Morning"],
            "top3": ["technical_depth", "hands_on_building", "flexible_schedule"],
        },
        {
            "id": 11,
            "name": "Jordan Lee",
            "major": "Computer Science",
            "year": "4th year",
            "bio_short": "Senior CS student building toward an industry ML role.",
            "goal_text": "Build a production ML pipeline and prepare for industry",
            "goal_type": "build_project",
            "skills_to_learn": ["machine_learning", "deep_learning", "system_design"],
            "skill_scores": {
                "python": 0.8,
                "machine_learning": 0.7,
                "data_analysis": 0.75,
                "sql": 0.7,
                "git": 0.8,
                "docker": 0.65,
                "statistics": 0.7,
            },
            "experience_score": 0.75,
            "experience_level": "advanced",
            "cadence": "weekly",
            "availability": ["Mon-Evening", "Tue-Evening", "Wed-Evening"],
            "top3": ["technical_depth", "hands_on_building", "accountability"],
        },
        {
            "id": 12,
            "name": "Sam Rivera",
            "major": "Information Systems",
            "year": "1st year",
            "bio_short": "1st-year IS student learning web development from scratch.",
            "goal_text": "Learn web development and build a portfolio website",
            "goal_type": "build_project",
            "skills_to_learn": ["html", "css", "javascript", "react"],
            "skill_scores": {"html": 0.3, "css": 0.25},
            "experience_score": 0.28,
            "experience_level": "beginner",
            "cadence": "weekly",
            "availability": ["Tue-Evening", "Thu-Evening", "Sat-Morning"],
            "top3": ["hands_on_building", "casual_friendly", "clear_feedback"],
        },
        {
            "id": 13,
            "name": "Chris Kim",
            "major": "Data Science",
            "year": "3rd year",
            "bio_short": "Data Science student looking to sharpen ML and stats skills.",
            "goal_text": "Improve my data analysis skills and learn ML",
            "goal_type": "learn_skill",
            "skills_to_learn": ["machine_learning", "statistics", "pandas"],
            "skill_scores": {"python": 0.5, "pandas": 0.45, "sql": 0.5, "statistics": 0.4},
            "experience_score": 0.48,
            "experience_level": "intermediate",
            "cadence": "every_other_week",
            "availability": ["Mon-Morning", "Wed-Morning", "Fri-Morning"],
            "top3": ["technical_depth", "clear_feedback", "accountability"],
        },
        {
            "id": 14,
            "name": "Zoe Martinez",
            "major": "Computer Science",
            "year": "4th year",
            "bio_short": "CS senior pivoting toward product management.",
            "goal_text": "Break into product management from engineering",
            "goal_type": "career_navigation",
            "skills_to_learn": ["product_management", "ux_design", "agile"],
            "skill_scores": {
                "python": 0.6,
                "javascript": 0.5,
                "git": 0.65,
                "sql": 0.5,
                "agile": 0.4,
            },
            "experience_score": 0.55,
            "experience_level": "intermediate",
            "cadence": "weekly",
            "availability": ["Mon-Morning", "Tue-Morning", "Wed-Morning"],
            "top3": ["big_picture", "career_guidance", "clear_feedback"],
        },
    ]

    request_id_map: dict[int, int] = {}  # student_id → request_id
    for s in students_data:
        user = User(
            id=s["id"],
            role="student",
            name=s["name"],
            headshot_url=f"/static/avatars/avatar_{s['id']}.svg",
            bio_short=s["bio_short"],
            major=s["major"],
            year=s["year"],
        )
        db.add(user)

    # Flush student User rows before creating StudentRequest FK references.
    db.flush()

    # Insert StudentRequests one at a time and flush after each so the
    # autoincrement id is assigned immediately.  (A single batched insert
    # triggers SQLAlchemy's "insertmanyvalues" path, which rejects the
    # nullable autoincrement primary key as a sentinel column.)
    for s in students_data:
        req = StudentRequest(
            student_id=s["id"],
            goal_text=s["goal_text"],
            goal_type=s["goal_type"],
            skills_to_learn=s["skills_to_learn"],
            skill_scores=s["skill_scores"],
            experience_score=s["experience_score"],
            experience_level=s["experience_level"],
            cadence=s["cadence"],
            availability=s["availability"],
            top3=s["top3"],
            created_at=_ago(days=30),
        )
        db.add(req)
        db.flush()
        request_id_map[s["id"]] = req.id

    # ------------------------------------------------------------------ #
    # 3. MAYA'S MATCH ROWS (rank 1=Priya, 2=Sarah, 3=Emily)               #
    # ------------------------------------------------------------------ #

    maya_request_id = request_id_map[9]

    # Scores computed using matching.compute_score with actual constants:
    # Priya  (3): 93.4187  — wins skills_fit + outcome_fit + availability_fit
    # Sarah  (1): 52.6104  — wins skills_fit coverage depth, weaker on outcome/avail
    # Emily  (5): 55.3854  — wins level_fit (closest exp gap ~0.47), weaker outcome
    #
    # Note: Emily's raw score is slightly higher than Sarah's (55 vs 52) but we
    # present them as rank 2 (Sarah) and rank 3 (Emily) per the spec requirement
    # that each "wins on something different" — Sarah on pure ML depth, Emily on
    # level fit.  The LLM rerank (cached below) sets the final ordering.

    matches_data = [
        {
            "mentor_id": 3,  # Priya Patel
            "rank": 1,
            "score": 93.42,
            "score_breakdown": {
                "skills_fit": 0.8538,
                "skills_fit_detail": {"coverage": 0.85, "level_fit": 0.8625},
                "outcome_fit": 1.0,
                "availability_fit": 1.0,
            },
            "explanation": (
                "Priya is an intermediate-to-advanced ML engineer at Google with strong "
                "Python and machine learning skills — exactly what you want to learn. "
                "She's free most evenings, which overlaps perfectly with your schedule."
            ),
        },
        {
            "mentor_id": 1,  # Dr. Sarah Chen
            "rank": 2,
            "score": 52.61,
            "score_breakdown": {
                "skills_fit": 0.7987,
                "skills_fit_detail": {"coverage": 0.9, "level_fit": 0.5625},
                "outcome_fit": 0.0,
                "availability_fit": 0.6667,
            },
            "explanation": (
                "Dr. Chen is an expert in machine learning and NLP with a decade of "
                "research experience. As a professor, she's skilled at teaching concepts "
                "from the ground up, and your Monday/Wednesday evenings overlap."
            ),
        },
        {
            "mentor_id": 5,  # Dr. Emily Watson
            "rank": 3,
            "score": 55.39,
            "score_breakdown": {
                "skills_fit": 0.8604,
                "skills_fit_detail": {"coverage": 0.8167, "level_fit": 0.9625},
                "outcome_fit": 0.0,
                "availability_fit": 0.6667,
            },
            "explanation": (
                "Dr. Watson's data science background and teaching style make her an "
                "ideal step ahead of your beginner level — she'll stretch you without "
                "leaving you behind. Your Tuesday and Thursday evenings align well."
            ),
        },
    ]

    for i, m in enumerate(matches_data):
        match = Match(
            id=i + 1,
            request_id=maya_request_id,
            mentor_id=m["mentor_id"],
            rank=m["rank"],
            score=m["score"],
            score_breakdown=m["score_breakdown"],
            explanation=m["explanation"],
            source="cached",
        )
        db.add(match)

    # ------------------------------------------------------------------ #
    # 4. MENTORSHIP RECORDS                                                #
    # ------------------------------------------------------------------ #

    jordan_request_id = request_id_map[11]
    chris_request_id = request_id_map[13]
    zoe_request_id = request_id_map[14]

    # Mentorship 1: Marcus ↔ Jordan — active, mid-flight (started 14 days ago)
    ms1 = Mentorship(
        id=1,
        mentor_id=2,  # Marcus Johnson
        student_id=11,  # Jordan Lee
        request_id=jordan_request_id,
        status="active",
        cadence="weekly",
        duration_weeks=6,
        mentor_decision="confirmed",
        student_decision="confirmed",
        started_at=_ago(days=14),
    )
    db.add(ms1)

    # Mentorship 2: Emily ↔ Chris — intro held, awaiting confirmation
    ms2 = Mentorship(
        id=2,
        mentor_id=5,  # Dr. Emily Watson
        student_id=13,  # Chris Kim
        request_id=chris_request_id,
        status="intro_held",
        cadence="every_other_week",
        mentor_decision="pending",
        student_decision="pending",
    )
    db.add(ms2)

    # Mentorship 3: Sarah ↔ Zoe — completed (60 days ago → 10 days ago)
    ms3 = Mentorship(
        id=3,
        mentor_id=1,  # Dr. Sarah Chen
        student_id=14,  # Zoe Martinez
        request_id=zoe_request_id,
        status="completed",
        cadence="weekly",
        duration_weeks=8,
        mentor_decision="confirmed",
        student_decision="confirmed",
        started_at=_ago(days=60),
        completed_at=_ago(days=10),
    )
    db.add(ms3)

    # Flush Mentorship rows before Meeting / Deliverable / Testimonial inserts
    # reference their FK (no ORM relationship defined to infer ordering).
    db.flush()

    # ------------------------------------------------------------------ #
    # 5. MEETINGS                                                          #
    # ------------------------------------------------------------------ #

    # Mentorship 1 (Marcus ↔ Jordan): 2 meetings, both held
    meetings_ms1 = [
        Meeting(
            id=1,
            mentorship_id=1,
            number=0,
            agreed_time_text="Tuesday 7pm — intro",
            status="held",
            summary="Intro meeting. Jordan shared project ideas; Marcus outlined the 6-week plan.",
            progress_notes=["Intro complete", "Jordan's goal: production ML pipeline"],
            next_deliverable_ids=[1],
        ),
        Meeting(
            id=2,
            mentorship_id=1,
            number=1,
            agreed_time_text="Tuesday 7pm — week 2",
            status="held",
            summary="Jordan completed the Docker setup and pushed the first CI workflow.",
            progress_notes=[
                "Dockerized the project",
                "GitHub Actions CI pipeline running",
                "Next: data ingestion module",
            ],
            next_deliverable_ids=[2, 3],
        ),
    ]
    for m in meetings_ms1:
        db.add(m)

    # Mentorship 2 (Emily ↔ Chris): 1 intro meeting, held
    meetings_ms2 = [
        Meeting(
            id=3,
            mentorship_id=2,
            number=0,
            agreed_time_text="Thursday 7pm — intro",
            status="held",
            summary="Intro meeting. Chris shared current skill gaps; Emily outlined learning path.",
            progress_notes=["Intro complete", "Focus: statistics + pandas workflow"],
            next_deliverable_ids=[4, 5],
        ),
    ]
    for m in meetings_ms2:
        db.add(m)

    # Mentorship 3 (Sarah ↔ Zoe): 4 meetings, all held
    meetings_ms3 = [
        Meeting(
            id=4,
            mentorship_id=3,
            number=0,
            agreed_time_text="Monday 6pm — intro",
            status="held",
            summary="Intro. Zoe shared her PM transition goal; Sarah sketched a research-to-PM narrative arc.",
            progress_notes=["Intro complete", "Goal: PM portfolio + paper draft"],
            next_deliverable_ids=[6],
        ),
        Meeting(
            id=5,
            mentorship_id=3,
            number=1,
            agreed_time_text="Monday 6pm — week 2",
            status="held",
            summary="Reviewed PM case study draft. Significant structural feedback given.",
            progress_notes=["Case study draft reviewed", "Revised thesis statement agreed"],
            next_deliverable_ids=[7],
        ),
        Meeting(
            id=6,
            mentorship_id=3,
            number=2,
            agreed_time_text="Monday 6pm — week 4",
            status="held",
            summary="Paper draft complete. Polished together; ready for submission.",
            progress_notes=["Paper draft finalized", "Submitted to OSU undergrad journal"],
            next_deliverable_ids=[8],
        ),
        Meeting(
            id=7,
            mentorship_id=3,
            number=3,
            agreed_time_text="Monday 6pm — week 8",
            status="held",
            summary="Closing meeting. Reviewed Zoe's growth and next steps for PM job search.",
            progress_notes=["Mentorship closed", "Zoe has PM portfolio and paper submission"],
            next_deliverable_ids=[],
        ),
    ]
    for m in meetings_ms3:
        db.add(m)

    # ------------------------------------------------------------------ #
    # 6. DELIVERABLES                                                      #
    # ------------------------------------------------------------------ #

    deliverables = [
        # Mentorship 1 (Marcus ↔ Jordan)
        Deliverable(
            id=1,
            mentorship_id=1,
            text="Set up Dockerized Python project with a working Makefile",
            mentor_annotation="Great job on the multi-stage Dockerfile!",
            status="done",
            due_meeting=1,
        ),
        Deliverable(
            id=2,
            mentorship_id=1,
            text="Implement GitHub Actions CI pipeline with pytest",
            mentor_annotation="Approved — tests are running on every push.",
            status="approved",
            due_meeting=2,
        ),
        Deliverable(
            id=3,
            mentorship_id=1,
            text="Draft the data ingestion module with a CSV loader",
            mentor_annotation="",
            status="proposed",
            due_meeting=3,
        ),
        # Mentorship 2 (Emily ↔ Chris)
        Deliverable(
            id=4,
            mentorship_id=2,
            text="Complete pandas EDA on a public dataset and write a 1-page summary",
            mentor_annotation="",
            status="proposed",
            due_meeting=1,
        ),
        Deliverable(
            id=5,
            mentorship_id=2,
            text="Review the 'Statistics for Data Science' chapter on probability distributions",
            mentor_annotation="",
            status="proposed",
            due_meeting=1,
        ),
        # Mentorship 3 (Sarah ↔ Zoe)
        Deliverable(
            id=6,
            mentorship_id=3,
            text="Write a 500-word PM case study on a product you admire",
            mentor_annotation="Strong first draft — clarify the problem statement.",
            status="done",
            due_meeting=1,
        ),
        Deliverable(
            id=7,
            mentorship_id=3,
            text="Revise case study with clearer thesis and data-backed claims",
            mentor_annotation="Excellent revision — ready to include in portfolio.",
            status="done",
            due_meeting=2,
        ),
        Deliverable(
            id=8,
            mentorship_id=3,
            text="Complete paper draft on user research methods in PM",
            mentor_annotation="Approved — submitted to undergrad journal.",
            status="done",
            due_meeting=3,
        ),
        Deliverable(
            id=9,
            mentorship_id=3,
            text="Update LinkedIn and portfolio with PM narrative",
            mentor_annotation="Done — great profile update.",
            status="done",
            due_meeting=4,
        ),
    ]
    for d in deliverables:
        db.add(d)

    # ------------------------------------------------------------------ #
    # 7. TESTIMONIALS                                                      #
    # ------------------------------------------------------------------ #

    testimonials = [
        Testimonial(
            id=1,
            mentorship_id=3,
            student_id=14,  # Zoe Martinez
            mentor_id=1,  # Dr. Sarah Chen
            text=(
                "Dr. Chen completely changed how I think about research problems. "
                "Her feedback was direct and she genuinely cared about my growth. "
                "I shipped a paper draft I'm proud of."
            ),
            created_at=_ago(days=10),
        ),
    ]
    for t in testimonials:
        db.add(t)

    # ------------------------------------------------------------------ #
    # 8. LLM CACHE — Maya's rerank response                               #
    # ------------------------------------------------------------------ #

    # Build the exact student_json and candidates_json the rerank call will use
    # so the cache key matches at runtime.
    student_json_obj = {
        "student_id": 9,
        "goal_type": "build_project",
        "skills_to_learn": ["python", "machine_learning", "data_analysis"],
        "skill_scores": {"python": 0.3, "html": 0.2, "css": 0.2, "git": 0.3},
        "experience_score": 0.275,
        "experience_level": "beginner",
        "availability": ["Mon-Evening", "Tue-Evening", "Wed-Evening", "Thu-Evening"],
    }
    candidates_json_obj = [
        {
            "mentor_id": "3",
            "mentor_name": "Priya Patel",
            "skill_scores": {
                "python": 0.9,
                "machine_learning": 0.9,
                "deep_learning": 0.8,
                "tensorflow": 0.85,
                "data_analysis": 0.75,
                "statistics": 0.7,
                "computer_vision": 0.8,
                "numpy": 0.8,
                "pandas": 0.75,
            },
            "experience_score": 0.78,
            "experience_level": "advanced",
            "outcomes": ["learn_skill", "build_project"],
            "availability": ["Mon-Evening", "Tue-Evening", "Wed-Evening", "Thu-Evening"],
            "shared_skills": ["python", "machine_learning", "data_analysis"],
            "student_level": "beginner",
            "overlap_summary": "Mon/Tue/Wed/Thu evenings",
        },
        {
            "mentor_id": "1",
            "mentor_name": "Dr. Sarah Chen",
            "skill_scores": {
                "python": 0.9,
                "machine_learning": 1.0,
                "deep_learning": 0.9,
                "nlp": 0.85,
                "data_analysis": 0.8,
                "statistics": 0.85,
                "research": 0.9,
                "pytorch": 0.8,
                "tensorflow": 0.7,
            },
            "experience_score": 0.9,
            "experience_level": "advanced",
            "outcomes": ["learn_skill", "research"],
            "availability": [
                "Mon-Morning",
                "Mon-Evening",
                "Wed-Morning",
                "Wed-Evening",
                "Fri-Morning",
            ],
            "shared_skills": ["python", "machine_learning", "data_analysis"],
            "student_level": "beginner",
            "overlap_summary": "Mon/Wed evenings",
        },
        {
            "mentor_id": "5",
            "mentor_name": "Dr. Emily Watson",
            "skill_scores": {
                "python": 0.8,
                "data_analysis": 0.9,
                "statistics": 0.9,
                "machine_learning": 0.75,
                "pandas": 0.85,
                "numpy": 0.8,
                "sql": 0.7,
                "research": 0.8,
                "probability": 0.85,
            },
            "experience_score": 0.74,
            "experience_level": "advanced",
            "outcomes": ["learn_skill", "research"],
            "availability": ["Tue-Morning", "Thu-Morning", "Tue-Evening", "Thu-Evening"],
            "shared_skills": ["python", "machine_learning", "data_analysis"],
            "student_level": "beginner",
            "overlap_summary": "Tue/Thu evenings",
        },
    ]

    student_json_str = json.dumps(student_json_obj)
    candidates_json_str = json.dumps(candidates_json_obj)
    rerank_prompt = RERANK_USER_TEMPLATE.format(
        student_json=student_json_str,
        candidates_json=candidates_json_str,
    )
    llm_cache_key = _cache_key(RERANK_SYSTEM, rerank_prompt)

    llm_response = json.dumps(
        {
            "matches": [
                {
                    "mentor_id": "3",
                    "rank": 1,
                    "explanation": (
                        "Priya is an intermediate-to-advanced ML engineer at Google with strong "
                        "Python and machine learning skills — exactly what you want to learn. "
                        "She's free most evenings, which overlaps perfectly with your schedule."
                    ),
                },
                {
                    "mentor_id": "1",
                    "rank": 2,
                    "explanation": (
                        "Dr. Chen is an expert in machine learning and NLP with a decade of "
                        "research experience. As a professor, she's skilled at teaching concepts "
                        "from the ground up, and your Monday/Wednesday evenings overlap."
                    ),
                },
                {
                    "mentor_id": "5",
                    "rank": 3,
                    "explanation": (
                        "Dr. Watson's data science background and teaching style make her an "
                        "ideal step ahead of your beginner level — she'll stretch you without "
                        "leaving you behind. Your Tuesday and Thursday evenings align well."
                    ),
                },
            ]
        }
    )

    db.add(LLMCache(key=llm_cache_key, response=llm_response))

    # ------------------------------------------------------------------ #
    # 9. COMMIT                                                             #
    # ------------------------------------------------------------------ #

    db.commit()

    # ------------------------------------------------------------------ #
    # 10. SVG AVATARS                                                       #
    # ------------------------------------------------------------------ #

    avatar_users = [
        # Mentors
        {"id": 1, "initials": "SC", "color": FACULTY_COLOR},  # Dr. Sarah Chen
        {"id": 2, "initials": "MJ", "color": INDUSTRY_COLOR},  # Marcus Johnson
        {"id": 3, "initials": "PP", "color": INDUSTRY_COLOR},  # Priya Patel
        {"id": 4, "initials": "JR", "color": INDUSTRY_COLOR},  # James Rodriguez
        {"id": 5, "initials": "EW", "color": FACULTY_COLOR},  # Dr. Emily Watson
        {"id": 6, "initials": "KP", "color": INDUSTRY_COLOR},  # Kevin Park
        {"id": 7, "initials": "AW", "color": FACULTY_COLOR},  # Dr. Aisha Williams
        {"id": 8, "initials": "DK", "color": INDUSTRY_COLOR},  # David Kim
        # Students
        {"id": 9, "initials": "MO", "color": STUDENT_COLOR},  # Maya Okonkwo
        {"id": 10, "initials": "AT", "color": STUDENT_COLOR},  # Alex Torres
        {"id": 11, "initials": "JL", "color": STUDENT_COLOR},  # Jordan Lee
        {"id": 12, "initials": "SR", "color": STUDENT_COLOR},  # Sam Rivera
        {"id": 13, "initials": "CK", "color": STUDENT_COLOR},  # Chris Kim
        {"id": 14, "initials": "ZM", "color": STUDENT_COLOR},  # Zoe Martinez
    ]
    _write_avatars(avatar_users)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    seed()
