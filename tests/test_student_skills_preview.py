"""Bug condition exploration test for the student-side resume skills preview.

Property 1: Bug Condition — Student resume preview renders extracted skills.

These tests encode the EXPECTED (post-fix) behavior. On UNFIXED code they are
expected to FAIL — the failures are the counterexamples that confirm the bug:
the student sign-up page has no `#skill-chips-result` target, the resume input
carries no HTMX trigger, and `POST /student/skills/extract` reads a `text`
field rather than the uploaded file, so a real resume yields an empty fragment.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3

Fixture pattern mirrors tests/test_flow_api.py: in-memory SQLite engine with a
`get_session` dependency override and `settings.llm_mode = "off"` for
deterministic (fallback) skill extraction.
"""

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
    # Force LLM off so skill extraction is deterministic (fallback_extract).
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

    # Seed into this in-memory DB (taxonomy + skills resolution).
    from seed import _seed_all

    seed_db = TestingSession()
    _seed_all(seed_db)
    seed_db.commit()
    seed_db.close()

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, TestingSession

    app.dependency_overrides.clear()


# ── Test case A: the preview target element must exist ──────────────────────────


def test_student_signup_has_skill_chips_result_target(client):
    """Bug Condition: `skillChipsResultElementExists` is false on unfixed code.

    Requirements 1.1, 2.1
    """
    c, _ = client
    r = c.get("/student/signup")
    assert r.status_code == 200
    assert 'id="skill-chips-result"' in r.text, (
        "Counterexample: #skill-chips-result is absent from /student/signup "
        "(the preview partial is never included)."
    )


# ── Test case B: the resume input must carry the HTMX preview trigger ───────────


def test_student_resume_input_has_htmx_preview_trigger(client):
    """Bug Condition: `skillsPreviewRequestIssued` is false on unfixed code.

    Requirements 1.2, 2.2
    """
    c, _ = client
    r = c.get("/student/signup")
    assert r.status_code == 200
    html = r.text

    assert 'hx-post="/student/skills/extract"' in html, (
        "Counterexample: resume input has no hx-post to /student/skills/extract."
    )
    assert 'hx-target="#skill-chips-result"' in html, (
        "Counterexample: resume input has no hx-target of #skill-chips-result."
    )
    assert 'hx-encoding="multipart/form-data"' in html, (
        "Counterexample: resume input does not send multipart/form-data."
    )
    assert 'hx-swap="outerHTML"' in html, (
        "Counterexample: resume input has no hx-swap of outerHTML."
    )


# ── Test case C: the extract endpoint must process the uploaded file ────────────

# Small set of readable TXT payloads known to yield taxonomy skills via
# fallback_extract (python + git are both in app/data/skills_taxonomy.json).
READABLE_RESUMES = [
    b"I know some python and git",
    b"Experienced with Python, Git, and Docker in production projects.",
    b"python python python git git react",
]


@pytest.mark.parametrize("resume_bytes", READABLE_RESUMES)
def test_student_skills_extract_processes_uploaded_file(client, resume_bytes):
    """Bug Condition: `uploadedFileProcessedByExtractEndpoint` is false on unfixed code.

    A readable multipart resume POSTed to /student/skills/extract must come back
    as a populated skill_chips fragment (chips + non-empty skill_scores_json).
    On unfixed code the handler reads `text`, not the file, so the fragment is
    empty.

    Requirements 1.3, 2.3
    """
    c, _ = client
    r = c.post(
        "/student/skills/extract",
        files={"resume_file": ("resume.txt", resume_bytes, "text/plain")},
    )
    assert r.status_code == 200
    html = r.text

    # The shared partial is rendered (its root is the preview target).
    assert 'id="skill-chips-result"' in html, (
        "Counterexample: endpoint did not render the partials/skill_chips.html fragment."
    )
    # Rendered skill chips are present.
    assert 'class="chip"' in html, (
        "Counterexample: no skill chips rendered — the uploaded resume was ignored."
    )
    # The hidden skill_scores_json is populated, not the empty-state '{}'.
    assert 'name="skill_scores_json"' in html, (
        "Counterexample: the hidden skill_scores_json field is missing."
    )
    assert 'value="{}"' not in html, (
        "Counterexample: skill_scores_json is '{}' — the uploaded resume yielded "
        "no skills because the handler read `text`, not the file."
    )


