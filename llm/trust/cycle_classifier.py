"""Cycle Intent Classifier — classify why a circular import exists.

Classifications:
  runtime_critical  — both sides need each other at execution time. Hard to fix.
  type_hint_only    — import only used in type annotations. Fix: TYPE_CHECKING guard.
  test_boundary     — test file importing prod, not a real runtime cycle.
  circular_safe     — intentional design (e.g. plugin registry). Low priority.
  unknown           — LLM could not determine or returned invalid response.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

_VALID_CLASSIFICATIONS = {
    "runtime_critical",
    "type_hint_only",
    "test_boundary",
    "circular_safe",
    "unknown",
}

_SYSTEM_PROMPT = (
    "You are a Python static analysis expert. "
    "You are given two files involved in a circular import and the specific import statement. "
    "Classify the import as one of: runtime_critical, type_hint_only, test_boundary, circular_safe. "
    "Return JSON with keys: classification (string), confidence (high/medium/low), "
    "reasoning (one sentence), suggested_fix (string or null). "
    "suggested_fix is required when classification is type_hint_only — provide the exact fix."
)

_MAX_CONTENT_CHARS = 1500  # Per file, to stay within token budget


@dataclass
class CycleClassification:
    classification: str
    confidence: str
    reasoning: str
    suggested_fix: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_cycle(
    source_file: str,
    source_content: str,
    target_file: str,
    target_content: str,
    raw_import: str,
    llm_client: Any,
) -> CycleClassification:
    """Classify the intent of a circular import. Returns CycleClassification.
    Never raises — returns classification='unknown' on any error.
    """
    try:
        truncated_source = source_content[:_MAX_CONTENT_CHARS]
        truncated_target = target_content[:_MAX_CONTENT_CHARS]
        user_content = (
            f"File A: {source_file}\n```\n{truncated_source}\n```\n\n"
            f"File B: {target_file}\n```\n{truncated_target}\n```\n\n"
            f"Circular import statement in File A: `{raw_import}`\n\n"
            "Classify this circular import."
        )
        response = llm_client.generate_json(_SYSTEM_PROMPT, user_content)
        classification = str(response.get("classification") or "").strip().lower()
        if classification not in _VALID_CLASSIFICATIONS:
            classification = "unknown"
        return CycleClassification(
            classification=classification,
            confidence=str(response.get("confidence") or "low"),
            reasoning=str(response.get("reasoning") or ""),
            suggested_fix=response.get("suggested_fix") or None,
        )
    except Exception:
        return CycleClassification(
            classification="unknown",
            confidence="low",
            reasoning="",
            suggested_fix=None,
        )
