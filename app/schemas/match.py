from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    mentor_id: int
    rank: int
    score: float
    score_breakdown: dict
    explanation: str
    source: str


class MatchExplanation(BaseModel):
    mentor_id: str  # stored as str in LLM output
    rank: int
    explanation: str


class MatchExplanations(BaseModel):
    matches: list[MatchExplanation]

    @field_validator("matches")
    @classmethod
    def must_have_3(cls, v: list[MatchExplanation]) -> list[MatchExplanation]:
        if len(v) != 3:
            raise ValueError("Must have exactly 3 match explanations")
        return v
