"""Integration tests for the standalone /messages chat page."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Mentorship, Message, User
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client(monkeypatch):
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

    from seed import _seed_all

    seed_db = TestingSession()
    _seed_all(seed_db)
    seed_db.commit()
    seed_db.close()

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, TestingSession

    app.dependency_overrides.clear()


def _active_mentorship(SessionMaker):
    db = SessionMaker()
    ms = (
        db.query(Mentorship)
        .filter(Mentorship.status == "active")
        .order_by(Mentorship.id.desc())
        .first()
    )
    ids = (ms.id, ms.mentor_id, ms.student_id)
    db.close()
    return ids


def test_participant_can_post_and_see_message(client):
    c, SessionMaker = client
    ms_id, mentor_id, _ = _active_mentorship(SessionMaker)
    c.post("/demo/role", data={"user_id": mentor_id}, follow_redirects=False)

    r = c.post("/messages", data={"text": "Welcome aboard"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/messages"

    r = c.get("/messages")
    assert r.status_code == 200
    assert "Welcome aboard" in r.text

    db = SessionMaker()
    assert db.query(Message).filter(Message.mentorship_id == ms_id).count() == 1
    db.close()


def test_empty_message_is_ignored(client):
    c, SessionMaker = client
    ms_id, mentor_id, _ = _active_mentorship(SessionMaker)
    c.post("/demo/role", data={"user_id": mentor_id}, follow_redirects=False)

    r = c.post("/messages", data={"text": "   "}, follow_redirects=False)
    assert r.status_code == 303

    db = SessionMaker()
    assert db.query(Message).filter(Message.mentorship_id == ms_id).count() == 0
    db.close()


def test_non_participant_cannot_post(client):
    c, SessionMaker = client
    ms_id, mentor_id, student_id = _active_mentorship(SessionMaker)

    # A user who is neither the mentor nor the student of any active mentorship.
    db = SessionMaker()
    outsider = (
        db.query(User)
        .filter(User.id.notin_([mentor_id, student_id]))
        .order_by(User.id)
        .first()
    )
    outsider_id = outsider.id
    db.close()

    c.post("/demo/role", data={"user_id": outsider_id}, follow_redirects=False)
    r = c.post("/messages", data={"text": "I should not be here"}, follow_redirects=False)
    assert r.status_code == 303

    db = SessionMaker()
    assert db.query(Message).filter(Message.mentorship_id == ms_id).count() == 0
    db.close()


def test_both_sides_build_a_conversation(client):
    c, SessionMaker = client
    ms_id, mentor_id, student_id = _active_mentorship(SessionMaker)

    c.post("/demo/role", data={"user_id": mentor_id}, follow_redirects=False)
    c.post("/messages", data={"text": "Hows the project going"}, follow_redirects=False)

    c.post("/demo/role", data={"user_id": student_id}, follow_redirects=False)
    c.post("/messages", data={"text": "Making progress"}, follow_redirects=False)

    r = c.get("/messages")
    assert "Hows the project going" in r.text
    assert "Making progress" in r.text

    db = SessionMaker()
    msgs = (
        db.query(Message)
        .filter(Message.mentorship_id == ms_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    assert [m.text for m in msgs] == ["Hows the project going", "Making progress"]
    db.close()
