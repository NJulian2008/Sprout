from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VALID_OUTCOMES = ["learn_skill", "build_project", "career_navigation", "research"]
VALID_AVAIL_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
VALID_AVAIL_PARTS = ["Morning", "Afternoon", "Evening", "Night"]
VALID_PRIORITIES = [
    "clear_feedback",
    "hands_on_building",
    "flexible_schedule",
    "career_guidance",
    "accountability",
    "casual_friendly",
    "technical_depth",
    "big_picture",
]


class MentorProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    skill_scores: dict[str, float]
    experience_score: float
    experience_level: str
    outcomes: list[str]
    availability: list[str]
    top3: list[str]
    max_students: int
    additional_experiences: str
    resume_text: str


class MentorSignupRequest(BaseModel):
    """Full mentor signup form data."""

    name: str
    bio_short: str = ""
    title: str = ""
    org: str = ""
    mentor_type: Literal["industry", "faculty"]
    resume_text: str = ""
    skill_scores: dict[str, float] = Field(default_factory=dict)
    additional_experiences: str = ""
    outcomes: list[str] = Field(default_factory=list)
    availability: list[str] = Field(default_factory=list)
    top3: list[str] = Field(default_factory=list)
    max_students: int = 2


class MentorCardOut(BaseModel):
    """Compact view for match cards and dashboard listings."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    name: str
    mentor_type: str | None
    title: str | None
    org: str | None
    headshot_url: str
    bio_short: str
    skill_scores: dict[str, float]
    experience_score: float
    experience_level: str
    outcomes: list[str]
    availability: list[str]
    top3: list[str]
