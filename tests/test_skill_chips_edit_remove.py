"""Bug condition exploration tests for the skill-chips-edit-remove bugfix.

Property 1: Bug Condition — Editable, addable, synced, and persisted skill chips.

These tests encode the EXPECTED (post-fix) behavior described by the design's
`isBugCondition`: extracted skills are shown AND the user wants to change a
value OR remove a skill, OR the user wants to add a skill the AI missed
(including from the empty "No skills detected yet" state) — but no edit/remove/
add control exists, the hidden `skill_scores_json` is never synced, and the
student submit handler re-extracts and discards the posted JSON.

On UNFIXED code these tests are EXPECTED TO FAIL — the failures are the
counterexamples that confirm the bug exists. DO NOT fix the code or the tests
when they fail here.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 2.1, 2.2, 2.3,
2.6, 2.8, 2.10

Fixture pattern mirrors tests/test_flow_api.py and
tests/test_student_skills_preview.py: an in-memory SQLite engine with a
`get_session` dependency override and `settings.llm_mode = "off"` for
deterministic (fallback) skill extraction.
"""

import json
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, MentorProfile, StudentRequest
from app.db.session import get_session
from app.main import app
from app.services.llm import extract_skills
from app.services.skills import experience_level, experience_score, load_taxonomy


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


def _make_txt(text: str) -> bytes:
    return text.encode("utf-8")


