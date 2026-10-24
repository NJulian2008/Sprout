from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_CADENCES = ["weekly", "every_other_week"]
VALID_OUTCOMES = ["learn_skill", "build_project", "career_navigation", "research"]


class StudentRequestCreate(BaseModel):
    goal_text: str
    goal_type: Literal["learn_skill", "build_project", "career_navigation", "research"]
    skills_to_learn: list[str]  # 1–5 taxonomy ids
    cadence: Literal["weekly", "every_other_week"] = "weekly"
    availability: list[str] = Field(default_factory=list)
    top3: list[str] = Field(default_factory=list)
    resume_text: str = ""
    skill_scores: dict[str, float] = Field(default_factory=dict)
    project_title: str = ""
    project_description: str = ""
    project_link: str = ""

    @field_validator("skills_to_learn")
    @classmethod
    def must_have_1_to_5_skills(cls, v: list[str]) -> list[str]:
        if not (1 <= len(v) <= 5):
            raise ValueError("skills_to_learn must have 1 to 5 items")
        return v


class StudentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    goal_text: str
    goal_type: str
    skills_to_learn: list[str]
    cadence: str
    availability: list[str]
    skill_scores: dict[str, float]
    experience_score: float
    experience_level: str
    created_at: datetime
