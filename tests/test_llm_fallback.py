"""Integration tests proving the LLM fallback paths work."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.services import llm as llm_module
from app.services.llm import LLMUnavailable, extract_skills


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.close()


class FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def complete_json(self, system, prompt, timeout_s=6.0):
        if self._exc:
            raise self._exc
        return self._response


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(llm_module, "get_llm_client", lambda db: client)


def test_valid_json_parsed(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient('{"skills": {"python": 0.8, "docker": 0.6}}'))
    result = extract_skills("resume text", db)
    assert result == {"python": 0.8, "docker": 0.6}


def test_malformed_json_falls_back(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient("{broken json"))
    # Fallback scans the text itself
    result = extract_skills("I know python and docker", db)
    assert "python" in result
    assert "docker" in result


def test_timeout_falls_back(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient(exc=TimeoutError("too slow")))
    result = extract_skills("python developer", db)
    assert "python" in result  # from fallback keyword scan


def test_unavailable_falls_back(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient(exc=LLMUnavailable("off")))
    result = extract_skills("python and react", db)
    assert "python" in result
    assert "react" in result


def test_unknown_skill_ids_dropped(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient('{"skills": {"python": 0.8, "quantumwizardry": 0.9}}'))
    result = extract_skills("resume", db)
    assert "python" in result
    assert "quantumwizardry" not in result


def test_confidence_clamped(monkeypatch, db):
    _patch_client(monkeypatch, FakeClient('{"skills": {"python": 1.5, "docker": -0.2}}'))
    result = extract_skills("resume", db)
    assert result["python"] == 1.0
    assert result["docker"] == 0.0
