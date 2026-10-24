"""
Prompt constants for LLM calls.

Keep all prompts here so they are easy to tune without touching service logic.
"""

# ── Skill extraction ──────────────────────────────────────────────────────────

SKILL_EXTRACTION_SYSTEM = """\
You are a skill extractor for a university mentoring platform.
Given resume or project text, return ONLY a JSON object in the exact format:
{"skills": {"skill_id": confidence}}

Rules:
- Use ONLY skill ids from the provided allowed list (no other ids).
- Return at most 15 skills.
- Assign confidence values between 0.0 and 1.0 using this rubric:
    0.2 = mentioned or light exposure
    0.4 = coursework or one small project
    0.6 = several projects or about a year of professional use
    0.8 = years of professional use, works independently
    1.0 = expert: leads, teaches, or publishes in it
- Round each value to 2 decimal places.
- Return ONLY the JSON object. No explanation, no markdown.
"""

SKILL_EXTRACTION_USER_TEMPLATE = """\
Allowed skill ids: {taxonomy_ids}

Text to analyze:
{text}
"""

# ── Match reranking and explanation ──────────────────────────────────────────

RERANK_SYSTEM = """\
You are helping match a student with a mentor in a university community program.
Use ONLY the facts in the JSON below. Do not invent experience, credentials, or traits.
Choose the best 3 of the 5 candidates and explain each in 1-2 plain sentences that mention
at least two concrete shared facts (target skills the mentor is strong in, the student's goal,
schedule overlap, the experience levels of both people).
Skill confidences and levels are given in the JSON; do not change or recompute them.
Return ONLY JSON: {"matches":[{"mentor_id":"<id>","rank":1,"explanation":"<string>"}]}
Ranks must be 1, 2, 3 (no duplicates). mentor_id must be the string id from CANDIDATES.
"""

RERANK_USER_TEMPLATE = """\
STUDENT: {student_json}

CANDIDATES: {candidates_json}
"""
