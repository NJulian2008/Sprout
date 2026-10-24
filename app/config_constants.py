"""
Matching weights and thresholds.

All tunable constants live here so they can be adjusted in one place
without touching service logic (spec D12).
"""

# ── Overall score weights (must sum to 1.0) ──────────────────────────────────
WEIGHT_SKILLS_FIT: float = 0.45
WEIGHT_OUTCOME_FIT: float = 0.30
WEIGHT_AVAIL_FIT: float = 0.25

# ── skills_fit sub-weights (must sum to 1.0) ─────────────────────────────────
SKILLS_FIT_COVERAGE_WEIGHT: float = 0.7
SKILLS_FIT_LEVEL_WEIGHT: float = 0.3

# ── cover() formula ──────────────────────────────────────────────────────────
# Minimum gap between mentor and student confidence to get full credit.
COVER_HEADROOM: float = 0.30

# ── level_fit() piecewise thresholds ─────────────────────────────────────────
# Full credit is given when the experience-score gap is in [MIN_GAP, MAX_GAP].
LEVEL_FIT_MIN_GAP: float = 0.15
LEVEL_FIT_MAX_GAP: float = 0.45
# Score falls to 0 below LOWER_BOUND (mentor behind student) or at UPPER_BOUND.
LEVEL_FIT_LOWER_BOUND: float = -0.15
LEVEL_FIT_UPPER_BOUND: float = 0.85

# ── availability_fit() ───────────────────────────────────────────────────────
# Number of overlapping blocks that earns a perfect availability score.
AVAIL_BLOCKS_FOR_FULL_SCORE: int = 3

# ── experience_level() thresholds ────────────────────────────────────────────
LEVEL_BEGINNER_THRESHOLD: float = 0.35
LEVEL_ADVANCED_THRESHOLD: float = 0.65

# ── experience_score() ───────────────────────────────────────────────────────
EXPERIENCE_SCORE_TOP_K: int = 5
