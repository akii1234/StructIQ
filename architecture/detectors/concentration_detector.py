"""Concentration risk — coupling concentrated in top files."""
from __future__ import annotations

import math
from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class ConcentrationRiskDetector(BaseDetector):
    id = "concentration_risk"
    name = "Concentration risk"
    category = "structural"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            nodes = graph.get("nodes") or []
            node_ids = [
                str(n["id"])
                for n in nodes
                if isinstance(n, dict) and isinstance(n.get("id"), str)
            ]
            n = len(node_ids)
            if n < 5:
                return []

            ca_ce: dict[str, int] = {}
            for rec in analysis.get("coupling_scores") or []:
                if not isinstance(rec, dict):
                    continue
                fp = rec.get("file")
                if not isinstance(fp, str) or fp not in node_ids:
                    continue
                try:
                    ca = int(rec.get("afferent_coupling", 0) or 0)
                    ce = int(rec.get("efferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    continue
                ca_ce[fp] = ca + ce

            if not ca_ce:
                return []

            ranked = sorted(ca_ce.items(), key=lambda x: (-x[1], x[0]))
            top_n = max(1, math.ceil(0.1 * n))
            top_set = {fp for fp, _ in ranked[:top_n]}

            edges = graph.get("edges") or []
            total_edges = len(edges)
            if total_edges == 0:
                return []

            touched = 0
            for e in edges:
                if not isinstance(e, dict):
                    continue
                s, t = e.get("source"), e.get("target")
                if not isinstance(s, str) or not isinstance(t, str):
                    continue
                if s in top_set or t in top_set:
                    touched += 1

            edge_share_pct = round(100.0 * touched / total_edges, 1)
            if edge_share_pct > 60:
                return [
                    {
                        "type": "concentration_risk",
                        "category": "structural",
                        "severity": "medium",
                        "module": "system",
                        "description": (
                            f"{edge_share_pct}% of all dependencies concentrate in the "
                            f"top {top_n} files — high systemic fragility"
                        ),
                        "metrics": {
                            "top_10pct_files": top_n,
                            "edge_share_pct": edge_share_pct,
                            "threshold_pct": 60,
                        },
                        "effort": "high",
                    }
                ]
            return []
        except Exception:
            return []
