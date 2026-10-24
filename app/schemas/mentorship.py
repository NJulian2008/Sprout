from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MentorshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mentor_id: int
    student_id: int
    request_id: int
    status: str
    note_from_student: str
    cadence: str
    duration_weeks: int | None
    mentor_decision: str
    student_decision: str
    started_at: datetime | None
    completed_at: datetime | None


class DeliverableCreate(BaseModel):
    mentorship_id: int
    text: str
    due_meeting: int | None = None


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mentorship_id: int
    text: str
    mentor_annotation: str
    status: str
    due_meeting: int | None


class DeliverableUpdate(BaseModel):
    text: str | None = None
    mentor_annotation: str | None = None
    status: Literal["proposed", "approved", "done"] | None = None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mentorship_id: int
    number: int
    agreed_time_text: str
    status: str
    progress_notes: list[dict]
    summary: str


class MeetingUpdate(BaseModel):
    agreed_time_text: str | None = None
    summary: str | None = None
    progress_notes: list[dict] | None = None
    status: Literal["scheduled", "held"] | None = None


class TestimonialCreate(BaseModel):
    text: str


class TestimonialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mentorship_id: int
    student_id: int
    mentor_id: int
    text: str
    created_at: datetime


class DecisionRequest(BaseModel):
    choice: Literal["confirm", "decline"]
