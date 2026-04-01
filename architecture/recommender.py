from __future__ import annotations

import json
from typing import Any, Dict, List

from StructIQ.config import settings
from StructIQ.llm.client import LLMClient


class RecommendationEngine:
    """Generate high-level architecture recommendations from Phase 2 artifacts."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client  # None until first use

    def _get_client(self) -> LLMClient:
        assert self._llm_client is not None, "_get_client called without an llm_client"
        return self._llm_client

    def generate(self, input_data: dict) -> dict:
        if self._llm_client is None:
            return {"recommendations": [], "root_cause_narrative": ""}

        if not isinstance(input_data, dict):
            return {"recommendations": [], "root_cause_narrative": ""}

        clusters = input_data.get("clusters") or {}
        anti_patterns = input_data.get("anti_patterns") or []
        entry_points = input_data.get("entry_points") or []

        compressed_clusters: Dict[str, int] = {
            str(k): len(v) if isinstance(v, list) else 0
            for k, v in clusters.items()
        }
        top_anti_patterns = sorted(
            [ap for ap in anti_patterns if isinstance(ap, dict)],
            key=lambda x: (0 if x.get("severity") == "high" else 1, x.get("type", "")),
        )[:10]

        payload = {
            "cluster_summary": compressed_clusters,
            "anti_patterns": top_anti_patterns,
            "entry_points": list(entry_points)[:20],
        }

        prompt = (
            "You are an architecture advisor. "
            "Return JSON only with top-level keys 'recommendations' and 'root_cause_narrative'. "
            "'root_cause_narrative' must be a single string of 2-3 sentences connecting "
            "all detected anti-patterns into one coherent architectural story. "
            "'recommendations' must be an array of objects. "
            "Each recommendation object must include: "
            "'message' (concise action), "
            "'based_on' (array of anti-pattern types/reasons), "
            "'affected_files' (array of affected file or module paths/names). "
            "Focus on actionable refactoring priorities from provided architecture data. "
            "Do not include source code, markdown, or extra top-level keys."
        )

        try:
            response = self._get_client().generate_json(prompt, json.dumps(payload))
        except Exception:
            return {"recommendations": [], "root_cause_narrative": ""}

        narrative = (
            str(response.get("root_cause_narrative", "")).strip()
            if isinstance(response, dict)
            else ""
        )

        recs = response.get("recommendations") if isinstance(response, dict) else []
        if not isinstance(recs, list):
            return {"recommendations": [], "root_cause_narrative": narrative}

        cleaned: List[Dict[str, Any]] = []
        for item in recs:
            if not isinstance(item, dict):
                continue

            message = str(item.get("message", "")).strip()
            if not message:
                continue

            based_on_raw = item.get("based_on", [])
            affected_raw = item.get("affected_files", [])

            based_on = (
                [str(v).strip() for v in based_on_raw if str(v).strip()]
                if isinstance(based_on_raw, list)
                else []
            )
            affected_files = (
                [str(v).strip() for v in affected_raw if str(v).strip()]
                if isinstance(affected_raw, list)
                else []
            )

            cleaned.append(
                {
                    "message": message,
                    "based_on": based_on,
                    "affected_files": affected_files,
                }
            )

        return {"recommendations": cleaned, "root_cause_narrative": narrative}
