"""End-to-end integration test walking the One Flow with LLM_MODE=off.

Uses an in-memory SQLite engine and a get_session dependency override so the
test is fully isolated from the on-disk app.db.
"""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client(monkeypatch):
    # Force LLM off so the flow is deterministic
    from app.settings import settings
    monkeypatch.setattr(settings, "llm_mode", "off")

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(engine, expire_on_commit=False)

    def override_get_session():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_get_session

    # Seed into this in-memory DB
    from seed import _seed_all
    seed_db = TestingSession()
    _seed_all(seed_db)
    seed_db.commit()
    seed_db.close()

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, TestingSession

    app.dependency_overrides.clear()


def test_one_flow_end_to_end(client):
    c, SessionMaker = client

    # 1. Student signup → matches
    r = c.post("/student/signup", data={
        "name": "Flow Maya",
        "goal_text": "Build an ML project",
        "goal_type": "build_project",
        "skills_to_learn": "python,machine_learning,data_analysis",
        "cadence": "weekly",
        "availability": "Mon-Evening,Tue-Evening,Wed-Evening",
        "top3": "hands_on_building,technical_depth,accountability",
        "resume_text": "I know some python and git",
        "skill_scores_json": "",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "/student/matches" in r.headers["location"]

    # 2. Matches page shows 3 cards
    r = c.get("/student/matches")
    assert r.status_code == 200
    assert r.text.count("Request intro meeting") == 3

    match_id = re.search(r'name="match_id" value="(\d+)"', r.text).group(1)

    # 3. Choose a mentor → Mentorship(requested)
    r = c.post("/student/requests", data={"match_id": match_id, "note": "Excited"}, follow_redirects=False)
    assert r.status_code == 303

    from app.db.models import Mentorship
    db = SessionMaker()
    ms = db.query(Mentorship).filter(Mentorship.status == "requested").order_by(Mentorship.id.desc()).first()
    msid, mentor_id, student_id = ms.id, ms.mentor_id, ms.student_id
    db.close()

    # 4. Mentor schedules the intro
    c.post("/demo/role", data={"user_id": mentor_id}, follow_redirects=False)
    r = c.get("/mentor/dashboard")
    assert r.status_code == 200

    r = c.post(f"/mentorships/{msid}/intro", data={"slot": "Tue-Evening"}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get(f"/api/mentorships/{msid}").json()["status"] == "intro_scheduled"

    # 5. Intro held
    r = c.post(f"/mentorships/{msid}/intro/held", follow_redirects=False)
    assert c.get(f"/api/mentorships/{msid}").json()["status"] == "intro_held"

    # 6. Mentor confirms (still pending overall)
    c.post(f"/mentorships/{msid}/decision", data={"choice": "confirm"}, follow_redirects=False)
    j = c.get(f"/api/mentorships/{msid}").json()
    assert j["mentor_decision"] == "confirmed"
    assert j["status"] == "intro_held"

    # 7. Student confirms → active
    c.post("/demo/role", data={"user_id": student_id}, follow_redirects=False)
    c.post(f"/mentorships/{msid}/decision", data={"choice": "confirm"}, follow_redirects=False)
    assert c.get(f"/api/mentorships/{msid}").json()["status"] == "active"

    # 8. Student proposes a deliverable
    r = c.post(f"/mentorships/{msid}/deliverables", data={"text": "Build a baseline model"}, follow_redirects=False)
    assert r.status_code == 303
    delivs = c.get(f"/api/mentorships/{msid}/deliverables").json()
    assert any(d["text"] == "Build a baseline model" for d in delivs)
    new_deliv = next(d for d in delivs if d["text"] == "Build a baseline model")
    assert new_deliv["status"] == "proposed"

    # 9. Mentor approves the deliverable
    c.post("/demo/role", data={"user_id": mentor_id}, follow_redirects=False)
    c.post(f"/deliverables/{new_deliv['id']}", data={"status": "approved"}, follow_redirects=False)
    delivs = c.get(f"/mentorships/{msid}/deliverables".replace("/mentorships", "/api/mentorships")).json()
    assert next(d for d in delivs if d["id"] == new_deliv["id"])["status"] == "approved"

    # 10. Student leaves testimonial → completed
    c.post("/demo/role", data={"user_id": student_id}, follow_redirects=False)
    r = c.post(f"/mentorships/{msid}/testimonial", data={"text": "Learned a ton!"}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get(f"/api/mentorships/{msid}").json()["status"] == "completed"


def test_decline_ends_mentorship(client):
    c, SessionMaker = client
    # Use the seeded intro_held mentorship (id=2)
    j = c.get("/api/mentorships/2").json()
    assert j["status"] == "intro_held"

    # Act as the mentor of mentorship 2 and decline
    mentor_id = j["mentor_id"]
    c.post("/demo/role", data={"user_id": mentor_id}, follow_redirects=False)
    c.post("/mentorships/2/decision", data={"choice": "decline"}, follow_redirects=False)
    assert c.get("/api/mentorships/2").json()["status"] == "ended"
