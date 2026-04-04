"""High coupling anti-pattern detector (registry adapter)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class HighCouplingDetector(BaseDetector):
    id = "high_coupling"
    name = "High coupling"
    category = "complexity"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            from StructIQ.architecture.analyzer import ArchitectureAnalyzer

            analyzer = ArchitectureAnalyzer()
            god_file_results = analyzer.detect_god_files(analysis)
            god_file_paths: set[str] = {
                ap["file"] for ap in god_file_results if "file" in ap
            }
            return [
                ap
                for ap in analyzer.detect_high_coupling(analysis)
                if ap.get("file") not in god_file_paths
            ]
        except Exception:
            return []
