"""Anti-Pattern Confirmation — verify static findings against actual file content.

Verdicts:
  confirmed         — LLM confirms the anti-pattern is real based on file content.
  likely_intentional — LLM thinks this is by design (base class, registry, etc.).
  unverified        — LLM returned invalid response or call failed.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

_VALID_VERDICTS = {"confirmed", "likely_intentional", "unverified"}

_SYSTEM_PROMPT = (
    "You are a software architecture reviewer. "
    "You are given a file that a static analyzer has flagged as a potential anti-pattern. "
    "Read the file content and determine if the finding is real or likely intentional design. "
    "Return JSON with keys: verdict (confirmed or likely_intentional), "
    "explanation (one specific sentence about what you see in this file). "
    "Be specific — name actual functions, classes, or responsibilities you observe."
)

_MAX_CONTENT_CHARS = 2000


@dataclass
class AntiPatternVerdict:
    verdict: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def confirm_antipattern(
    pattern_type: str,
    file_path: str,
    file_content: str,
    llm_client: Any,
) -> AntiPatternVerdict:
    """Confirm or question a static anti-pattern finding.
    Never raises — returns verdict='unverified' on any error.
    """
    try:
        truncated = file_content[:_MAX_CONTENT_CHARS]
        user_content = (
            f"Anti-pattern detected: {pattern_type}\n"
            f"File: {file_path}\n\n"
            f"File content:\n```\n{truncated}\n```\n\n"
            "Is this anti-pattern real or likely intentional design?"
        )
        response = llm_client.generate_json(_SYSTEM_PROMPT, user_content)
        verdict = str(response.get("verdict") or "").strip().lower()
        if verdict not in _VALID_VERDICTS:
            verdict = "unverified"
        return AntiPatternVerdict(
            verdict=verdict,
            explanation=str(response.get("explanation") or ""),
        )
    except Exception:
        return AntiPatternVerdict(verdict="unverified", explanation="")