def test_student_resume_review_stage_persists_edited_skills(client):
    c, SessionMaker = client
    resume_text = "I know Python and Git"
    review = c.post(
        "/student/signup",
        data={
            "stage": "review",
            "name": "Review Student",
            "goal_text": "Build a Python project",
            "specialty": "computer_science",
        },
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
    )
    assert review.status_code == 200
    assert "Review your skills" in review.text
    assert 'name="skill_reviewed" value="1"' in review.text

    create = c.post(
        "/student/signup",
        data={
            "stage": "create",
            "name": "Review Student",
            "goal_text": "Build a Python project",
            "specialty": "computer_science",
            "resume_text": resume_text,
            "skill_scores_json": '{"python": 0.5}',
            "skill_reviewed": "1",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == {"python": 0.5}
        assert req.resume_text == resume_text
    finally:
        db.close()


def test_mentor_resume_review_stage_persists_edited_skills(client):
    c, SessionMaker = client
    resume_text = "I know Python and Git"
    review = c.post(
        "/mentor/signup",
        data={
            "stage": "review",
            "name": "Review Mentor",
            "specialties": "computer_science",
        },
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
    )
    assert review.status_code == 200
    assert "Review your skills" in review.text
    assert 'name="skill_reviewed" value="1"' in review.text

    create = c.post(
        "/mentor/signup",
        data={
            "stage": "create",
            "name": "Review Mentor",
            "specialties": "computer_science",
            "resume_text": resume_text,
            "skill_scores_json": '{"python": 0.5}',
            "skill_reviewed": "1",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    db = SessionMaker()
    try:
        profile = db.query(MentorProfile).order_by(MentorProfile.user_id.desc()).first()
        assert profile is not None
        assert profile.skill_scores == {"python": 0.5}
        assert profile.resume_text == resume_text
    finally:
        db.close()


def test_student_skill_review_follows_resume_and_has_step_navigation(client):
    c, _ = client
    review = c.post(
        "/student/signup",
        data={
            "stage": "review",
            "name": "Wizard Student",
            "goal_text": "Build a Python project",
            "specialty": "computer_science",
        },
        files={"resume_file": ("resume.txt", _make_txt("Python and Git"), "text/plain")},
    )
    assert review.status_code == 200
    html = review.text
    assert '<h1 data-wizard-heading>Review your skills</h1>' in html
    assert 'data-step-title="When are you free?"' in html
    assert 'data-step-title="What matters most to you?"' in html
    assert html.index("Review your skills") < html.index("When are you free?")
    assert html.index("When are you free?") < html.index("What matters most to you?")
    assert html.count('data-wizard-back') == 2
    assert "data-history-back" not in html
    assert "data-confidence-output" not in html
    assert "%" not in html


def test_mentor_skill_review_follows_resume_and_keeps_later_steps(client):
    c, _ = client
    review = c.post(
        "/mentor/signup",
        data={
            "stage": "review",
            "name": "Wizard Mentor",
            "specialties": "computer_science",
        },
        files={"resume_file": ("resume.txt", _make_txt("Python and Git"), "text/plain")},
    )
    assert review.status_code == 200
    html = review.text
    assert html.index("Review your skills") < html.index("What can you help students do?")
    assert html.index("What can you help students do?") < html.index("When are you free?")
    assert html.index("When are you free?") < html.index("What defines your mentoring?")
    assert html.count('data-wizard-back') == 3
    assert "data-confidence-output" not in html
    assert "%" not in html


# ════════════════════════════════════════════════════════════════════════════
# Test case 1 — student discard (value edit + removal ignored server-side)
#
# isBugCondition: hasExtractedSkills AND userWantsToEditValue/RemoveSkill, and
# submittedEditsIgnored on the student path.
# Requirements 1.4, 1.7, 2.8
# ════════════════════════════════════════════════════════════════════════════


def test_student_signup_persists_edited_skill_scores_json(client):
    """Expected (post-fix): a posted edited `skill_scores_json` is persisted.

    The resume "I know some python and git" extracts {python, git}. The user
    lowers python to 0.5 and removes git, posting {"python": 0.5}. The persisted
    StudentRequest.skill_scores MUST equal the posted edited set.

    On UNFIXED code this FAILS: the handler re-extracts from the resume and
    ignores the posted JSON, so git is still present and python keeps its
    extracted confidence (counterexample: persisted set is the re-extracted
    set, not {"python": 0.5}).
    """
    c, SessionMaker = client
    resume_text = "I know some python and git"
    edited = {"python": 0.5}

    r = c.post(
        "/student/signup",
        data={
            "name": "Edit Discard Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
            "skill_scores_json": json.dumps(edited),
        },
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == edited, (
            "Counterexample: posted edited skill_scores_json was discarded. "
            f"Expected {edited}, got {req.skill_scores} (re-extracted from resume)."
        )
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# Test case 2 — student added-skill discard
#
# isBugCondition: userWantsToAddSkill (a canonical skill the resume lacks).
# Requirements 1.3, 1.4, 1.7, 2.3, 2.8
# ════════════════════════════════════════════════════════════════════════════


def test_student_signup_persists_added_skill_from_json(client):
    """Expected (post-fix): a posted ADDED canonical skill is persisted.

    A Python-only resume extracts {python}. The user adds sql (which the resume
    does not mention), posting {"python": ..., "sql": 0.6}. The persisted set
    MUST contain sql.

    On UNFIXED code this FAILS: the handler re-extracts from the resume, so the
    added sql is dropped (counterexample: sql absent from the persisted set).
    """
    c, SessionMaker = client
    resume_text = "python python python"  # yields {python}; no sql mention
    posted = {"python": 0.6, "sql": 0.6}

    r = c.post(
        "/student/signup",
        data={
            "name": "Add Discard Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
            "skill_scores_json": json.dumps(posted),
        },
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert "sql" in req.skill_scores, (
            "Counterexample: posted added skill 'sql' was discarded. "
            f"Persisted set {req.skill_scores} does not contain 'sql' "
            "(handler re-extracted from the Python-only resume)."
        )
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# Test case 3 — remove control on populated chips; scores stay internal
#
# The UI displays each confidence as an editable slider and keeps the hidden
# score map synchronized when a skill is edited or removed.
# Requirements 1.2, 2.2
# ════════════════════════════════════════════════════════════════════════════


def test_populated_chips_have_remove_control_and_editable_confidence(client):
    """Each skill has a remove control and an editable confidence slider.

    Render non-empty chips via POST /mentor/skills/extract with a known-skill
    text. The fragment must expose the UI controls and preserve the extracted
    confidence in the hidden score map.
    """
    c, _ = client
    r = c.post("/mentor/skills/extract", data={"text": "I know some python and git"})
    assert r.status_code == 200
    html = r.text

    # Sanity: chips are actually rendered so the assertions are meaningful.
    assert 'class="chip skill-chip"' in html, "Expected non-empty chips to be rendered."
    assert "data-remove-skill" in html, "Expected a per-skill remove control."
    assert "data-confidence-slider" in html, "Expected an editable confidence slider."
    assert '"python": 0.3' in html, "The confidence score must remain in the hidden form data."


# ════════════════════════════════════════════════════════════════════════════
# Test case 4 — no add control in the populated branch
#
# isBugCondition: NOT addControlExists.
# Requirements 1.3, 2.3
# ════════════════════════════════════════════════════════════════════════════


def test_populated_chips_have_taxonomy_add_control(client):
    """A plain text add control resolves skill names without a combo selector."""
    c, _ = client
    r = c.post("/mentor/skills/extract", data={"text": "I know some python and git"})
    assert r.status_code == 200
    html = r.text

    assert 'class="chip-add-input"' in html, "Expected a free-text add box."
    assert 'type="text"' in html and 'list="skill-suggestions"' not in html
    assert "skill-suggestions" not in html and "<datalist" not in html
    assert "chip-add" in html, "Expected an add button."


# ════════════════════════════════════════════════════════════════════════════
# Test case 5 — no add control in the empty state
#
# isBugCondition: userWantsToAddSkill from the empty "No skills detected yet"
# branch (Requirement 2.10 defect).
# Requirements 1.8, 2.10
# ════════════════════════════════════════════════════════════════════════════


def test_empty_state_shows_message_and_add_control(client):
    """The empty branch keeps "No skills detected yet" AND offers a free-text
    add control.

    Render the partial via an extraction that yields NO skills (empty text).
    The fragment MUST show "No skills detected yet" and a chip-add-input /
    chip-add control so a skill can be added even from the empty state.
    """
    c, _ = client
    r = c.post("/mentor/skills/extract", data={"text": ""})
    assert r.status_code == 200
    html = r.text

    assert "No skills detected yet" in html, (
        "Expected the empty-state message to remain."
    )
    assert 'class="chip-add-input"' in html, "Expected an add box in the empty state."
    assert "chip-add" in html, "Expected an add button in the empty state."


# ════════════════════════════════════════════════════════════════════════════
# Test case 6 — editing note consistent with the controls
#
# isBugCondition: the note advertises editing that no control supports.
# Requirements 1.5, 2.6
# ════════════════════════════════════════════════════════════════════════════


def test_populated_note_mentions_remove_and_add(client):
    """Expected (post-fix): the populated note matches the actual controls.

    The note should reference removing and adding a skill, rather than the stale
    "edit any value below" with no controls behind it.

    On UNFIXED code this FAILS: the note is "AI estimate — edit any value
    below." and mentions neither removing nor adding.
    """
    c, _ = client
    r = c.post("/mentor/skills/extract", data={"text": "I know some python and git"})
    assert r.status_code == 200
    html_lower = r.text.lower()

    assert "remove" in html_lower, (
        "Counterexample: the editing note/controls never mention removing a "
        "skill (note still reads 'edit any value below')."
    )
    assert "add" in html_lower, (
        "Counterexample: the editing note/controls never mention adding a "
        "skill (note still reads 'edit any value below')."
    )


# ════════════════════════════════════════════════════════════════════════════
# Task 2 — Preservation property tests (Property 2)
#
# Property 2: Preservation — Unedited, un-added, and unrelated behavior.
#
# Observation-first methodology: every assertion below records behavior that was
# OBSERVED by running the UNFIXED code for inputs where `isBugCondition` is
# false (the user triggers extraction but does NOT edit/remove/add a skill, no
# skills are detected and none are added, or a non-skill field is submitted).
# The expected outcome on UNFIXED code is PASS — these pin the baseline the fix
# must preserve. Posting the extracted set verbatim is a no-op "edit", so it is
# NOT a bug condition.
#
# Several assertions are property-style: they quantify over a generated set of
# inputs (varied readable known-skill texts, varied random skill maps) and
# assert a universal property holds across all of them, using the project's
# pytest + TestClient convention.
#
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
# ════════════════════════════════════════════════════════════════════════════

# Varied readable resume texts, each known to yield taxonomy skills (python/git
# are in app/data/skills_taxonomy.json) via the deterministic fallback_extract.
READABLE_TEXTS = [
    "I know some python and git",
    "Experienced with Python, Git, and Docker in production projects.",
    "python python python git git react",
    "Backend engineer: python, sql, docker, kubernetes.",
]

# A resume whose words map to NO taxonomy skill, so fallback_extract yields {}.
# (Verified empirically: the fallback substring-scan finds no taxonomy term,
# including the single-letter "c" id, in this text.)
NO_SKILL_RESUME = "My hobbies are reading writing and swimming"


# ── Requirement 3.2 — unedited student submission persists the extracted set ──


def test_preserve_student_unedited_posted_json_equals_extracted(client):
    """3.2 (student): posting skill_scores_json EQUAL to what the resume
    extracts persists StudentRequest.skill_scores identical to the extracted
    set.

    On UNFIXED code the student handler ignores the posted JSON and re-extracts,
    but because the posted set equals the extraction, the persisted set is the
    extracted set either way. This is a no-op edit (NOT a bug condition) and
    must still hold after the fix.

    Property: holds for every readable known-skill resume text.
    """
    c, SessionMaker = client
    for idx, text in enumerate(READABLE_TEXTS):
        db = SessionMaker()
        try:
            expected = extract_skills(text, db)
        finally:
            db.close()
        assert expected != {}, "Sanity: resume should extract at least one skill."

        r = c.post(
            "/student/signup",
            data={
                "name": f"Unedited Student {idx}",
                "goal_text": "Build an ML project",
                "specialty": "artificial_intelligence",
                "cadence": "weekly",
                "availability": "Mon-Evening,Tue-Evening",
                "top3": "hands_on_building,technical_depth,accountability",
                "skill_scores_json": json.dumps(expected),
            },
            files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/student/matches" in r.headers["location"]

        db = SessionMaker()
        try:
            req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
            assert req is not None
            assert req.skill_scores == expected
            exp_s = experience_score(expected)
            assert req.experience_score == exp_s
            assert req.experience_level == experience_level(exp_s)
        finally:
            db.close()


# ── Requirement 3.2 — unedited mentor submission persists verbatim ────────────


def test_preserve_mentor_unedited_posted_json_persists_verbatim(client):
    """3.2 (mentor): posting skill_scores_json equal to the extracted set
    persists MentorProfile.skill_scores verbatim.

    The mentor handler already honors a posted set via {k: float(v)}, so the
    persisted map equals the posted (extracted) set with float values.

    Property: holds for every readable known-skill resume text.
    """
    c, SessionMaker = client
    for idx, text in enumerate(READABLE_TEXTS):
        db = SessionMaker()
        try:
            extracted = extract_skills(text, db)
        finally:
            db.close()
        assert extracted != {}, "Sanity: resume should extract at least one skill."

        r = c.post(
            "/mentor/signup",
            data={
                "name": f"Unedited Mentor {idx}",
                "specialties": "artificial_intelligence",
                "outcomes": "Shipped an ML pipeline,Published a paper",
                "availability": "Mon-Evening,Tue-Evening",
                "top3": "hands_on_building,technical_depth,accountability",
                "skill_scores_json": json.dumps(extracted),
            },
            files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/mentor/dashboard" in r.headers["location"]

        db = SessionMaker()
        try:
            profile = (
                db.query(MentorProfile).order_by(MentorProfile.user_id.desc()).first()
            )
            assert profile is not None
            expected_float = {k: float(v) for k, v in extracted.items()}
            assert profile.skill_scores == expected_float
        finally:
            db.close()


# ── Requirement 3.3 — no skills detected and no add → "No skills detected yet"
#    + value="{}", and an empty-skills resume persists {} ──────────────────────


def test_preserve_extract_no_skills_shows_empty_state(client):
    """3.3: an extraction yielding no skills renders "No skills detected yet"
    and a hidden value="{}" on BOTH extract endpoints.
    """
    c, _ = client

    # Mentor extract with text that maps to no taxonomy skill.
    r = c.post("/mentor/skills/extract", data={"text": NO_SKILL_RESUME})
    assert r.status_code == 200
    assert "No skills detected yet" in r.text
    assert "value='{}'" in r.text
    assert 'class="chip"' not in r.text

    # Student extract with a no-skill resume file.
    r = c.post(
        "/student/skills/extract",
        files={"resume_file": ("resume.txt", _make_txt(NO_SKILL_RESUME), "text/plain")},
    )
    assert r.status_code == 200
    assert "No skills detected yet" in r.text
    assert "value='{}'" in r.text
    assert 'class="chip"' not in r.text


def test_preserve_student_empty_skill_resume_persists_empty_map(client):
    """3.3: a student submission whose resume yields no skills and who adds none
    persists an empty skill_scores map ({}).

    On UNFIXED code the handler re-extracts from the resume; a resume with no
    taxonomy terms extracts {} and persists {}.
    """
    c, SessionMaker = client
    r = c.post(
        "/student/signup",
        data={
            "name": "No Skills Student",
            "goal_text": "Explore a new area",
            "specialty": "artificial_intelligence",
        },
        files={"resume_file": ("resume.txt", _make_txt(NO_SKILL_RESUME), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == {}
        assert req.experience_score == 0.0
        assert req.experience_level == experience_level(0.0)  # "beginner"
    finally:
        db.close()


# ── Requirement 3.5 — only canonical taxonomy ids persisted ───────────────────


def test_preserve_student_persists_only_canonical_taxonomy_ids(client):
    """3.5 (student): posting a skill_scores_json whose keys are canonical
    taxonomy ids persists exactly those canonical id keys; no unknown/free-text
    key is persisted.

    To keep a baseline that is stable whether the handler honors the posted set
    (post-fix) or re-extracts (unfixed), the posted canonical set equals what
    the resume extracts, so the persisted keys are the same canonical ids either
    way. Every persisted key must be a canonical taxonomy id.
    """
    c, SessionMaker = client
    taxonomy = load_taxonomy()
    text = "Backend engineer: python, sql, docker, git."

    db = SessionMaker()
    try:
        extracted = extract_skills(text, db)
    finally:
        db.close()
    assert extracted != {}
    # Sanity: every extracted key is canonical (precondition of the baseline).
    assert all(k in taxonomy for k in extracted)

    r = c.post(
        "/student/signup",
        data={
            "name": "Canonical Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
            "skill_scores_json": json.dumps(extracted),
        },
        files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores != {}
        # Every persisted key is a canonical taxonomy id; no free-text key.
        for key in req.skill_scores:
            assert key in taxonomy, f"Non-canonical key persisted: {key!r}"
        assert set(req.skill_scores) == set(extracted)
    finally:
        db.close()


# ── Requirement 3.7 — absent / malformed skill_scores_json falls back ─────────


def test_preserve_student_absent_skill_scores_json_falls_back(client):
    """3.7: a student submission with skill_scores_json ABSENT falls back to
    re-extraction without crashing (303 redirect), persisting the extracted set.
    """
    c, SessionMaker = client
    text = "I know some python and git"
    db = SessionMaker()
    try:
        expected = extract_skills(text, db)
    finally:
        db.close()

    r = c.post(
        "/student/signup",
        data={
            "name": "Absent JSON Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
        },
        files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == expected
    finally:
        db.close()


def test_preserve_student_malformed_skill_scores_json_falls_back(client):
    """3.7: a student submission with skill_scores_json="not json" falls back to
    re-extraction without crashing (303 redirect), persisting the extracted set.
    """
    c, SessionMaker = client
    text = "I know some python and git"
    db = SessionMaker()
    try:
        expected = extract_skills(text, db)
    finally:
        db.close()

    r = c.post(
        "/student/signup",
        data={
            "name": "Malformed JSON Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
            "skill_scores_json": "not json",
        },
        files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == expected
    finally:
        db.close()


# ── Requirement 3.4 — experience_score / experience_level helpers unchanged ───
#
# Property-based: generate random skill sets {skill_id: confidence in [0,1]} and
# assert the helpers return the documented values (top-5 mean; thresholds 0.35
# beginner / 0.65 intermediate / else advanced). `hypothesis` is not installed
# in this project, so a seeded loop-based generator provides the universal
# coverage across the input domain.


def _expected_score(skills: dict[str, float], k: int = 5) -> float:
    if not skills:
        return 0.0
    top = sorted(skills.values(), reverse=True)[:k]
    return sum(top) / len(top)


def _expected_level(score: float) -> str:
    if score < 0.35:
        return "beginner"
    if score < 0.65:
        return "intermediate"
    return "advanced"


def test_preserve_experience_helpers_match_documented_rules():
    """3.4: experience_score is the mean of the top-5 confidences (0.0 for an
    empty dict) and experience_level maps <0.35 → beginner, <0.65 →
    intermediate, else advanced — across many random skill sets.

    Property: for all generated {skill_id: confidence in [0,1]} sets, the
    helpers equal the independently-computed documented values.
    """
    taxonomy_ids = list(load_taxonomy().keys())
    rng = random.Random(1234)

    # Empty set is the documented edge case.
    assert experience_score({}) == 0.0
    assert experience_level(experience_score({})) == "beginner"

    for _ in range(500):
        size = rng.randint(1, min(10, len(taxonomy_ids)))
        ids = rng.sample(taxonomy_ids, size)
        skills = {sid: round(rng.random(), 4) for sid in ids}

        score = experience_score(skills)
        expected = _expected_score(skills)
        assert score == pytest.approx(expected), (
            f"experience_score mismatch for {skills}: {score} != {expected}"
        )
        assert experience_level(score) == _expected_level(score)

    # Explicit threshold boundaries (documented values).
    assert experience_level(0.0) == "beginner"
    assert experience_level(0.34) == "beginner"
    assert experience_level(0.35) == "intermediate"
    assert experience_level(0.64) == "intermediate"
    assert experience_level(0.65) == "advanced"
    assert experience_level(1.0) == "advanced"


# ── Requirement 3.6 — all other (non-skill) fields persist as before ─────────


def test_preserve_student_other_fields_persist(client):
    """3.6 (student): goal, specialty, availability, top3, and derived goal_type
    persist exactly as before on a representative student submission.
    """
    c, SessionMaker = client
    text = "I know some python and git"

    r = c.post(
        "/student/signup",
        data={
            "name": "Other Fields Student",
            "goal_text": "Build an ML project with a research thesis",
            "specialty": "artificial_intelligence",
            "cadence": "biweekly",
            "availability": "Mon-Evening,Tue-Morning,Wed-Evening",
            "top3": "hands_on_building,technical_depth,accountability",
        },
        files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.goal_text == "Build an ML project with a research thesis"
        assert req.specialty == "artificial_intelligence"
        assert req.cadence == "biweekly"
        assert req.availability == ["Mon-Evening", "Tue-Morning", "Wed-Evening"]
        assert req.top3 == ["hands_on_building", "technical_depth", "accountability"]
        assert req.resume_text == text
        # goal_type is inferred from goal_text ("research"/"thesis" → research).
        assert req.goal_type == "research"
    finally:
        db.close()


def test_preserve_mentor_other_fields_persist(client):
    """3.6 (mentor): outcomes, specialties, availability, and top3 persist
    exactly as before on a representative mentor submission.
    """
    c, SessionMaker = client
    text = "I know some python and git"

    r = c.post(
        "/mentor/signup",
        data={
            "name": "Other Fields Mentor",
            "specialties": "artificial_intelligence,computer_science",
            "outcomes": "Shipped an ML pipeline,Mentored 5 students",
            "availability": "Mon-Evening,Tue-Evening",
            "top3": "hands_on_building,technical_depth,accountability",
        },
        files={"resume_file": ("resume.txt", _make_txt(text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        profile = db.query(MentorProfile).order_by(MentorProfile.user_id.desc()).first()
        assert profile is not None
        assert profile.specialties == ["artificial_intelligence", "computer_science"]
        assert profile.outcomes == ["Shipped an ML pipeline", "Mentored 5 students"]
        assert profile.availability == ["Mon-Evening", "Tue-Evening"]
        assert profile.top3 == ["hands_on_building", "technical_depth", "accountability"]
        assert profile.max_students == 1
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# Task 4 — Optional server-side integration tests
#
# These exercise the full extract → edit/add → submit → persist flow end to end
# through the HTTP layer, confirming the authoritative server-side guarantee:
# a posted (edited AND added) skill_scores_json is persisted, drives the derived
# experience values, and a manually added skill survives even when extraction
# found nothing. Client-side-only behaviors (merge-not-duplicate, empty →
# non-empty DOM transition, live badge recompute) have no JS test harness in
# this project and are covered by these persistence tests plus manual/DOM
# verification.
#
# Validates: Requirements 2.8 (+ matching), 2.10
# ════════════════════════════════════════════════════════════════════════════


def test_integration_student_extract_then_edit_and_add_persists_and_matches(client):
    """2.8 (+ matching): extract via /student/skills/extract, then submit
    /student/signup with an edited value AND an added canonical skill the resume
    lacked; the persisted set equals the posted set and drives experience.

    Resume "I know some python and git" extracts {python, git}. The user posts
    {"python": 0.5, "sql": 0.7} — python's confidence edited down and sql added
    (the resume mentions no sql). The persisted StudentRequest.skill_scores MUST
    equal that posted set, and experience_score / experience_level MUST match
    the skills-service helpers for that posted set. Finally /student/matches
    must load (200).
    """
    c, SessionMaker = client
    resume_text = "I know some python and git"

    # 1) Extract first (HTMX fragment round-trip the UI performs).
    extract = c.post(
        "/student/skills/extract",
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
    )
    assert extract.status_code == 200
    assert "data-skill-item" in extract.text  # chips were rendered to edit/add from

    # 2) Submit with an edited value (python down to 0.5) AND an added skill
    #    (sql, which the resume lacks).
    edited_and_added = {"python": 0.5, "sql": 0.7}
    r = c.post(
        "/student/signup",
        data={
            "name": "Edit And Add Student",
            "goal_text": "Build an ML project",
            "specialty": "artificial_intelligence",
            "cadence": "weekly",
            "availability": "Mon-Evening,Tue-Evening",
            "top3": "hands_on_building,technical_depth,accountability",
            "skill_scores_json": json.dumps(edited_and_added),
        },
        files={"resume_file": ("resume.txt", _make_txt(resume_text), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/student/matches" in r.headers["location"]

    # Posted values are coerced to float server-side; keys are preserved.
    expected = {k: float(v) for k, v in edited_and_added.items()}

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == expected, (
            f"Expected persisted set {expected}, got {req.skill_scores}."
        )
        # Experience values derive from the posted (edited + added) set.
        exp_s = experience_score(expected)
        assert req.experience_score == exp_s
        assert req.experience_level == experience_level(exp_s)
    finally:
        db.close()

    # 3) The matches page loads for the persisted student (follow the redirect).
    matches = c.get("/student/matches")
    assert matches.status_code == 200


def test_integration_student_add_from_empty_extraction_persists_added_skill(client):
    """2.10: a resume that yields NO skills plus a single ADDED canonical skill
    persists exactly that added skill.

    The resume (NO_SKILL_RESUME) extracts {} — the "No skills detected yet"
    state the user adds a skill from. Posting {"sql": 0.6} must persist exactly
    {"sql": 0.6}, proving the manually added skill is honored even though
    extraction found nothing.
    """
    c, SessionMaker = client
    added = {"sql": 0.6}

    r = c.post(
        "/student/signup",
        data={
            "name": "Add From Empty Student",
            "goal_text": "Explore a new area",
            "specialty": "artificial_intelligence",
            "skill_scores_json": json.dumps(added),
        },
        files={"resume_file": ("resume.txt", _make_txt(NO_SKILL_RESUME), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    expected = {k: float(v) for k, v in added.items()}

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == expected, (
            "Manually added skill should be persisted even when extraction found "
            f"nothing. Expected {expected}, got {req.skill_scores}."
        )
    finally:
        db.close()


def test_student_signup_preserves_intentionally_empty_skill_list(client):
    c, SessionMaker = client
    r = c.post(
        "/student/signup",
        data={
            "name": "Remove All Student",
            "goal_text": "Explore mentoring",
            "specialty": "artificial_intelligence",
            "skill_scores_json": "{}",
            "skill_scores_reviewed": "1",
        },
        files={"resume_file": ("resume.txt", _make_txt("Python and Docker"), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        req = db.query(StudentRequest).order_by(StudentRequest.id.desc()).first()
        assert req is not None
        assert req.skill_scores == {}
    finally:
        db.close()


def test_mentor_signup_preserves_intentionally_empty_skill_list(client):
    c, SessionMaker = client
    r = c.post(
        "/mentor/signup",
        data={
            "name": "Remove All Mentor",
            "specialties": "computer_science",
            "skill_scores_json": "{}",
            "skill_scores_reviewed": "1",
        },
        files={"resume_file": ("resume.txt", _make_txt("Python and Docker"), "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 303

    db = SessionMaker()
    try:
        profile = db.query(MentorProfile).order_by(MentorProfile.user_id.desc()).first()
        assert profile is not None
        assert profile.skill_scores == {}
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# GET /api/skills/normalize — free-text add resolution (fuzzy fallback)
#
# The free-text add box resolves typed text to a canonical taxonomy id. Exact
# id/label/alias matches are handled client-side; near-miss typos fall back to
# this endpoint, which calls normalize_skill_id (exact match then rapidfuzz
# fuzzy match ≥ 85). Unknown text resolves to {id: None} so the client rejects
# the add rather than persisting a non-canonical key (Requirement 3.5).
# ════════════════════════════════════════════════════════════════════════════


def test_api_normalize_exact_label(client):
    """An exact label (case-insensitive) resolves to its canonical id + label."""
    c, _ = client
    r = c.get("/api/skills/normalize", params={"q": "JavaScript"})
    assert r.status_code == 200
    assert r.json() == {"id": "javascript", "label": "JavaScript"}


def test_api_normalize_alias(client):
    """A known alias resolves to the canonical id."""
    c, _ = client
    r = c.get("/api/skills/normalize", params={"q": "py"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "python"
    assert body["label"] == "Python"


def test_api_normalize_fuzzy_typo(client):
    """A near-miss typo resolves via the fuzzy fallback (rapidfuzz ≥ 85).

    'pythn' is not an exact id/label/alias, so only the fuzzy branch can resolve
    it. rapidfuzz is a project dependency, so this should map to 'python'.
    """
    c, _ = client
    r = c.get("/api/skills/normalize", params={"q": "pythn"})
    assert r.status_code == 200
    assert r.json()["id"] == "python"


def test_api_normalize_unknown_returns_null(client):
    """Unrecognizable text resolves to {id: None} (the add is rejected)."""
    c, _ = client
    r = c.get("/api/skills/normalize", params={"q": "zzzznotaskill"})
    assert r.status_code == 200
    assert r.json() == {"id": None, "label": None}


def test_api_normalize_blank_returns_null(client):
    """Blank / whitespace input resolves to {id: None} without error."""
    c, _ = client
    for q in ["", "   "]:
        r = c.get("/api/skills/normalize", params={"q": q})
        assert r.status_code == 200
        assert r.json() == {"id": None, "label": None}
