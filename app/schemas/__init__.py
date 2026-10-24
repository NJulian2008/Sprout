from __future__ import annotations

# ai
from app.schemas.ai import SkillScores

# match
from app.schemas.match import MatchExplanation, MatchExplanations, MatchOut

# mentor
from app.schemas.mentor import (
    VALID_AVAIL_DAYS,
    VALID_AVAIL_PARTS,
    VALID_PRIORITIES,
    MentorCardOut,
    MentorProfileOut,
    MentorSignupRequest,
)
from app.schemas.mentor import (
    VALID_OUTCOMES as MENTOR_VALID_OUTCOMES,
)

# mentorship
from app.schemas.mentorship import (
    DecisionRequest,
    DeliverableCreate,
    DeliverableOut,
    DeliverableUpdate,
    MeetingOut,
    MeetingUpdate,
    MentorshipOut,
    TestimonialCreate,
    TestimonialOut,
)

# student
from app.schemas.student import (
    VALID_CADENCES,
    StudentRequestCreate,
    StudentRequestOut,
)
from app.schemas.student import (
    VALID_OUTCOMES as STUDENT_VALID_OUTCOMES,
)

# user
from app.schemas.user import UserCreate, UserOut

__all__ = [
    # user
    "UserCreate",
    "UserOut",
    # mentor
    "MentorCardOut",
    "MentorProfileOut",
    "MentorSignupRequest",
    "VALID_AVAIL_DAYS",
    "VALID_AVAIL_PARTS",
    "MENTOR_VALID_OUTCOMES",
    "VALID_PRIORITIES",
    # student
    "StudentRequestCreate",
    "StudentRequestOut",
    "VALID_CADENCES",
    "STUDENT_VALID_OUTCOMES",
    # match
    "MatchExplanation",
    "MatchExplanations",
    "MatchOut",
    # mentorship
    "DecisionRequest",
    "DeliverableCreate",
    "DeliverableOut",
    "DeliverableUpdate",
    "MeetingOut",
    "MeetingUpdate",
    "MentorshipOut",
    "TestimonialCreate",
    "TestimonialOut",
    # ai
    "SkillScores",
]
