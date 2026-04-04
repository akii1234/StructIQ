"""Sends digest to LLM once, returns 4 narrative fields."""
from __future__ import annotations

import json
from typing import Any

from StructIQ.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a senior software architect analyzing a codebase intelligence report.
You will receive a structured digest of static analysis findings.
Return JSON with exactly these 4 keys:

"system_narrative": 3 short paragraphs. Para 1: what this system is and what it does (infer from file names and services). Para 2: how data flows through the main entry points. Para 3: the dominant architectural pattern you see.

"onboarding_guide": A 5-item plain-English list for a senior engineer joining today. Each item is one sentence. Format as a JSON array of strings. Cover: where to start reading, what the core data model is, which files are highest risk to change, what the module structure means, and one non-obvious thing about the architecture.

"domain_narratives": A JSON object with keys "structural", "complexity", "maintainability", "migration". Each value is one plain-English sentence explaining what the score means for this specific codebase — not generic advice.

"migration_assessment": 2-3 sentences. Given the migration blockers found, how ready is this codebase for a stack migration? What must be done first?

Be specific. Use file names and module names from the digest. Do not use markdown."""


class NarrativeGenerator:
    def __init__(self, llm_client: Any) -> None:
        self._client = llm_client

    def generate(self, digest: dict[str, Any]) -> dict[str, Any]:
        """Returns narrative dict. On any failure returns empty strings (non-fatal)."""
        empty = {
            "system_narrative": "",
            "onboarding_guide": [],
            "domain_narratives": {},
            "migration_assessment": "",
        }
        if not self._client:
            return empty
        try:
            user_message = f"Codebase digest:\n{json.dumps(digest, indent=2)}"
            result = self._client.generate_json(SYSTEM_PROMPT, user_message)
            if not isinstance(result, dict):
                return empty
            return {
                "system_narrative": str(result.get("system_narrative", "")),
                "onboarding_guide": result.get("onboarding_guide", []),
                "domain_narratives": result.get("domain_narratives", {}),
                "migration_assessment": str(result.get("migration_assessment", "")),
            }
        except Exception as exc:
            logger.warning(
                "NarrativeGenerator failed (non-fatal): %s", exc, exc_info=True
            )
            return empty
