from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    role: Literal["student", "mentor"]
    name: str
    headshot_url: str = ""
    bio_short: str = ""
    major: str | None = None
    year: str | None = None
    mentor_type: Literal["industry", "faculty"] | None = None
    title: str | None = None
    org: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    name: str
    headshot_url: str
    bio_short: str
    major: str | None
    year: str | None
    mentor_type: str | None
    title: str | None
    org: str | None
    is_sample: bool
