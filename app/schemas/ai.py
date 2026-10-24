from __future__ import annotations

from pydantic import BaseModel, model_validator


class SkillScores(BaseModel):
    """Validated AI output for skill extraction.

    Taxonomy keys only, values 0.0–1.0. Unknown keys are silently dropped;
    values are clamped to [0.0, 1.0] and rounded to 2 decimal places.
    """

    skills: dict[str, float]

    @model_validator(mode="after")
    def validate_skills(self) -> SkillScores:
        # Import inside validator to avoid circular imports at module load time.
        from app.services.skills import load_taxonomy

        taxonomy = load_taxonomy()
        cleaned: dict[str, float] = {}
        for k, v in self.skills.items():
            if k in taxonomy:
                cleaned[k] = round(min(1.0, max(0.0, v)), 2)
            # unknown keys are silently dropped
        self.skills = cleaned
        return self