# ════════════════════════════════════════════════════════════════════════════
# Task 2 — Preservation property tests (Property 2)
#
# Property 2: Preservation — Non-preview behavior is unchanged.
#
# Observation-first methodology: every assertion below records behavior that was
# OBSERVED by running the UNFIXED code for inputs where `isBugCondition` is
# false (the mentor extract flow, student final submission, submission-time
# `skill_scores_json` handling, and direct `_resume_text_from_upload` calls).
# The expected outcome on unfixed code is PASS — this pins the baseline that the
# fix must preserve.
#
# These are property-style tests: each one quantifies over a generated set of
# inputs (varied readable TXT/PDF/DOCX payloads, and varied empty/unreadable
# payloads) and asserts a universal property holds across all of them, using
# the project's established pytest + TestClient convention.
#
# Validates: Requirements 3.1, 3.2, 3.3, 3.4
# ════════════════════════════════════════════════════════════════════════════

import json
from io import BytesIO

from fastapi import HTTPException

from app.db.models import StudentRequest
from app.routers.pages import _resume_text_from_upload


# ── Resume fixture builders (readable TXT / PDF / DOCX) ──────────────────────


def _make_txt(text: str) -> bytes:
    return text.encode("utf-8")


def _make_pdf(text: str) -> bytes:
    """Hand-build a minimal single-page PDF whose text pypdf can extract.

    Avoids a PDF-writer dependency (none is installed) while exercising the real
    pypdf extraction path inside `_resume_text_from_upload`.
    """
    content = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(pdf))
        pdf += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += ("%010d 00000 n \n" % off).encode()
    pdf += b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n"
    pdf += str(xref_pos).encode() + b"\n%%EOF"
    return pdf


def _make_docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()


class _UploadStub:
    """Minimal stand-in matching what `_resume_text_from_upload` reads.

    The helper only touches `.filename` and `.file.read()`, so this avoids the
    async plumbing of a real `UploadFile` while exercising the real code path.
    """

    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self.file = BytesIO(data)


# Varied readable resume texts, each known to yield taxonomy skills (python/git
# are in app/data/skills_taxonomy.json) via the deterministic fallback_extract.
READABLE_TEXTS = [
    "I know some python and git",
    "Experienced with Python, Git, and Docker in production projects.",
    "python python python git git react",
    "Backend engineer: python, sql, docker, kubernetes.",
]


# ── Requirement 3.1 — mentor extract flow is unchanged ──────────────────────


def test_preserve_mentor_extract_renders_chips_into_target(client):
    """3.1 Observed: POST /mentor/skills/extract with known-skill text renders
    the skill_chips fragment (root #skill-chips-result) with chips.

    Property: holds for every readable known-skill text.
    """
    c, _ = client
    for text in READABLE_TEXTS:
        r = c.post("/mentor/skills/extract", data={"text": text})
        assert r.status_code == 200
        html = r.text
        assert 'id="skill-chips-result"' in html
        assert 'class="chip"' in html
        assert 'name="skill_scores_json"' in html
        # Known skills produce a populated (non-empty) hidden field.
        assert 'value="{}"' not in html


def test_preserve_mentor_extract_empty_text_renders_empty_fragment(client):
    """3.1 Observed: empty/blank text yields the empty-state fragment (no chips),
    still rendering the #skill-chips-result target with an empty hidden field.
    """
    c, _ = client
    for text in ["", "   ", "\n\t "]:
        r = c.post("/mentor/skills/extract", data={"text": text})
        assert r.status_code == 200
        html = r.text
        assert 'id="skill-chips-result"' in html
        assert 'class="chip"' not in html
        assert 'value="{}"' in html


# ── Requirement 3.2 — student final submission is unchanged ──────────────────


