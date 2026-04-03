"""First Action Precision — produce one copy-paste-ready instruction for the top recommendation.

One call per run. ~500 tokens. Returns a specific, actionable string or empty string on failure.
"""

from __future__ import annotations
from typing import Any

_SYSTEM_PROMPT = (
    "You are a senior software engineer giving a colleague their first task. "
    "You have a modernization plan and file summaries. "
    "Write ONE specific, copy-paste-ready instruction for the single most important first action. "
    "Include: exact file path, line number if known, exact change needed. "
    "No markdown. No bullet points. Two sentences maximum. "
    "Return JSON with a single key: first_action (string)."
)

_MAX_SUMMARY_CHARS = 200


def generate_first_action(
    top_step: dict,
    step_description: str,
    affected_file_summaries: dict[str, str],
    llm_client: Any,
) -> str:
    """Generate precise first action string. Returns empty string on any failure."""
    try:
        summaries_text = "\n".join(
            f"{path}: {summary[:_MAX_SUMMARY_CHARS]}"
            for path, summary in list(affected_file_summaries.items())[:3]
        )
        user_content = (
            f"Top recommended action: {top_step.get('action', '')} — "
            f"from `{top_step.get('from', '')}` to `{top_step.get('to', '')}`\n\n"
            f"Step description: {step_description}\n\n"
            f"Affected file summaries:\n{summaries_text}\n\n"
            "What is the single most precise first action a developer should take right now?"
        )
        response = llm_client.generate_json(_SYSTEM_PROMPT, user_content)
        return str(response.get("first_action") or "").strip()
    except Exception:
        return ""
