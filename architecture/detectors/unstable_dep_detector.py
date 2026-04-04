"""Stable Dependencies Principle violation detector."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class UnstableDependencyDetector(BaseDetector):
    id = "unstable_dependency"
    name = "Unstable dependency"
    category = "structural"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            inst: dict[str, float] = {}
            for rec in analysis.get("coupling_scores") or []:
                if not isinstance(rec, dict):
                    continue
                fp = rec.get("file")
                if not isinstance(fp, str):
                    continue
                raw = rec.get("instability")
                try:
                    inst[fp] = float(raw) if raw is not None else 0.5
                except (TypeError, ValueError):
                    inst[fp] = 0.5

            violations: list[tuple[float, AntiPatternResult]] = []
            for e in graph.get("edges") or []:
                if not isinstance(e, dict):
                    continue
                s, t = e.get("source"), e.get("target")
                if not isinstance(s, str) or not isinstance(t, str):
                    continue
                si = inst.get(s, 0.5)
                ti = inst.get(t, 0.5)
                if si <= 0.3 and ti >= 0.8:
                    severity_gap = ti - si
                    violations.append(
                        (
                            -severity_gap,
                            {
                                "type": "unstable_dependency",
                                "category": "structural",
                                "severity": "medium",
                                "file": s,
                                "description": (
                                    "Stable file depends on highly unstable file — "
                                    "violates Stable Dependencies Principle"
                                ),
                                "metrics": {
                                    "file_instability": si,
                                    "dependency": t,
                                    "dependency_instability": ti,
                                },
                                "effort": "medium",
                            },
                        )
                    )

            violations.sort(key=lambda x: (x[0], x[1].get("file", ""), x[1].get("metrics", {}).get("dependency", "")))
            return [v[1] for v in violations[:10]]
        except Exception:
            return []
