"""Builds a token-efficient digest of all phase outputs for LLM consumption."""
from __future__ import annotations

from typing import Any


class DigestBuilder:
    """Assembles a structured context digest. Target: < 1500 tokens."""

    def build(
        self,
        phase1: dict[str, Any],
        graph: dict[str, Any],
        analysis: dict[str, Any],
        insights: dict[str, Any],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Build digest. All fields are bounded to prevent token explosion."""
        return {
            "system": {
                "total_files": len(phase1.get("files") or []),
                "languages": list(
                    {
                        f.get("language")
                        for f in (phase1.get("classified_files") or [])
                        if f.get("language")
                    }
                ),
                "total_edges": len(graph.get("edges") or []),
                "entry_points": (analysis.get("entry_points") or [])[:5],
                "overall_score": insights.get("overall_score"),
                "overall_grade": insights.get("overall_grade"),
            },
            "domain_scores": {
                domain: {
                    "score": data.get("score"),
                    "grade": data.get("grade"),
                    "finding_count": data.get("finding_count"),
                }
                for domain, data in (insights.get("domain_scores") or {}).items()
            },
            "top_anti_patterns": [
                {
                    "type": ap.get("type"),
                    "severity": ap.get("severity"),
                    "file": ap.get("file")
                    or ap.get("module")
                    or ", ".join((ap.get("files") or [])[:2]),
                    "description": str(ap.get("description", ""))[:120],
                }
                for ap in sorted(
                    (insights.get("anti_patterns") or []),
                    key=lambda x: {
                        "high": 3,
                        "medium": 2,
                        "low": 1,
                    }.get(x.get("severity", "low"), 0),
                    reverse=True,
                )[:8]
            ],
            "services": {
                k: v[:4]  # max 4 files per service shown
                for k, v in list((insights.get("services") or {}).items())[:8]
            },
            "plan_summary": {
                "decision": plan.get("decision"),
                "plan_mode": plan.get("plan_mode"),
                "task_count": len(plan.get("tasks") or []),
                "top_tasks": [
                    {
                        "type": t.get("type"),
                        "priority": t.get("priority"),
                        "target": (t.get("target") or [])[:2],
                    }
                    for t in (plan.get("tasks") or [])[:5]
                ],
            },
            "migration_blockers": [
                ap
                for ap in (insights.get("anti_patterns") or [])
                if ap.get("type")
                in (
                    "no_abstraction_layer",
                    "hardcoded_config",
                    "test_gap",
                    "large_function",
                    "god_file",
                )
            ][:5],
        }
