from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config_constants import CS_ENGINEERING_SPECIALTIES

VALID_CADENCES = ["weekly", "every_other_week"]
VALID_OUTCOMES = ["learn_skill", "build_project", "career_navigation", "research"]


class StudentRequestCreate(BaseModel):
    goal_text: str
    specialty: str
    cadence: Literal["weekly", "every_other_week"] = "weekly"
    availability: list[str] = Field(default_factory=list)
    top3: list[str] = Field(default_factory=list)
    resume_text: str
    project_title: str = ""
    project_description: str = ""
    project_link: str = ""

    @field_validator("resume_text")
    @classmethod
    def resume_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resume_text must not be blank")
        return value

    @field_validator("goal_text")
    @classmethod
    def goal_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal_text must not be blank")
        return value

    @field_validator("specialty")
    @classmethod
    def specialty_must_be_supported(cls, value: str) -> str:
        if value not in CS_ENGINEERING_SPECIALTIES:
            raise ValueError("specialty must be a supported CS or engineering field")
        return value


class StudentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    goal_text: str
    goal_type: str
    specialty: str
    skills_to_learn: list[str]
    cadence: str
    availability: list[str]
    skill_scores: dict[str, float]
    experience_score: float
    experience_level: str
    created_at: datetime
