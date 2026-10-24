"""Tests for the demo role switcher redirect behavior.

Bugfix: POST /demo/role must land on the switched profile's dashboard
(/student/dashboard or /mentor/dashboard) instead of the landing page.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User
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


def _all_users(SessionMaker):
    db = SessionMaker()
    try:
        return [(u.id, u.role) for u in db.query(User).all()]
    finally:
        db.close()


# ── Property 1: Bug condition - role switcher redirects to matching dashboard ──

def test_switch_redirects_to_role_dashboard(client):
    """For every seeded user, POST /demo/role redirects to their dashboard."""
    c, SessionMaker = client
    expected = {
        "student": "/student/dashboard",
        "mentor": "/mentor/dashboard",
    }
    for uid, role in _all_users(SessionMaker):
        r = c.post("/demo/role", data={"user_id": uid}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == expected[role], (
            f"user {uid} ({role}) redirected to {r.headers['location']}"
        )


def test_switch_sets_session(client):
    """After switching, the dashboard renders as the switched user."""
    c, SessionMaker = client
    for uid, role in _all_users(SessionMaker):
        c.post("/demo/role", data={"user_id": uid}, follow_redirects=False)
        path = f"/{role}/dashboard"
        r = c.get(path)
        assert r.status_code == 200


# ── Property 2: Preservation - non-switch behavior unchanged ──

def test_reset_redirects_to_landing(client):
    c, _ = client
    r = c.post("/demo/reset", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_llm_mode_redirects_to_demo(client):
    c, _ = client
    r = c.post("/demo/llm_mode", data={"mode": "off"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/demo"


def test_sessionless_landing_shows_ctas(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "Student" in r.text
    assert "Mentor" in r.text


def test_unknown_user_falls_back_to_landing(client):
    """A user_id with no matching User falls back to /."""
    c, SessionMaker = client
    max_id = max(uid for uid, _ in _all_users(SessionMaker))
    for bad in (max_id + 1, max_id + 9999):
        r = c.post("/demo/role", data={"user_id": bad}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
