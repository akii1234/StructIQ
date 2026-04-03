"""Health Score Rationale — produce two sentences explaining why the score is what it is.

One call per run. ~200 tokens. Returns string or empty string on failure.
"""

from __future__ import annotations
from typing import Any

_SYSTEM_PROMPT = (
    "You are a software architecture advisor. "
    "Given a codebase health score and its breakdown, write exactly two plain-English sentences "
    "explaining why the score is what it is. "
    "Be specific — mention the actual penalty contributors. No jargon. No markdown. "
    "Return JSON with a single key: rationale (string)."
)


def generate_score_rationale(
    score: int,
    grade: str,
    components: dict,
    cycle_count: int,
    god_file_count: int,
    llm_client: Any,
) -> str:
    """Generate a 2-sentence rationale for the health score. Returns empty string on any failure."""
    try:
        user_content = (
            f"Health Score: {score}/100 (Grade: {grade})\n"
            f"Penalty breakdown: {components}\n"
            f"Total cycles: {cycle_count}\n"
            f"God files: {god_file_count}\n\n"
            "Explain in two sentences why this score is what it is."
        )
        response = llm_client.generate_json(_SYSTEM_PROMPT, user_content)
        return str(response.get("rationale") or "").strip()
    except Exception:
        return ""
