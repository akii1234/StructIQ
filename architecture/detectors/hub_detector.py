"""Hub file detector — high fan-in, low fan-out (not god file)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class HubFileDetector(BaseDetector):
    id = "hub_file"
    name = "Hub file"
    category = "structural"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            from StructIQ.architecture.analyzer import ArchitectureAnalyzer

            analyzer = ArchitectureAnalyzer()
            god_paths = {
                ap["file"]
                for ap in analyzer.detect_god_files(analysis)
                if isinstance(ap.get("file"), str)
            }

            out: list[AntiPatternResult] = []
            for rec in analysis.get("coupling_scores") or []:
                if not isinstance(rec, dict):
                    continue
                fp = rec.get("file")
                if not isinstance(fp, str) or fp in god_paths:
                    continue
                try:
                    ca = int(rec.get("afferent_coupling", 0) or 0)
                    ce = int(rec.get("efferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if ca >= 8 and ce <= 1:
                    out.append(
                        {
                            "type": "hub_file",
                            "category": "structural",
                            "severity": "high",
                            "file": fp,
                            "description": (
                                f"File is depended on by {ca} other files but depends on "
                                "almost nothing — single point of structural failure"
                            ),
                            "metrics": {
                                "afferent_coupling": ca,
                                "efferent_coupling": ce,
                                "threshold": 8,
                            },
                            "effort": "high",
                        }
                    )
            return out
        except Exception:
            return []