def test_preserve_student_signup_persists_and_redirects(client):
    """3.2 Observed: POST /student/signup with a readable resume file returns a
    303 to /student/matches and persists skill_scores, resume_text,
    experience_score, and experience_level on the StudentRequest.

    Property: holds across varied readable TXT resume payloads.
    """
    c, SessionMaker = client
    from app.services.skills import experience_level, experience_score
    from app.services.llm import extract_skills

    for idx, text in enumerate(READABLE_TEXTS):
        resume_bytes = _make_txt(text)
        r = c.post(
            "/student/signup",
            data={
                "name": f"Preserve Student {idx}",
                "goal_text": "Build an ML project",
                "specialty": "artificial_intelligence",
                "cadence": "weekly",
                "availability": "Mon-Evening,Tue-Evening",
                "top3": "hands_on_building,technical_depth,accountability",
            },
            files={"resume_file": ("resume.txt", resume_bytes, "text/plain")},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/student/matches" in r.headers["location"]

        db = SessionMaker()
        try:
            req = (
                db.query(StudentRequest)
                .order_by(StudentRequest.id.desc())
                .first()
            )
            assert req is not None
            assert req.resume_text == text
            # skill_scores is persisted from extract_skills on the resume text.
            expected_scores = extract_skills(text, db)
            assert req.skill_scores == expected_scores
            exp_s = experience_score(expected_scores)
            assert req.experience_score == exp_s
            assert req.experience_level == experience_level(exp_s)
            # Known-skill resume yields a non-empty skill map.
            assert req.skill_scores != {}
        finally:
            db.close()


# ── Requirement 3.3 — skill_scores_json precedence is unchanged ──────────────


def test_preserve_partial_still_emits_skill_scores_json_field(client):
    """3.3 Observed: the partials/skill_chips.html fragment still emits a hidden
    input named skill_scores_json in both the populated and empty states.
    """
    c, _ = client
    # Populated state (known-skill text).
    r = c.post("/mentor/skills/extract", data={"text": "I know some python and git"})
    assert 'name="skill_scores_json"' in r.text
    # Empty state.
    r = c.post("/mentor/skills/extract", data={"text": ""})
    assert 'name="skill_scores_json"' in r.text


def test_student_submission_honors_posted_skill_scores_json(client):
    """Student submit now HONORS a posted non-empty skill_scores_json.

    Changed intentionally by the skill-chips-edit-remove bugfix (Requirement
    2.8): this test previously pinned the old buggy behavior where the student
    handler discarded posted edits and re-extracted from the resume.
    """
    c, SessionMaker = client

    resume_text = "I know some python and git"
    edited_scores = {"python": 0.5}
    r = c.post(
        "/student/signup",
        data={
            "name": "Precedence Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
            "skill_scores_json": json.dumps(edited_scores),
        },
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        # Persisted scores come from the posted edited field, NOT re-extraction.
        assert req.skill_scores == edited_scores
    finally:
        db.close()


# ── Requirement 3.4 — _resume_text_from_upload is unchanged ──────────────────


def test_preserve_resume_reader_returns_text_for_readable_inputs(client):
    """3.4 Observed: _resume_text_from_upload returns the text for readable
    TXT/PDF/DOCX inputs.

    Property: for every readable text and every supported format, the helper
    returns text containing the source skills.
    """
    for text in READABLE_TEXTS:
        txt_upload = _UploadStub("resume.txt", _make_txt(text))
        assert _resume_text_from_upload(txt_upload) == text

        pdf_upload = _UploadStub("resume.pdf", _make_pdf(text))
        pdf_text = _resume_text_from_upload(pdf_upload)
        assert "python" in pdf_text.lower()

        docx_upload = _UploadStub("resume.docx", _make_docx(text))
        assert _resume_text_from_upload(docx_upload) == text


def test_preserve_resume_reader_raises_422_for_empty_unreadable_unsupported(client):
    """3.4 Observed: _resume_text_from_upload raises HTTPException(422) for
    empty, unreadable, and unsupported inputs.

    Property: across empty payloads, whitespace-only TXT, corrupt PDF/DOCX
    bytes, and unsupported extensions, the helper always raises 422.
    """
    raising_cases = [
        # Empty content (any extension) → "empty" branch.
        _UploadStub("resume.txt", b""),
        _UploadStub("resume.pdf", b""),
        _UploadStub("resume.docx", b""),
        # Readable bytes but no text after decode → "no readable text" branch.
        _UploadStub("resume.txt", b"   \n\t  "),
        # Corrupt/unreadable PDF and DOCX bytes → generic read-failure branch.
        _UploadStub("resume.pdf", b"not a real pdf"),
        _UploadStub("resume.docx", b"not a real docx"),
        # Unsupported extension → "unsupported format" branch.
        _UploadStub("resume.rtf", b"some resume content"),
        _UploadStub("resume", b"no extension content"),
    ]
    for upload in raising_cases:
        try:
            _resume_text_from_upload(upload)
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError(
                f"Expected HTTPException(422) for {upload.filename!r} with "
                f"{upload.file.getvalue()!r}, but none was raised."
            )
