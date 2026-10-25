"""
SQLAlchemy 2.0 ORM models for the Sprout mentor-matching platform.

All 10 tables are declared using the Mapped[T] / mapped_column() style
against a single DeclarativeBase.  JSON dict columns use
MutableDict.as_mutable(JSON) and JSON list columns use
MutableList.as_mutable(JSON) so that in-place mutations are tracked
automatically by SQLAlchemy's unit-of-work.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    headshot_url: Mapped[str] = mapped_column(String, default="")
    bio_short: Mapped[str] = mapped_column(String, default="")
    major: Mapped[str | None] = mapped_column(String, nullable=True)
    year: Mapped[str | None] = mapped_column(String, nullable=True)
    mentor_type: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    org: Mapped[str | None] = mapped_column(String, nullable=True)
    is_sample: Mapped[bool] = mapped_column(default=True)


# ---------------------------------------------------------------------------
# MentorProfile
# ---------------------------------------------------------------------------


class MentorProfile(Base):
    __tablename__ = "mentorprofile"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    resume_text: Mapped[str] = mapped_column(String, default="")
    skill_scores: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    skill_levels: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    experience_score: Mapped[float] = mapped_column(default=0.0)
    experience_level: Mapped[str] = mapped_column(String, default="intermediate")
    additional_experiences: Mapped[str] = mapped_column(String, default="")
    specialties: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    outcomes: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    availability: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    top3: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    max_students: Mapped[int] = mapped_column(default=2)


# ---------------------------------------------------------------------------
# StudentRequest
# ---------------------------------------------------------------------------


class StudentRequest(Base):
    __tablename__ = "studentrequest"

    id: Mapped[int | None] = mapped_column(primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    goal_text: Mapped[str] = mapped_column(String, nullable=False)
    goal_type: Mapped[str] = mapped_column(String, nullable=False)
    specialty: Mapped[str] = mapped_column(String, default="computer_science")
    skills_to_learn: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    cadence: Mapped[str] = mapped_column(String, default="weekly")
    availability: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    top3: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    resume_text: Mapped[str] = mapped_column(String, default="")
    skill_scores: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    skill_levels: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    experience_score: Mapped[float] = mapped_column(default=0.0)
    experience_level: Mapped[str] = mapped_column(String, default="beginner")
    project_title: Mapped[str] = mapped_column(String, default="")
    project_description: Mapped[str] = mapped_column(String, default="")
    project_link: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------


class Match(Base):
    __tablename__ = "match"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("studentrequest.id"), nullable=False)
    mentor_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    rank: Mapped[int] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    explanation: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="fallback")


# ---------------------------------------------------------------------------
# Mentorship
# ---------------------------------------------------------------------------


class Mentorship(Base):
    __tablename__ = "mentorship"

    id: Mapped[int] = mapped_column(primary_key=True)
    mentor_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    request_id: Mapped[int] = mapped_column(ForeignKey("studentrequest.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="requested")
    note_from_student: Mapped[str] = mapped_column(String, default="")
    cadence: Mapped[str] = mapped_column(String, default="weekly")
    duration_weeks: Mapped[int | None] = mapped_column(nullable=True)
    mentor_decision: Mapped[str] = mapped_column(String, default="pending")
    student_decision: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------


class Meeting(Base):
    __tablename__ = "meeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    mentorship_id: Mapped[int] = mapped_column(ForeignKey("mentorship.id"), nullable=False)
    number: Mapped[int] = mapped_column(nullable=False)
    agreed_time_text: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="scheduled")
    progress_notes: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    summary: Mapped[str] = mapped_column(String, default="")
    next_deliverable_ids: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)


# ---------------------------------------------------------------------------
# Deliverable
# ---------------------------------------------------------------------------


class Deliverable(Base):
    __tablename__ = "deliverable"

    id: Mapped[int] = mapped_column(primary_key=True)
    mentorship_id: Mapped[int] = mapped_column(ForeignKey("mentorship.id"), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    mentor_annotation: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="proposed")
    due_meeting: Mapped[int | None] = mapped_column(nullable=True)


# ---------------------------------------------------------------------------
# Testimonial
# ---------------------------------------------------------------------------


class Testimonial(Base):
    __tablename__ = "testimonial"

    id: Mapped[int] = mapped_column(primary_key=True)
    mentorship_id: Mapped[int] = mapped_column(ForeignKey("mentorship.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    mentor_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True)
    mentorship_id: Mapped[int] = mapped_column(ForeignKey("mentorship.id"), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ---------------------------------------------------------------------------
# LLMCache
# ---------------------------------------------------------------------------


class LLMCache(Base):
    __tablename__ = "llmcache"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    response: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# Explicit index for LLMCache.key lookups (unique constraint already creates
# one on most backends, but this is explicit and portable).
Index("ix_llmcache_key", LLMCache.key, unique=True)
